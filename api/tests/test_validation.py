"""Testes do Validation determinístico (`CONFLITO_AGENDA`, `INTEGRIDADE_CIRCADIANA` e `SOBRECARGA`).

Usam as fixtures de `api/tests/fixtures/` e garantem zero chamadas a LLM. Rodam no CI.
Rodar (a partir de api/): python -m pytest -q
"""

import inspect
from datetime import date, time
from pathlib import Path

import pytest

from app.core.config import Settings
from app.modules.agentes import validation
from app.modules.agentes.contratos import (
    BlocoEstudo,
    CheckIn,
    ContextoEstudante,
    Janela,
    PropostaGrade,
    ResultadoValidacao,
)
from app.modules.agentes.validation import (
    REGRA_CONFLITO_AGENDA,
    REGRA_INTEGRIDADE_CIRCADIANA,
    REGRA_SOBRECARGA,
    AgenteValidation,
    calcular_limiares,
    formatar_relatorio,
    validar,
    verificar_conflito_agenda,
    verificar_integridade_circadiana,
    verificar_sobrecarga,
)
from app.modules.rag import llm

FIXTURES = Path(__file__).parent / "fixtures"


def carregar_contexto(nome: str) -> ContextoEstudante:
    return ContextoEstudante.model_validate_json((FIXTURES / "contexto" / f"{nome}.json").read_text(encoding="utf-8"))


def carregar_proposta(nome: str) -> PropostaGrade:
    return PropostaGrade.model_validate_json((FIXTURES / "proposta" / f"{nome}.json").read_text(encoding="utf-8"))


def carregar_resultado(nome: str) -> ResultadoValidacao:
    return ResultadoValidacao.model_validate_json((FIXTURES / "resultado" / f"{nome}.json").read_text(encoding="utf-8"))


def bloco(
    bloco_id: str,
    dia: date,
    inicio: time,
    fim: time,
    *,
    carga: str = "alta",
    disciplina: str = "Cálculo I",
    material_id: str = "calc-01",
) -> BlocoEstudo:
    foco_min = max(1, (fim.hour * 60 + fim.minute) - (inicio.hour * 60 + inicio.minute))
    return BlocoEstudo(
        id=bloco_id,
        dia=dia,
        inicio=inicio,
        fim=fim,
        disciplina=disciplina,
        material_id=material_id,
        carga=carga,
        tecnica="Pomodoro",
        foco_min=foco_min,
        pausa_min=5,
    )


def proposta_com(ctx: ContextoEstudante, *blocos: BlocoEstudo) -> PropostaGrade:
    return PropostaGrade(estudante_id=ctx.estudante_id, semana_inicio=ctx.semana_inicio, blocos=list(blocos))


class AgendaGoogleFake:
    """Stub de `ProvedorAgenda` simulando eventos ocupados vindos do Google Agenda."""

    def __init__(self, ocupados: list[Janela]) -> None:
        self.ocupados = ocupados
        self.consultas: list[tuple[date, date]] = []

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        self.consultas.append((inicio, fim))
        filtrados = [j for j in self.ocupados if inicio <= j.dia <= fim]
        return [], filtrados

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        return [f"gcal-{b.id}" for b in blocos]


# ---------------------------------------------------------------- fixtures principais (aprova / reprova)
def test_fixture_valida_aprovada_em_todas_as_regras():
    ctx = carregar_contexto("matutino")
    proposta = carregar_proposta("valida")
    esperado = carregar_resultado("aprovado")

    res = validar(proposta, ctx)
    assert res == esperado
    assert res.status == "APROVADO" and res.violacoes == []


def test_fixture_reducao_danos_aprovada_no_contexto_fadiga():
    ctx = carregar_contexto("fadiga")
    proposta = carregar_proposta("reducao_danos")

    res = validar(proposta, ctx)
    assert res.status == "APROVADO" and res.violacoes == []


def test_fixture_violacoes_reprovada_igual_ao_contrato_esperado():
    ctx = carregar_contexto("matutino")
    proposta = carregar_proposta("violacoes")
    esperado = carregar_resultado("reprovado")

    res = validar(proposta, ctx)
    assert res.status == esperado.status == "REPROVADO"
    assert [(v.regra, v.dia, v.bloco_id, v.excesso_min) for v in res.violacoes] == [
        (v.regra, v.dia, v.bloco_id, v.excesso_min) for v in esperado.violacoes
    ]
    assert all("mover 25 min" in v.mensagem for v in res.violacoes)


