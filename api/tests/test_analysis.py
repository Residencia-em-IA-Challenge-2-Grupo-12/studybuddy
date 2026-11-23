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


# ---------------------------------------------------------------- [3.2] Pomodoro adaptativo e prioridade
from app.modules.agentes.analysis import prioridade  # noqa: E402
from app.modules.agentes.analysis.pomodoro import ritmo  # noqa: E402
from app.modules.agentes.contratos import DiretivaMaestro  # noqa: E402

REDUCAO = DiretivaMaestro(intencao="planejar a semana", rota="reducao_danos")


@pytest.mark.parametrize("indice,esperado", [(0.95, (50, 10)), (0.7, (50, 10)), (0.6, (25, 5)),
                                             (0.4, (25, 5)), (0.39, (25, 10)), (0.0, (25, 10))])
def test_tabela_do_pomodoro(indice, esperado):
    r = ritmo(indice)
    assert (r.foco_min, r.pausa_min) == esperado


def test_fadiga_e_alta_energia_geram_blocos_de_tamanhos_diferentes():
    fadiga, energia = AgenteAnalysis().propor(contexto("fadiga")), AgenteAnalysis().propor(contexto("alta_energia"))
    assert {b.foco_min for b in fadiga.blocos} == {25} and {b.pausa_min for b in fadiga.blocos} == {10}
    assert {b.foco_min for b in energia.blocos} == {50} and {b.pausa_min for b in energia.blocos} == {10}


def test_material_com_prazo_em_2_dias_e_agendado_antes_do_prazo():
    ctx = contexto("prazo_apertado")
    fis = next(m for m in ctx.materiais if m.id == "fis-01")
    assert (fis.prazo - ctx.semana_inicio).days == 2
    p = AgenteAnalysis().propor(ctx)
    blocos_fis = [b for b in p.blocos if b.material_id == "fis-01"]
    assert "fis-01" not in p.fora_da_grade
    assert len(blocos_fis) == prioridade.blocos(fis, 25, ctx.semana_inicio)  # todos os blocos, com os extras
    assert all(b.dia < fis.prazo for b in blocos_fis)


def test_urgente_pega_os_picos_antes_dos_outros():
    ctx = contexto("prazo_apertado")
    fis = next(m for m in ctx.materiais if m.id == "fis-01")
    picos = [(j.dia, j.inicio, j.fim) for j in ctx.picos if j.dia < fis.prazo]
    no_pico = [b for b in AgenteAnalysis().propor(ctx).blocos
               if any(d == b.dia and i <= b.inicio and b.fim <= f for d, i, f in picos)]
    assert no_pico and {b.material_id for b in no_pico} == {"fis-01"}  # os picos antes da prova são da física


def test_ordem_por_prazo_e_dificuldade():
    ctx = contexto("prazo_apertado")
    ids = [m.id for m in prioridade.ordenar(ctx.materiais, ctx.semana_inicio)]
    assert ids[:2] == ["fis-01", "calc-01"]          # prazos de 2 e 4 dias
    assert ids[2:] == ["prog-01", "hist-01", "ing-01"]  # sem prazo: dificuldade 3, 2, 1


def test_mais_dificil_ganha_mais_blocos():
    ctx = contexto("matutino")
    calc, prog = (next(m for m in ctx.materiais if m.id == i) for i in ("calc-01", "prog-01"))
    assert prioridade.blocos(calc, 25, ctx.semana_inicio) == 10 + 1  # 4h, dificuldade 4
    assert prioridade.blocos(prog, 25, ctx.semana_inicio) == 8       # 3h, dificuldade 3, sem prazo


def test_reducao_de_danos_gera_um_dia_mais_leve():
    ctx = contexto("fadiga")
    normal, leve = AgenteAnalysis().propor(ctx), AgenteAnalysis().propor(ctx, REDUCAO)
    assert leve.modo == "reducao_danos"
    assert all(b.carga == "baixa" for b in leve.blocos)
    assert {"calc-01", "prog-01"} <= set(leve.fora_da_grade)
    assert all(b.pausa_min == 15 for b in leve.blocos)
    por_dia = {}
    for b in leve.blocos:
        por_dia[b.dia] = por_dia.get(b.dia, 0) + 1
    assert max(por_dia.values()) <= 3
    assert len(leve.blocos) < len(normal.blocos)
    assert inv.todas(leve, ctx) == {}


@pytest.mark.parametrize("nome", CONTEXTOS)
def test_reducao_de_danos_respeita_as_regras(nome):
    ctx = contexto(nome)
    assert inv.todas(AgenteAnalysis().propor(ctx, REDUCAO), ctx) == {}


# ---------------------------------------------------------------- [3.3] Reajuste a partir das violações
from collections import Counter  # noqa: E402

from app.modules.agentes.contratos import ResultadoValidacao, Violacao  # noqa: E402


