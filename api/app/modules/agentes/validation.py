"""Camada de Validation determinística da grade de estudos. Só regras, sem LLM.

Recebe uma `PropostaGrade` e um `ContextoEstudante` (com janelas livres/ocupadas vindas
da integração com o Google Agenda via `ProvedorAgenda`, além de sono, refeições e vales
circadianos) e devolve um `ResultadoValidacao`.

Regras verificadas:
  - `CONFLITO_AGENDA`: nenhum bloco de estudo pode se sobrepor a eventos ocupados
    (intervalos semiabertos `[inicio, fim)` — eventos adjacentes não conflitam).
    Aceita opcionalmente um `ProvedorAgenda` para conferir compromissos atualizados
    diretamente na agenda (ex.: Google Calendar) antes da gravação.
  - `INTEGRIDADE_CIRCADIANA`: protege sono, higiene do sono (padrão: 60 min antes de
    dormir para blocos de alta carga), janelas de refeição e vales circadianos/pós-prandiais
    (blocos de alta carga).
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, time, timedelta

from .contratos import (
    BlocoEstudo,
    ContextoEstudante,
    Janela,
    PropostaGrade,
    ProvedorAgenda,
    ResultadoValidacao,
    Violacao,
)

REGRA_CONFLITO_AGENDA = "CONFLITO_AGENDA"
REGRA_INTEGRIDADE_CIRCADIANA = "INTEGRIDADE_CIRCADIANA"

HIGIENE_SONO_PADRAO_MIN = 60

_SEGUNDOS_DIA = 24 * 60 * 60
_FIM_DIA_SONO_SEG = 23 * 3600 + 59 * 60  # convenção de contratos.py: sono cruzando meia-noite termina em 23:59

_DIAS_SEMANA = (
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
)

Intervalo = tuple[int, int]  # [inicio_seg, fim_seg) dentro do dia


def _para_segundos(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def _formatar_hora(t: time) -> str:
    return t.strftime("%H:%M") if t.second == 0 else t.strftime("%H:%M:%S")


def _formatar_segundos(seg: int) -> str:
    if seg >= _SEGUNDOS_DIA:
        return "24:00"
    horas, resto = divmod(seg, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}" if segundos == 0 else f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def _nome_dia(dia: date) -> str:
    return _DIAS_SEMANA[dia.weekday()]


def _sobrepoe(a: Intervalo, b: Intervalo) -> bool:
    """Sobreposição estrita de intervalos semiabertos [inicio, fim)."""
    return max(a[0], b[0]) < min(a[1], b[1])


def _unir(intervalos: Iterable[Intervalo], *, unir_adjacentes: bool = True) -> list[Intervalo]:
    out: list[Intervalo] = []
    for ini, fim in sorted(intervalos):
        if out and (ini <= out[-1][1] if unir_adjacentes else ini < out[-1][1]):
            out[-1] = (out[-1][0], max(out[-1][1], fim))
        else:
            out.append((ini, fim))
    return out


def _subtrair(base: list[Intervalo], cortes: list[Intervalo]) -> list[Intervalo]:
    out: list[Intervalo] = []
    for a, b in base:
        pedacos = [(a, b)]
        for c, d in cortes:
            pedacos = [
                p
                for x, y in pedacos
                for p in ((x, min(y, c)), (max(x, d), y))
                if p[0] < p[1]
            ]
        out.extend(pedacos)
    return _unir(out, unir_adjacentes=True)


def _por_dia(janelas: Iterable[Janela], *, unir_adjacentes: bool = True) -> dict[date, list[Intervalo]]:
    dias: dict[date, list[Intervalo]] = defaultdict(list)
    for j in janelas:
        dias[j.dia].append((_para_segundos(j.inicio), _para_segundos(j.fim)))
    return {dia: _unir(ivs, unir_adjacentes=unir_adjacentes) for dia, ivs in dias.items()}


def _intervalo_bloco(bloco: BlocoEstudo) -> Intervalo:
    return _para_segundos(bloco.inicio), _para_segundos(bloco.fim)


def janelas_higiene_sono(
    sono: Iterable[Janela],
    *,
    higiene_sono_min: int = HIGIENE_SONO_PADRAO_MIN,
) -> dict[date, list[Intervalo]]:
    """Calcula a janela de higiene do sono (ex.: 60 min antes de dormir) para cada início de sono.

    Respeita a convenção de `contratos.py` para sono que cruza a meia-noite: quando um dia
    termina dormindo (fim >= 23:59) e o dia seguinte começa dormindo em 00:00, trata 00:00
    como continuação do mesmo sono, sem gerar higiene falsa no meio da madrugada.
    """
    if higiene_sono_min <= 0:
        return {}

    higiene_seg = higiene_sono_min * 60
    sono_por_dia = _por_dia(sono, unir_adjacentes=True)
    dias_cruza_meia_noite = {
        dia for dia, ivs in sono_por_dia.items() if any(fim >= _FIM_DIA_SONO_SEG for _, fim in ivs)
    }

    brutas: dict[date, list[Intervalo]] = defaultdict(list)
    for dia, ivs in sono_por_dia.items():
        for ini, _ in ivs:
            if ini == 0 and (dia - timedelta(days=1)) in dias_cruza_meia_noite:
                continue
            if ini >= higiene_seg:
                brutas[dia].append((ini - higiene_seg, ini))
            else:
                if ini > 0:
                    brutas[dia].append((0, ini))
                falta = higiene_seg - ini
                brutas[dia - timedelta(days=1)].append((_SEGUNDOS_DIA - falta, _SEGUNDOS_DIA))

    resultado: dict[date, list[Intervalo]] = {}
    for dia, ivs in brutas.items():
        limpas = _subtrair(_unir(ivs, unir_adjacentes=True), sono_por_dia.get(dia, []))
        if limpas:
            resultado[dia] = limpas
    return resultado


def verificar_conflito_agenda(
    proposta: PropostaGrade,
    contexto: ContextoEstudante,
    *,
    ocupados_extras: Iterable[Janela] = (),
) -> list[Violacao]:
    """Regra `CONFLITO_AGENDA`: nenhum bloco sobreposto a eventos ocupados da agenda."""
    # Unifica apenas eventos que se sobrepõem (comum em convites simultâneos no Google Agenda),
    # preservando compromissos adjacentes (ex.: 09:00-10:00 e 10:00-11:00) para mensagens precisas.
    ocupados_por_dia = _por_dia([*contexto.ocupados, *ocupados_extras], unir_adjacentes=False)
    violacoes: list[Violacao] = []

    for bloco in proposta.blocos:
        iv_bloco = _intervalo_bloco(bloco)
        for occ_ini, occ_fim in ocupados_por_dia.get(bloco.dia, []):
            if _sobrepoe(iv_bloco, (occ_ini, occ_fim)):
                violacoes.append(
                    Violacao(
                        regra=REGRA_CONFLITO_AGENDA,
                        dia=bloco.dia,
                        bloco_id=bloco.id,
                        mensagem=(
                            f"{_nome_dia(bloco.dia)}: o bloco das {_formatar_hora(bloco.inicio)} "
                            f"de {bloco.disciplina} se sobrepõe a um compromisso das "
                            f"{_formatar_segundos(occ_ini)} às {_formatar_segundos(occ_fim)}."
                        ),
                        excesso_min=None,
                    )
                )
    return violacoes


def verificar_integridade_circadiana(
    proposta: PropostaGrade,
    contexto: ContextoEstudante,
    *,
    higiene_sono_min: int = HIGIENE_SONO_PADRAO_MIN,
) -> list[Violacao]:
    """Regra `INTEGRIDADE_CIRCADIANA`: protege sono, higiene do sono, refeições e vales circadianos."""
    sono_por_dia = _por_dia(contexto.sono, unir_adjacentes=True)
    higiene_por_dia = janelas_higiene_sono(contexto.sono, higiene_sono_min=higiene_sono_min)
    refeicoes_por_dia = _por_dia(contexto.refeicoes, unir_adjacentes=True)
    vales_por_dia = _por_dia(contexto.vales, unir_adjacentes=True)

    violacoes: list[Violacao] = []
    for bloco in proposta.blocos:
        iv_bloco = _intervalo_bloco(bloco)
        alta = bloco.carga == "alta"
        rotulo_carga = "alta carga" if alta else "baixa carga"
        dia_txt = _nome_dia(bloco.dia)
        hora_txt = _formatar_hora(bloco.inicio)

        em_sono = any(_sobrepoe(iv_bloco, iv) for iv in sono_por_dia.get(bloco.dia, []))
        if em_sono:
            violacoes.append(
                Violacao(
                    regra=REGRA_INTEGRIDADE_CIRCADIANA,
                    dia=bloco.dia,
                    bloco_id=bloco.id,
                    mensagem=f"{dia_txt}: bloco de {rotulo_carga} às {hora_txt}, dentro da janela de sono.",
                    excesso_min=None,
                )
            )
        elif alta and any(_sobrepoe(iv_bloco, iv) for iv in higiene_por_dia.get(bloco.dia, [])):
            violacoes.append(
                Violacao(
                    regra=REGRA_INTEGRIDADE_CIRCADIANA,
                    dia=bloco.dia,
                    bloco_id=bloco.id,
                    mensagem=(
                        f"{dia_txt}: bloco de alta carga às {hora_txt}, na janela de higiene do sono "
                        f"({higiene_sono_min} min antes de dormir)."
                    ),
                    excesso_min=None,
                )
            )

        if any(_sobrepoe(iv_bloco, iv) for iv in refeicoes_por_dia.get(bloco.dia, [])):
            violacoes.append(
                Violacao(
                    regra=REGRA_INTEGRIDADE_CIRCADIANA,
                    dia=bloco.dia,
                    bloco_id=bloco.id,
                    mensagem=f"{dia_txt}: bloco de {rotulo_carga} às {hora_txt}, durante a janela de refeição.",
                    excesso_min=None,
                )
            )

        if alta and any(_sobrepoe(iv_bloco, iv) for iv in vales_por_dia.get(bloco.dia, [])):
            violacoes.append(
                Violacao(
                    regra=REGRA_INTEGRIDADE_CIRCADIANA,
                    dia=bloco.dia,
                    bloco_id=bloco.id,
                    mensagem=f"{dia_txt}: bloco de alta carga às {hora_txt}, no vale pós-prandial.",
                    excesso_min=None,
                )
            )

    return violacoes


def validar(
    proposta: PropostaGrade,
    contexto: ContextoEstudante,
    *,
    higiene_sono_min: int = HIGIENE_SONO_PADRAO_MIN,
    provedor_agenda: ProvedorAgenda | None = None,
) -> ResultadoValidacao:
    """Valida `PropostaGrade` + `ContextoEstudante` de forma 100% determinística (zero LLM)."""
    ocupados_extras: list[Janela] = []
    if provedor_agenda is not None and proposta.blocos:
        dias = [b.dia for b in proposta.blocos]
        _, ocupados_extras = provedor_agenda.ler_janelas(min(dias), max(dias))

    violacoes = [
        *verificar_conflito_agenda(proposta, contexto, ocupados_extras=ocupados_extras),
        *verificar_integridade_circadiana(proposta, contexto, higiene_sono_min=higiene_sono_min),
    ]

    ordem_bloco = {b.id: idx for idx, b in enumerate(proposta.blocos)}
    violacoes.sort(key=lambda v: (v.dia, ordem_bloco.get(v.bloco_id or "", len(ordem_bloco)), v.regra))

    status = "REPROVADO" if violacoes else "APROVADO"
    return ResultadoValidacao(status=status, violacoes=violacoes)


class AgenteValidation:
    """Fachada do agente de Validation determinístico (compatível com o Maestro)."""

    nome = "Validation"

    def __init__(
        self,
        *,
        higiene_sono_min: int = HIGIENE_SONO_PADRAO_MIN,
        provedor_agenda: ProvedorAgenda | None = None,
    ) -> None:
        self.higiene_sono_min = higiene_sono_min
        self.provedor_agenda = provedor_agenda

    def validar(self, proposta: PropostaGrade, contexto: ContextoEstudante) -> ResultadoValidacao:
        return validar(
            proposta,
            contexto,
            higiene_sono_min=self.higiene_sono_min,
            provedor_agenda=self.provedor_agenda,
        )