# ---------------------------------------------------------------- relatório estruturado: todas as fixtures plantadas
FIXTURES_COM_VIOLACAO_PLANTADA = [
    (
        "violacoes",
        "matutino",
        [
            (REGRA_CONFLITO_AGENDA, date(2026, 11, 30), "b1", None),
            (REGRA_INTEGRIDADE_CIRCADIANA, date(2026, 12, 1), "b2", None),
            (REGRA_INTEGRIDADE_CIRCADIANA, date(2026, 12, 2), "b3", None),
        ],
    ),
    (
        "higiene_sono",
        "matutino",
        [
            (REGRA_INTEGRIDADE_CIRCADIANA, date(2026, 11, 30), "b_higiene", None),
        ],
    ),
    (
        "refeicao",
        "matutino",
        [
            (REGRA_INTEGRIDADE_CIRCADIANA, date(2026, 12, 3), "b_refeicao", None),
        ],
    ),
    (
        "sobrecarga_fadiga",
        "fadiga",
        [
            (REGRA_SOBRECARGA, date(2026, 11, 30), None, 32),
        ],
    ),
    (
        "sobrecarga_noturna",
        "noturno",
        [
            (REGRA_INTEGRIDADE_CIRCADIANA, date(2026, 12, 2), "n1", None),
            (REGRA_SOBRECARGA, date(2026, 12, 2), None, 120),
            (REGRA_SOBRECARGA, date(2026, 12, 2), None, 270),
        ],
    ),
]


@pytest.mark.parametrize(
    "nome_proposta,nome_contexto,esperadas",
    FIXTURES_COM_VIOLACAO_PLANTADA,
    ids=[f"{p}_em_{c}" for p, c, _ in FIXTURES_COM_VIOLACAO_PLANTADA],
)
def test_todas_as_fixtures_com_violacao_plantada_geram_violacao_esperada(nome_proposta, nome_contexto, esperadas):
    """Critério de aceite: toda fixture com violação plantada gera regra, dia, bloco e ação úteis ao Analysis."""
    ctx = carregar_contexto(nome_contexto)
    proposta = carregar_proposta(nome_proposta)

    res = validar(proposta, ctx)
    assert res.status == "REPROVADO"
    # Contrato Pydantic ida e volta pelo JSON
    assert ResultadoValidacao.model_validate_json(res.model_dump_json()) == res
    # Exatamente as violações esperadas no dia e bloco certos
    obtidas = [(v.regra, v.dia, v.bloco_id, v.excesso_min) for v in res.violacoes]
    assert obtidas == esperadas

    # Cada mensagem precisa ser legível e indicar ao Analysis o que violou e quanto cortar/mover
    for v in res.violacoes:
        assert any(
            dia in v.mensagem
            for dia in ("Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira")
        )
        assert ("mover " in v.mensagem) or ("cortar " in v.mensagem)


def test_formatar_relatorio_estruturado_aprovado_e_reprovado():
    ctx = carregar_contexto("matutino")
    aprovado = validar(carregar_proposta("valida"), ctx)
    assert formatar_relatorio(aprovado).startswith("APROVADO:")

    reprovado = validar(carregar_proposta("sobrecarga_noturna"), carregar_contexto("noturno"))
    relatorio = formatar_relatorio(reprovado)
    assert "REPROVADO" in relatorio
    assert "[SOBRECARGA]" in relatorio
    assert "estudo noturno ininterrupto" in relatorio
    assert "violando o descanso circadiano" in relatorio
    assert "excesso=120 min" in relatorio


# ---------------------------------------------------------------- CONFLITO_AGENDA (aprova e reprova + Google Agenda)
def test_conflito_agenda_aprova_sem_sobreposicao_e_eventos_adjacentes():
    ctx = carregar_contexto("matutino")  # ocupado segunda 2026-11-30 das 09:00 às 10:00
    # Blocos colados nas bordas (08:35-09:00 e 10:00-10:25) não sobrepõem [09:00, 10:00)
    p = proposta_com(
        ctx,
        bloco("b1", date(2026, 11, 30), time(8, 35), time(9, 0)),
        bloco("b2", date(2026, 11, 30), time(10, 0), time(10, 25)),
        # Mesmo horário em outro dia sem compromisso não conflita
        bloco("b3", date(2026, 12, 1), time(9, 0), time(9, 25)),
    )
    assert verificar_conflito_agenda(p, ctx) == []
    assert validar(p, ctx).status == "APROVADO"