def resultado(nome: str) -> ResultadoValidacao:
    return ResultadoValidacao.model_validate_json((FIXTURES / "resultado" / f"{nome}.json").read_text(encoding="utf-8"))


def foco_no_dia(p: PropostaGrade, dia) -> int:
    return sum(b.foco_min for b in p.blocos if b.dia == dia)


def test_reajuste_remove_as_violacoes_plantadas_sem_criar_outras():
    ctx, antes = contexto("matutino"), proposta("violacoes")
    assert inv.todas(antes, ctx)  # a fixture começa errada
    depois = AgenteAnalysis().reajustar(antes, resultado("reprovado").violacoes, ctx)
    assert inv.todas(depois, ctx) == {}
    assert PropostaGrade.model_validate_json(depois.model_dump_json()) == depois
    assert depois.iteracao == antes.iteracao + 1


def test_reajuste_mexe_so_no_que_foi_apontado():
    ctx, antes = contexto("matutino"), proposta("violacoes")
    depois = AgenteAnalysis().reajustar(antes, resultado("reprovado").violacoes, ctx)
    ids = {b.id for b in depois.blocos}
    assert {"b1", "b2", "b3"}.isdisjoint(ids)
    b4 = next(b for b in antes.blocos if b.id == "b4")
    assert b4 in depois.blocos  # intacto: mesmo dia, horário e conteúdo
    novos = [b for b in depois.blocos if b.id.startswith("r1-")]
    assert Counter(b.material_id for b in novos) == Counter({"calc-01": 2, "prog-01": 1})
    saidos = {(b.dia, b.inicio) for b in antes.blocos if b.id in {"b1", "b2", "b3"}}
    assert all((b.dia, b.inicio) not in saidos for b in novos)  # não volta para o horário reprovado


def test_reajuste_sem_violacoes_nao_mexe_nos_blocos():
    ctx = contexto("matutino")
    p = AgenteAnalysis().propor(ctx)
    assert AgenteAnalysis().reajustar(p, [], ctx).blocos == p.blocos


def test_sobrecarga_corta_o_excesso_e_nao_sobrecarrega_outro_dia():
    ctx = contexto("matutino")
    antes = AgenteAnalysis().propor(ctx)
    v = resultado("sobrecarga").violacoes[0]  # quarta-feira, excesso de 120 min
    depois = AgenteAnalysis().reajustar(antes, [v], ctx)
    assert foco_no_dia(depois, v.dia) <= foco_no_dia(antes, v.dia) - v.excesso_min
    assert not any(b.id.startswith("r1-") and b.dia == v.dia for b in depois.blocos)  # nada novo no dia cortado
    limite = sum(1 for b in depois.blocos if b.dia == v.dia)
    for dia in {b.dia for b in depois.blocos if b.id.startswith("r1-")}:
        assert sum(1 for b in depois.blocos if b.dia == dia) <= limite
    assert inv.todas(depois, ctx) == {}


def test_sobrecarga_corta_primeiro_o_menos_prioritario():
    ctx = contexto("matutino")
    antes = AgenteAnalysis().propor(ctx)
    v = Violacao(regra="SOBRECARGA", dia=ctx.semana_inicio, mensagem="excesso", excesso_min=25)
    depois = AgenteAnalysis().reajustar(antes, [v], ctx)
    cortado = ({b.id for b in antes.blocos} - {b.id for b in depois.blocos}).pop()
    assert next(b for b in antes.blocos if b.id == cortado).material_id == "ing-01"  # sem prazo, dificuldade 1


def test_sem_como_resolver_reduz_a_carga_e_diz_o_que_ficou_de_fora():
    ctx = contexto("agenda_cheia")
    for m in ctx.materiais:
        m.horas_estimadas = 40  # lota todas as janelas
    antes = AgenteAnalysis().propor(ctx)
    alvo = antes.blocos[0]
    v = Violacao(regra="CONFLITO_AGENDA", dia=alvo.dia, bloco_id=alvo.id, mensagem="conflito")
    depois = AgenteAnalysis().reajustar(antes, [v], ctx)
    assert len(depois.blocos) == len(antes.blocos) - 1
    assert alvo.material_id in depois.fora_da_grade
    assert inv.todas(depois, ctx) == {}


def test_violacao_sem_bloco_usa_os_invariantes_do_dia():
    ctx, antes = contexto("matutino"), proposta("violacoes")
    b2 = next(b for b in antes.blocos if b.id == "b2")
    v = Violacao(regra="INTEGRIDADE_CIRCADIANA", dia=b2.dia, mensagem="alta carga no vale")
    depois = AgenteAnalysis().reajustar(antes, [v], ctx)
    assert "b2" not in {b.id for b in depois.blocos}
    assert {"b1", "b3", "b4"} <= {b.id for b in depois.blocos}  # outros dias não foram apontados
