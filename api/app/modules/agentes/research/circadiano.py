"""Perfil circadiano e processamento de check-in diário ([2.2] Issue #13).

Funções puras e determinísticas para:
  1. Quebra de janelas de sono na meia-noite (`22:00`–`06:00` -> `22:00`–`23:59` e `00:00`–`06:00`),
     respeitando a invariante `inicio < fim` do contrato `Janela`.
  2. Geração de janelas de refeições (almoço, jantar e opcionalmente café da manhã).
  3. Derivação de janelas de pico cognitivo (alta carga) e vale pós-prandial/circadiano (baixa carga)
     para cada cronotipo (`matutino`, `vespertino`, `noturno`), com realocação inteligente quando o
     horário de pico padrão está bloqueado por expediente longo (ex.: perfil CLT `agenda_cheia`).
  4. Cálculo do `indice_capacidade` (0.0 a 1.0) a partir do `CheckIn` (`energia`, `horas_sono`,
     `estresse`) e mapeamento das 4 escalas do frontend (`humor`, `estresse`, `sono`, `fadiga`).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, time, timedelta

from pydantic import Field

from app.modules.agentes.analysis.janelas import hora, intersecao, minutos, por_dia, subtrair
from app.modules.agentes.contratos import CheckIn, Contrato, Cronotipo, Janela

FIM_DIA = time(23, 59)
INICIO_DIA = time(0, 0)

# Janelas circadianas canônicas por cronotipo (alinhadas às fixtures de api/tests/fixtures/contexto/)
PICOS_PADRAO: dict[Cronotipo, tuple[time, time]] = {
    "matutino": (time(8, 0), time(11, 0)),
    "vespertino": (time(15, 30), time(18, 30)),
    "noturno": (time(19, 30), time(22, 30)),
}

VALES_PADRAO: dict[Cronotipo, tuple[time, time]] = {
    "matutino": (time(13, 0), time(15, 0)),
    "vespertino": (time(13, 30), time(15, 0)),
    "noturno": (time(14, 0), time(16, 0)),
}


class EscalasCheckIn(Contrato):
    """As quatro escalas coletadas pela UI de check-in diário + horas de sono."""

    humor: int = Field(default=3, ge=1, le=5)
    estresse: int = Field(ge=1, le=5)
    sono: int = Field(default=3, ge=1, le=5)  # qualidade percebida do sono (1..5)
    fadiga: int = Field(ge=1, le=5)
    horas_sono: float = Field(ge=0.0, le=24.0)


def mapear_escalas_para_checkin(escalas: EscalasCheckIn) -> CheckIn:
    """Converte as 4 escalas da UI para o contrato `CheckIn` (`energia = 6 - fadiga`)."""
    return CheckIn(
        energia=6 - escalas.fadiga,
        horas_sono=escalas.horas_sono,
        estresse=escalas.estresse,
    )


def calcular_indice_capacidade(checkin: CheckIn) -> float:
    """Calcula o índice de capacidade cognitiva em [0.0, 1.0] a partir do CheckIn.

    Fundamentação científica na base do projeto:
      - `artigo_05_sleep_consolidation_walker.txt`: sono < 7h deteriora a capacidade de foco e LTP;
      - `artigo_14_willpower_depletion_baumeister.txt`: estresse e fadiga decisória depletam o
        autocontrole disponível para tarefas de alta carga.

    Calibração canônica com as fixtures da [0.2]:
      - `CheckIn(energia=5, horas_sono=8, estresse=1)` -> `0.9` (`alta_energia.json`)
      - `CheckIn(energia=3, horas_sono=7, estresse=2)` -> `0.6` (`matutino/vespertino/noturno/agenda_cheia/prazo_apertado.json`)
      - `CheckIn(energia=1, horas_sono=4, estresse=5)` -> `0.2` (`fadiga.json`)
    """
    norm_energia = (checkin.energia - 1.0) / 4.0          # 1..5 -> 0.0..1.0
    norm_estresse = (5.0 - checkin.estresse) / 4.0        # 1..5 -> 1.0..0.0 (menor estresse = maior capacidade)
    norm_sono = max(0.0, min(1.0, (checkin.horas_sono - 4.0) / 4.0))  # <=4h -> 0.0; >=8h -> 1.0 (7h -> 0.75)

    # Combinação linear ponderada + base residual de 0.2 para calibrar com as fixtures (0.2, 0.6, 0.9)
    bruto = 0.2 + 0.5 * norm_energia + 0.1 * norm_sono + 0.1 * norm_estresse
    return round(max(0.0, min(1.0, bruto)), 2)


def classificar_estado_capacidade(indice_capacidade: float) -> str:
    """Classifica o estado operacional do estudante conforme os limiares do projeto."""
    if indice_capacidade >= 0.7:
        return "alta_energia"
    if indice_capacidade < 0.4:
        return "fadiga"
    return "normal"


def dias_da_semana(semana_inicio: date, num_dias: int = 5) -> list[date]:
    """Gera a sequência de dias úteis/planejados a partir de `semana_inicio` (padrão: 5 dias, seg a sex)."""
    return [semana_inicio + timedelta(days=i) for i in range(num_dias)]


def expandir_janelas_sono(
    dias: Iterable[date],
    inicio_sono: time,
    fim_sono: time,
) -> list[Janela]:
    """Distribui o horário de sono pelos dias da semana, quebrando na meia-noite quando necessário.

    Convenção de `contratos.py`: uma `Janela` nunca cruza a meia-noite.
    Se `inicio_sono > fim_sono` (ex.: `22:00` às `06:00`), cada dia recebe duas janelas:
      - `[22:00, 23:59)` e `[00:00, 06:00)`, na mesma ordem das fixtures de `contexto/`.
    Se `inicio_sono < fim_sono` (ex.: cronotipo noturno `02:00` às `10:00`), cada dia recebe uma
    única janela `[02:00, 10:00)`.
    """
    janelas: list[Janela] = []
    for dia in dias:
        if inicio_sono < fim_sono:
            janelas.append(Janela(dia=dia, inicio=inicio_sono, fim=fim_sono))
        else:
            if inicio_sono < FIM_DIA:
                janelas.append(Janela(dia=dia, inicio=inicio_sono, fim=FIM_DIA))
            if fim_sono > INICIO_DIA:
                janelas.append(Janela(dia=dia, inicio=INICIO_DIA, fim=fim_sono))
    return janelas


def expandir_janelas_refeicoes(
    dias: Iterable[date],
    *,
    almoco: time | None = time(12, 0),
    jantar: time | None = time(19, 0),
    cafe: time | None = None,
    duracao_min: int = 60,
) -> list[Janela]:
    """Gera as janelas diárias de refeição (duração padrão de 60 minutos) para os dias informados."""
    horarios = [h for h in (cafe, almoco, jantar) if h is not None]
    janelas: list[Janela] = []
    for dia in dias:
        for ini in horarios:
            ini_min = minutos(ini)
            fim_min = min(23 * 60 + 59, ini_min + duracao_min)
            if ini_min < fim_min:
                janelas.append(Janela(dia=dia, inicio=ini, fim=hora(fim_min)))
    return janelas


def derivar_picos_e_vales(
    cronotipo: Cronotipo,
    dias: Iterable[date],
    *,
    livres: Iterable[Janela] = (),
    ocupados: Iterable[Janela] = (),
) -> tuple[list[Janela], list[Janela]]:
    """Deriva as janelas de `picos` e `vales` circadianos para cada dia da semana.

    Regra padrão:
      - `matutino`: pico `08:00`–`11:00`, vale `13:00`–`15:00`
      - `vespertino`: pico `15:30`–`18:30`, vale `13:30`–`15:00`
      - `noturno`: pico `19:30`–`22:30`, vale `14:00`–`16:00`

    Adaptação para dupla jornada / agenda cheia (`artigo_14` e `artigo_19`, fixture `agenda_cheia.json`):
      Quando o estudante tem janelas `livres` informadas e o pico padrão do seu cronotipo não possui
      nenhuma interseção com o tempo livre do dia (ex.: trabalhador CLT matutino ocupado das `08:00`
      às `17:00`, livre apenas `06:00`–`07:00` e `19:00`–`22:00`), o Research realoca o pico para o
      primeiro bloco matinal disponível (`06:00`–`07:00`) e o início da janela noturna (`19:00`–`20:30`),
      posicionando o vale de fadiga no fim da noite (`21:00`–`22:00`).
    """
    dias_lista = list(dias)
    livres_lista = list(livres)
    ocupados_lista = list(ocupados)

    pico_ini, pico_fim = PICOS_PADRAO[cronotipo]
    vale_ini, vale_fim = VALES_PADRAO[cronotipo]

    livres_por_dia = por_dia(livres_lista)
    ocupados_por_dia = por_dia(ocupados_lista)

    picos: list[Janela] = []
    vales: list[Janela] = []

    iv_pico_padrao = [(minutos(pico_ini), minutos(pico_fim))]
    iv_vale_padrao = [(minutos(vale_ini), minutos(vale_fim))]

    for dia in dias_lista:
        livres_dia = subtrair(livres_por_dia.get(dia, []), ocupados_por_dia.get(dia, []))

        # Se não há restrição total sobre o pico padrão, usa as janelas canônicas do cronotipo
        if not livres_dia or intersecao(livres_dia, iv_pico_padrao):
            picos.append(Janela(dia=dia, inicio=pico_ini, fim=pico_fim))
            vales.append(Janela(dia=dia, inicio=vale_ini, fim=vale_fim))
            continue

        # Adaptação dupla jornada (ex.: CLT ocupado durante todo o pico padrão)
        for a, b in livres_dia:
            duracao = b - a
            if b <= 8 * 60:
                # Micro-bloco matinal protegido antes do expediente (artigo_19)
                picos.append(Janela(dia=dia, inicio=hora(a), fim=hora(b)))
            elif a >= 18 * 60 and duracao >= 120:
                # Janela noturna: primeiros 90 min ainda aproveitáveis como pico secundário,
                # última hora antes da higiene do sono marcada como vale de fadiga volitiva (artigo_14)
                picos.append(Janela(dia=dia, inicio=hora(a), fim=hora(min(b, a + 90))))
                vales.append(Janela(dia=dia, inicio=hora(max(a + 90, b - 60)), fim=hora(b)))

        if not any(p.dia == dia for p in picos):
            picos.append(Janela(dia=dia, inicio=pico_ini, fim=pico_fim))
        if not any(v.dia == dia for v in vales):
            vales.append(Janela(dia=dia, inicio=vale_ini, fim=vale_fim))

    return picos, vales