def test_conflito_agenda_reprova_sobreposicoes_parciais_e_totais():
    ctx = carregar_contexto("matutino")  # ocupado 2026-11-30 09:00-10:00
    casos = [
        bloco("b_inicio", date(2026, 11, 30), time(8, 45), time(9, 10)),
        bloco("b_dentro", date(2026, 11, 30), time(9, 15), time(9, 40)),
        bloco("b_fim", date(2026, 11, 30), time(9, 50), time(10, 15)),
        bloco("b_envolve", date(2026, 11, 30), time(8, 50), time(10, 10)),  # 80 min: envolve 09:00-10:00 sem sobrecarga
    ]
    for b in casos:
        res = validar(proposta_com(ctx, b), ctx)
        assert res.status == "REPROVADO"
        assert len(res.violacoes) == 1
        assert res.violacoes[0].regra == REGRA_CONFLITO_AGENDA and res.violacoes[0].bloco_id == b.id


def test_conflito_agenda_eventos_sobrepostos_no_google_agenda_nao_duplicam_violacao():
    ctx = carregar_contexto("matutino").model_copy(
        update={
            "ocupados": [
                Janela(dia=date(2026, 11, 30), inicio=time(9, 0), fim=time(10, 0)),
                Janela(dia=date(2026, 11, 30), inicio=time(9, 30), fim=time(10, 30)),
            ]
        }
    )
    p = proposta_com(ctx, bloco("b1", date(2026, 11, 30), time(9, 15), time(9, 45)))
    violacoes = verificar_conflito_agenda(p, ctx)
    assert len(violacoes) == 1
    assert violacoes[0].regra == REGRA_CONFLITO_AGENDA and "09:00 às 10:30" in violacoes[0].mensagem


def test_conflito_agenda_reprova_compromisso_novo_vindo_do_provedor_google_agenda():
    ctx = carregar_contexto("matutino")
    proposta = carregar_proposta("valida")  # b1 fica em 2026-11-30 08:00-08:25
    agenda = AgendaGoogleFake([Janela(dia=date(2026, 11, 30), inicio=time(8, 0), fim=time(8, 30))])

    res = AgenteValidation(provedor_agenda=agenda).validar(proposta, ctx)
    assert agenda.consultas == [(date(2026, 11, 30), date(2026, 12, 1))]
    assert res.status == "REPROVADO"
    assert len(res.violacoes) == 1
    assert res.violacoes[0].regra == REGRA_CONFLITO_AGENDA and res.violacoes[0].bloco_id == "b1"


def test_conflito_agenda_reprova_jornada_clt_na_fixture_agenda_cheia():
    ctx = carregar_contexto("agenda_cheia")  # ocupado 08:00-17:00
    p = proposta_com(ctx, bloco("b1", date(2026, 11, 30), time(10, 0), time(10, 25)))
    res = validar(p, ctx)
    assert res.status == "REPROVADO"
    assert res.violacoes[0].regra == REGRA_CONFLITO_AGENDA and res.violacoes[0].bloco_id == "b1"


# ---------------------------------------------------------------- INTEGRIDADE_CIRCADIANA (aprova e reprova)
def test_integridade_circadiana_aprova_alta_fora_das_janelas_e_baixa_em_higiene_e_vale():
    # agenda_cheia: sono começa 22:30 (higiene 21:30-22:30), vale 21:00-22:00, pico 19:00-20:30
    ctx = carregar_contexto("agenda_cheia")
    p = proposta_com(
        ctx,
        bloco("b_pico", date(2026, 11, 30), time(19, 0), time(19, 25), carga="alta"),
        # Alta carga imediatamente antes da higiene do sono (21:00-21:30 seria neutro se não fosse vale;
        # 20:30-21:00 é neutro e fora da higiene 21:30-22:30)
        bloco("b_neutro", date(2026, 11, 30), time(20, 30), time(20, 55), carga="alta"),
        # Baixa carga na higiene do sono e no vale é permitida
        bloco("b_baixa_higiene", date(2026, 11, 30), time(21, 30), time(21, 55), carga="baixa", disciplina="Inglês"),
    )
    assert verificar_integridade_circadiana(p, ctx) == []
    assert validar(p, ctx).status == "APROVADO"


