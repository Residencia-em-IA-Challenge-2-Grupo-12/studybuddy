"""Testes do Validation determinístico (`CONFLITO_AGENDA` e `INTEGRIDADE_CIRCADIANA`).

Usam as fixtures de `api/tests/fixtures/` e garantem zero chamadas a LLM. Rodam no CI.
Rodar (a partir de api/): python -m pytest -q
"""

import inspect
from datetime import date, time
from pathlib import Path

from app.modules.agentes import validation
from app.modules.agentes.contratos import (
    BlocoEstudo,
    ContextoEstudante,
    Janela,
    PropostaGrade,
    ResultadoValidacao,
)
from app.modules.agentes.validation import (
    REGRA_CONFLITO_AGENDA,
    REGRA_INTEGRIDADE_CIRCADIANA,
    AgenteValidation,
    validar,
    verificar_conflito_agenda,
    verificar_integridade_circadiana,
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
    assert res == esperado
    assert res.status == "REPROVADO"
    assert [(v.regra, v.bloco_id) for v in res.violacoes] == [
        (REGRA_CONFLITO_AGENDA, "b1"),
        (REGRA_INTEGRIDADE_CIRCADIANA, "b2"),
        (REGRA_INTEGRIDADE_CIRCADIANA, "b3"),
    ]


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
    p = proposta_com(
        ctx,
        bloco("b_inicio", date(2026, 11, 30), time(8, 45), time(9, 10)),
        bloco("b_dentro", date(2026, 11, 30), time(9, 15), time(9, 40)),
        bloco("b_fim", date(2026, 11, 30), time(9, 50), time(10, 15)),
        bloco("b_envolve", date(2026, 11, 30), time(8, 30), time(10, 30)),
    )
    res = validar(p, ctx)
    assert res.status == "REPROVADO"
    assert [v.bloco_id for v in res.violacoes] == ["b_inicio", "b_dentro", "b_fim", "b_envolve"]
    assert all(v.regra == REGRA_CONFLITO_AGENDA for v in res.violacoes)


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

    ctx = carregar_contexto("matutino")
    assert validar(carregar_proposta("valida"), ctx).status == "APROVADO"
    assert validar(carregar_proposta("violacoes"), ctx).status == "REPROVADO"
    assert chamadas == []
