"""Analysis Agent ([3.x]) sobre as fixtures. Sem LLM: rodam no CI."""

from datetime import date, time
from pathlib import Path

import pytest

from app.modules.agentes.analysis import AgenteAnalysis
from app.modules.agentes.analysis import invariantes as inv
from app.modules.agentes.analysis.janelas import subtrair, unir
from app.modules.agentes.contratos import ContextoEstudante, PropostaGrade

FIXTURES = Path(__file__).parent / "fixtures"
CONTEXTOS = sorted(p.stem for p in (FIXTURES / "contexto").glob("*.json"))


def contexto(nome: str) -> ContextoEstudante:
    return ContextoEstudante.model_validate_json((FIXTURES / "contexto" / f"{nome}.json").read_text(encoding="utf-8"))


def proposta(nome: str) -> PropostaGrade:
    return PropostaGrade.model_validate_json((FIXTURES / "proposta" / f"{nome}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- intervalos
def test_unir_e_subtrair():
    assert unir([(60, 120), (0, 30), (100, 200)]) == [(0, 30), (60, 200)]
    assert subtrair([(0, 600)], [(60, 120), (300, 400)]) == [(0, 60), (120, 300), (400, 600)]
    assert subtrair([(0, 60)], [(0, 60)]) == []


# ---------------------------------------------------------------- [3.1] critérios de aceite
@pytest.mark.parametrize("nome", CONTEXTOS)
def test_proposta_respeita_as_regras(nome):
    ctx = contexto(nome)
    p = AgenteAnalysis().propor(ctx)
    assert p.blocos, "toda fixture tem tempo livre: a grade não pode sair vazia"
    assert inv.todas(p, ctx) == {}  # sem alta carga em vale, nada fora dos livres, nada após prazo, sem sobreposição


@pytest.mark.parametrize("nome", CONTEXTOS)
def test_proposta_valida_no_contrato(nome):
    p = AgenteAnalysis().propor(contexto(nome))
    assert PropostaGrade.model_validate_json(p.model_dump_json()) == p


def test_alta_carga_prefere_o_pico():
    ctx = contexto("matutino")
    picos = {(j.dia, j.inicio, j.fim) for j in ctx.picos}
    alta = [b for b in AgenteAnalysis().propor(ctx).blocos if b.carga == "alta"]
    no_pico = [b for b in alta if any(d == b.dia and i <= b.inicio and b.fim <= f for d, i, f in picos)]
    assert len(no_pico) / len(alta) >= 0.8


def test_baixa_carga_vai_para_o_vale():
    ctx = contexto("matutino")
    baixa = [b for b in AgenteAnalysis().propor(ctx).blocos if b.carga == "baixa"]
    assert all(time(13) <= b.inicio < time(15) for b in baixa)  # vale pós-almoço da fixture


def test_materia_se_espalha_pela_semana():
    calc = [b for b in AgenteAnalysis().propor(contexto("matutino")).blocos if b.material_id == "calc-01"]
    assert len({b.dia for b in calc}) >= 3


def test_deterministico():
    ctx = contexto("vespertino")
    assert AgenteAnalysis().propor(ctx) == AgenteAnalysis().propor(ctx)


def test_sem_espaco_vai_para_fora_da_grade():
    ctx = contexto("agenda_cheia")
    ctx.materiais[0].horas_estimadas = 40  # muito mais que as noites livres
    p = AgenteAnalysis().propor(ctx)
    assert ctx.materiais[0].id in p.fora_da_grade
    assert inv.todas(p, ctx) == {}


def test_prazo_antes_da_semana_nao_agenda():
    ctx = contexto("matutino")
    ctx.materiais[0].prazo = date(2026, 11, 1)
    p = AgenteAnalysis().propor(ctx)
    assert ctx.materiais[0].id in p.fora_da_grade
    assert all(b.material_id != ctx.materiais[0].id for b in p.blocos)


# ---------------------------------------------------------------- invariantes acusam a fixture plantada
def test_invariantes_acham_as_violacoes_plantadas():
    achados = inv.todas(proposta("violacoes"), contexto("matutino"))
    assert achados["fora_dos_livres"] == ["b1", "b3"]   # aula de segunda 9h e horário de sono
    assert achados["alta_em_vale"] == ["b2"]


def test_proposta_valida_passa_nos_invariantes():
    assert inv.todas(proposta("valida"), contexto("matutino")) == {}