def test_integridade_circadiana_reprova_bloco_em_janela_de_sono():
    ctx_mat = carregar_contexto("matutino")  # sono 22:00-23:59 e 00:00-06:00
    p_mat = proposta_com(
        ctx_mat,
        bloco("b_noite", date(2026, 11, 30), time(22, 30), time(22, 55), carga="alta"),
        bloco("b_madrugada", date(2026, 12, 1), time(5, 30), time(5, 55), carga="baixa"),
    )
    res_mat = validar(p_mat, ctx_mat)
    assert res_mat.status == "REPROVADO"
    assert [(v.regra, v.bloco_id) for v in res_mat.violacoes] == [
        (REGRA_INTEGRIDADE_CIRCADIANA, "b_noite"),
        (REGRA_INTEGRIDADE_CIRCADIANA, "b_madrugada"),
    ]

    ctx_not = carregar_contexto("noturno")  # sono 02:00-10:00
    p_not = proposta_com(ctx_not, bloco("b_sono_noturno", date(2026, 11, 30), time(3, 0), time(3, 25), carga="alta"))
    res_not = validar(p_not, ctx_not)
    assert res_not.status == "REPROVADO" and res_not.violacoes[0].regra == REGRA_INTEGRIDADE_CIRCADIANA


def test_integridade_circadiana_reprova_alta_carga_em_higiene_do_sono_nos_cronotipos():
    # Matutino: sono 22:00 -> higiene 21:00-22:00
    ctx_mat = carregar_contexto("matutino")
    p_mat = proposta_com(
        ctx_mat,
        bloco("b_ok", date(2026, 11, 30), time(20, 30), time(21, 0), carga="alta"),
        bloco("b_higiene", date(2026, 11, 30), time(21, 15), time(21, 40), carga="alta"),
    )
    res_mat = validar(p_mat, ctx_mat)
    assert res_mat.status == "REPROVADO"
    assert len(res_mat.violacoes) == 1
    assert res_mat.violacoes[0].bloco_id == "b_higiene"
    assert "higiene do sono" in res_mat.violacoes[0].mensagem

    # Vespertino: sono 23:30 -> higiene 22:30-23:30
    ctx_vesp = carregar_contexto("vespertino")
    p_vesp = proposta_com(ctx_vesp, bloco("b_vesp", date(2026, 11, 30), time(22, 45), time(23, 10), carga="alta"))
    res_vesp = validar(p_vesp, ctx_vesp)
    assert res_vesp.status == "REPROVADO" and "higiene do sono" in res_vesp.violacoes[0].mensagem

    # Noturno: sono 02:00 -> higiene 01:00-02:00
    ctx_not = carregar_contexto("noturno")
    p_not = proposta_com(ctx_not, bloco("b_not", date(2026, 11, 30), time(1, 15), time(1, 40), carga="alta"))
    res_not = validar(p_not, ctx_not)
    assert res_not.status == "REPROVADO" and "higiene do sono" in res_not.violacoes[0].mensagem


def test_higiene_do_sono_cruza_meia_noite_para_sono_logo_apos_00h():
    # Estudante dorme das 00:30 às 08:30 na terça -> higiene 1h antes cobre segunda 23:30-24:00 e terça 00:00-00:30
    ctx = carregar_contexto("noturno").model_copy(
        update={"sono": [Janela(dia=date(2026, 12, 1), inicio=time(0, 30), fim=time(8, 30))]}
    )
    p = proposta_com(
        ctx,
        bloco("b_vespera", date(2026, 11, 30), time(23, 35), time(23, 55), carga="alta"),
        bloco("b_madrugada", date(2026, 12, 1), time(0, 0), time(0, 25), carga="alta"),
    )
    res = validar(p, ctx)
    assert res.status == "REPROVADO"
    assert [v.bloco_id for v in res.violacoes] == ["b_vespera", "b_madrugada"]
    assert all(v.regra == REGRA_INTEGRIDADE_CIRCADIANA and "higiene do sono" in v.mensagem for v in res.violacoes)


def test_bloco_cruzando_higiene_e_sono_nao_duplica_violacao():
    ctx = carregar_contexto("matutino")  # higiene 21:00-22:00, sono 22:00-23:59
    p = proposta_com(ctx, bloco("b_cruza", date(2026, 11, 30), time(21, 45), time(22, 10), carga="alta"))
    res = validar(p, ctx)
    assert len(res.violacoes) == 1
    assert "janela de sono" in res.violacoes[0].mensagem


def test_integridade_circadiana_reprova_bloco_em_janela_de_refeicao():
    ctx = carregar_contexto("matutino")  # refeições: 12:00-13:00 e 19:00-20:00
    p = proposta_com(
        ctx,
        bloco("b_almoco", date(2026, 11, 30), time(12, 15), time(12, 40), carga="alta"),
        bloco("b_jantar", date(2026, 11, 30), time(19, 30), time(19, 55), carga="alta"),
        # Imediatamente após o almoço (13:00-13:25, baixa carga): sem conflito de refeição
        bloco("b_pos_almoco", date(2026, 11, 30), time(13, 0), time(13, 25), carga="baixa"),
    )
    res = validar(p, ctx)
    assert res.status == "REPROVADO"
    assert [v.bloco_id for v in res.violacoes] == ["b_almoco", "b_jantar"]
    assert all(v.regra == REGRA_INTEGRIDADE_CIRCADIANA and "refeição" in v.mensagem for v in res.violacoes)


# ---------------------------------------------------------------- SOBRECARGA (diária, bloco contínuo e corte por check-in)
def _blocos_200min_com_pausas(dia: date) -> list[BlocoEstudo]:
    """4 blocos de 50 min espaçados com pausas (total 200 min/dia, contínuo máx 50 min), fora de ocupados/refeições."""
    return [
        bloco("b1", dia, time(7, 0), time(7, 50), carga="alta"),
        bloco("b2", dia, time(8, 0), time(8, 50), carga="alta"),
        bloco("b3", dia, time(10, 0), time(10, 50), carga="alta"),
        bloco("b4", dia, time(15, 0), time(15, 50), carga="baixa", disciplina="História"),
    ]


def test_sobrecarga_aprova_dentro_dos_limiares_diario_e_continuo():
    ctx = carregar_contexto("matutino")  # check-in normal: 240 min/dia, 90 min contínuo
    p = proposta_com(ctx, *_blocos_200min_com_pausas(date(2026, 11, 30)))

    assert verificar_sobrecarga(p, ctx) == []
    assert validar(p, ctx).status == "APROVADO"


def test_sobrecarga_reprova_carga_diaria_acima_do_limiar():
    ctx = carregar_contexto("matutino")  # limite normal: 240 min/dia
    dia = date(2026, 11, 30)
    blocos = [
        *_blocos_200min_com_pausas(dia),
        bloco("b5", dia, time(16, 0), time(16, 50), carga="baixa", disciplina="Inglês"),  # total = 250 min
    ]
    res = validar(proposta_com(ctx, *blocos), ctx)
    assert res.status == "REPROVADO"
    assert len(res.violacoes) == 1
    v = res.violacoes[0]
    assert v.regra == REGRA_SOBRECARGA and v.bloco_id is None and v.dia == dia and v.excesso_min == 10


def test_sobrecarga_reprova_bloco_continuo_acima_do_limiar():
    ctx = carregar_contexto("matutino")  # limite contínuo normal: 90 min
    dia = date(2026, 12, 1)

    # 1) Único bloco contínuo de 105 min (> 90 min), embora abaixo da carga diária (240 min)
    p_unico = proposta_com(ctx, bloco("b_longo", dia, time(7, 0), time(8, 45), carga="alta"))
    res_unico = validar(p_unico, ctx)
    assert res_unico.status == "REPROVADO"
    assert len(res_unico.violacoes) == 1
    assert (
        res_unico.violacoes[0].regra == REGRA_SOBRECARGA
        and res_unico.violacoes[0].bloco_id == "b_longo"
        and res_unico.violacoes[0].excesso_min == 15
    )

    # 2) Dois blocos colados sem pausa (07:00-07:50 e 07:50-08:40 = 100 min ininterruptos > 90 min)
    p_colados = proposta_com(
        ctx,
        bloco("b_a", dia, time(7, 0), time(7, 50), carga="alta"),
        bloco("b_b", dia, time(7, 50), time(8, 40), carga="alta"),
    )
    res_colados = validar(p_colados, ctx)
    assert res_colados.status == "REPROVADO"
    assert len(res_colados.violacoes) == 1
    assert (
        res_colados.violacoes[0].regra == REGRA_SOBRECARGA
        and res_colados.violacoes[0].bloco_id is None
        and res_colados.violacoes[0].excesso_min == 10
    )


def test_sobrecarga_corte_automatico_com_fixture_estresse_alto():
    """Critério de aceite: com a fixture de estresse alto (`fadiga.json`), o limiar cai 30% automaticamente."""
    ctx_normal = carregar_contexto("matutino")  # estresse=2, horas_sono=7 -> 240 min/dia, 90 min contínuo
    ctx_fadiga = carregar_contexto("fadiga")    # estresse=5, horas_sono=4 -> corte de 30%: 168 min/dia, 63 min contínuo

    lim_fadiga = calcular_limiares(ctx_fadiga.checkin)
    assert lim_fadiga.percentual_corte_aplicado == 0.30
    assert lim_fadiga.carga_max_diaria_min == 168
    assert lim_fadiga.bloco_continuo_max_min == 63

    # 200 min/dia (4x50 min com pausas): aprovado no perfil normal, reprovado por corte de 30% em fadiga
    dia = date(2026, 11, 30)
    blocos_200 = _blocos_200min_com_pausas(dia)
    assert validar(proposta_com(ctx_normal, *blocos_200), ctx_normal).status == "APROVADO"

    res_fadiga = validar(proposta_com(ctx_fadiga, *blocos_200), ctx_fadiga)
    assert res_fadiga.status == "REPROVADO"
    assert len(res_fadiga.violacoes) == 1
    v = res_fadiga.violacoes[0]
    assert v.regra == REGRA_SOBRECARGA and v.bloco_id is None and v.excesso_min == 32
    assert "30%" in v.mensagem and "estresse alto" in v.mensagem

    # Bloco contínuo de 75 min: aprovado no perfil normal (<= 90), reprovado em fadiga (> 63, excesso 12)
    b75 = bloco("b_75", date(2026, 12, 1), time(7, 0), time(8, 15), carga="alta")
    assert validar(proposta_com(ctx_normal, b75), ctx_normal).status == "APROVADO"
    res_b75 = validar(proposta_com(ctx_fadiga, b75), ctx_fadiga)
    assert res_b75.status == "REPROVADO"
    assert res_b75.violacoes[0].regra == REGRA_SOBRECARGA and res_b75.violacoes[0].excesso_min == 12


def test_sobrecarga_corte_proporcional_por_estresse_ou_privacao_de_sono():
    lim_energia = calcular_limiares(carregar_contexto("alta_energia").checkin)
    assert lim_energia.percentual_corte_aplicado == 0.0 and lim_energia.carga_max_diaria_min == 240

    # Sinal moderado isolado (estresse 4 ou sono 5.5h) -> metade do teto de corte (15%)
    lim_estresse4 = calcular_limiares(CheckIn(energia=3, horas_sono=7.0, estresse=4))
    assert lim_estresse4.percentual_corte_aplicado == 0.15 and lim_estresse4.carga_max_diaria_min == 204

    lim_sono55 = calcular_limiares(CheckIn(energia=3, horas_sono=5.5, estresse=2))
    assert lim_sono55.percentual_corte_aplicado == 0.15 and lim_sono55.carga_max_diaria_min == 204

    # Sinal severo isolado (estresse 5 ou sono < 5h) ou combinação -> corte total (30%)
    lim_sono45 = calcular_limiares(CheckIn(energia=2, horas_sono=4.5, estresse=2))
    assert lim_sono45.percentual_corte_aplicado == 0.30 and lim_sono45.carga_max_diaria_min == 168


def test_sobrecarga_reprova_dia_com_6h_seguidas_de_estudo_noturno():
    """Critério de aceite: um dia com 6h seguidas de estudo noturno é reprovado por SOBRECARGA."""
    dia = date(2026, 12, 2)  # quarta-feira (mesmo dia da fixture resultado/sobrecarga.json)
    blocos_6h_noturno = [
        bloco("n1", dia, time(18, 0), time(19, 0), carga="alta").model_copy(update={"pausa_min": 0}),
        bloco("n2", dia, time(19, 0), time(20, 0), carga="alta").model_copy(update={"pausa_min": 0}),
        bloco("n3", dia, time(20, 0), time(21, 0), carga="alta").model_copy(update={"pausa_min": 0}),
        bloco("n4", dia, time(21, 0), time(22, 0), carga="alta").model_copy(update={"pausa_min": 0}),
        bloco("n5", dia, time(22, 0), time(23, 0), carga="alta").model_copy(update={"pausa_min": 0}),
        BlocoEstudo(
            id="n6",
            dia=dia,
            inicio=time(23, 0),
            fim=time(23, 59),
            disciplina="Cálculo I",
            material_id="calc-01",
            carga="alta",
            tecnica="Pomodoro",
            foco_min=60,
            pausa_min=0,
        ),
    ]

    # 1) Mesmo em contexto noturno (sono só 02:00-10:00, sem refeição no período), SOBRECARGA reprova sozinha
    ctx_noturno_sem_jantar = carregar_contexto("noturno").model_copy(update={"refeicoes": []})
    res_not = validar(proposta_com(ctx_noturno_sem_jantar, *blocos_6h_noturno), ctx_noturno_sem_jantar)
    assert res_not.status == "REPROVADO"
    assert all(v.regra == REGRA_SOBRECARGA for v in res_not.violacoes)
    assert any(v.dia == dia and v.bloco_id is None and v.excesso_min == 120 for v in res_not.violacoes)
    assert any(v.dia == dia and v.excesso_min == 270 for v in res_not.violacoes)

    # 2) No perfil matutino, 6h noturnas seguidas violam tanto SOBRECARGA (excesso 120 min) quanto INTEGRIDADE_CIRCADIANA
    ctx_mat = carregar_contexto("matutino")
    res_mat = validar(proposta_com(ctx_mat, *blocos_6h_noturno), ctx_mat)
    assert res_mat.status == "REPROVADO"
    regras = {v.regra for v in res_mat.violacoes}
    assert {REGRA_SOBRECARGA, REGRA_INTEGRIDADE_CIRCADIANA} <= regras


def test_limiares_validation_configuraveis_em_config_py(monkeypatch):
    monkeypatch.setenv("VALIDATION_CARGA_MAX_DIARIA_MIN", "180")
    monkeypatch.setenv("VALIDATION_BLOCO_CONTINUO_MAX_MIN", "60")
    monkeypatch.setenv("VALIDATION_PERCENTUAL_CORTE", "0.25")
    monkeypatch.setenv("VALIDATION_MARGEM_SONO_MIN", "90")

    s = Settings()
    assert s.validation_carga_max_diaria_min == 180
    assert s.validation_bloco_continuo_max_min == 60
    assert s.validation_percentual_corte == 0.25
    assert s.validation_margem_sono_min == 90

    # Confirma que a margem de sono de config.py é aplicada dinamicamente em validation.py
    monkeypatch.setattr(validation.settings, "validation_margem_sono_min", 90)
    ctx = carregar_contexto("matutino")  # sono 22:00 -> com margem 90 min, higiene começa às 20:30
    p = proposta_com(ctx, bloco("b_margem", date(2026, 11, 30), time(20, 40), time(21, 0), carga="alta"))
    res = validar(p, ctx)
    assert res.status == "REPROVADO" and "90 min antes de dormir" in res.violacoes[0].mensagem


# ---------------------------------------------------------------- zero chamadas a LLM (critério de aceite)
def test_validation_faz_zero_chamadas_a_llm(monkeypatch):
    chamadas = []

    def bloquear_llm(*args, **kwargs):
        chamadas.append((args, kwargs))
        raise AssertionError("Validation é determinístico e nunca pode chamar LLM")

    for fabrica in ("gerador", "triagem", "guardrails", "guardrails_fallback"):
        monkeypatch.setattr(llm, fabrica, bloquear_llm)

    # Garante também que o módulo não importa nem referencia factories/bibliotecas de LLM
    fonte = inspect.getsource(validation)
    for proibido in ("langchain_ollama", "ChatOllama", "ollama", "modules.rag.llm"):
        assert proibido not in fonte

    ctx_mat = carregar_contexto("matutino")
    ctx_fad = carregar_contexto("fadiga")
    assert validar(carregar_proposta("valida"), ctx_mat).status == "APROVADO"
    assert validar(carregar_proposta("violacoes"), ctx_mat).status == "REPROVADO"
    assert validar(proposta_com(ctx_fad, *_blocos_200min_com_pausas(date(2026, 11, 30))), ctx_fad).status == "REPROVADO"
    assert chamadas == []
