"""Métricas do Analysis ([3.4]): as fórmulas acusam propostas erradas e o conjunto de avaliação é coerente.
Sem Ollama. Rodar a partir de pesquisa/: python -m pytest -q metricas/agentes"""

from .cenarios import FIXTURES, AgenteAnalysis, carregar, contexto, entradas  # primeiro: põe api/ no sys.path

from app.modules.agentes.contratos import PropostaGrade, ResultadoValidacao  # noqa: E402

from . import metricas as mt  # noqa: E402
from . import regras  # noqa: E402
from .runner import avaliar, tabela_resumo  # noqa: E402


def _fixture(pasta, nome, modelo):
    return modelo.model_validate_json((FIXTURES / pasta / f"{nome}.json").read_text(encoding="utf-8"))


def _matutino():
    return contexto({"id": "t", "contexto": "matutino"})


def test_conjunto_tem_pelo_menos_20_cenarios_com_ids_unicos_e_rotulo():
    cs = carregar()
    assert len(cs) >= 20
    assert len({c["id"] for c in cs}) == len(cs)
    assert all(c.get("esperado") for c in cs)
    assert len(entradas()) == len(cs)  # todos montam a partir das fixtures


def test_todos_os_cenarios_batem_com_o_rotulo():
    falhas = {e.id: linha["erros"] for e in entradas() if not (linha := avaliar(e)[0])["rotulo"]}
    assert falhas == {}


def test_regras_acham_as_mesmas_violacoes_da_fixture_reprovada():
    ctx, p = _matutino(), _fixture("proposta", "violacoes", PropostaGrade)
    achadas = {(v.bloco_id, v.regra) for v in regras.detectar(p, ctx)}
    fixture = {(v.bloco_id, v.regra) for v in _fixture("resultado", "reprovado", ResultadoValidacao).violacoes}
    assert achadas == fixture


def test_proposta_errada_derruba_integridade_e_aderencia():
    ctx, p = _matutino(), _fixture("proposta", "violacoes", PropostaGrade)
    assert mt.integridade(p, ctx) == 0.0
    assert mt.alta_no_vale(p, ctx) == 1
    assert mt.aderencia_circadiana(p, ctx) < 1


def test_reajuste_que_nao_mexe_em_nada_nao_resolve_nada():
    ctx, p = _matutino(), _fixture("proposta", "violacoes", PropostaGrade)
    vs = _fixture("resultado", "reprovado", ResultadoValidacao).violacoes
    assert mt.reajuste(p, p, vs, ctx)["resolvidas"] == 0


def test_sobrecarga_so_conta_se_o_dia_caiu_o_excesso():
    ctx = _matutino()
    p = AgenteAnalysis().propor(ctx)
    v = _fixture("resultado", "sobrecarga", ResultadoValidacao).violacoes[0]
    assert mt.reajuste(p, p, [v], ctx)["resolvidas"] == 0
    assert mt.reajuste(p, AgenteAnalysis().reajustar(p, [v], ctx), [v], ctx)["resolvidas"] == 1


def test_ritmo_errado_e_prazo_descoberto_aparecem():
    ctx = _matutino()
    p = AgenteAnalysis().propor(ctx)
    assert mt.pausas_adequadas(p, [50, 10]) == 0.0
    sem_calc = p.model_copy(update={"blocos": [b for b in p.blocos if b.material_id != "calc-01"]})
    assert mt.cobertura_prazos(sem_calc, ctx, ["calc-01"]) == 0.0
    ok, erros = mt.rotulo(sem_calc, ctx, {"fora_da_grade": ["calc-01"], "prazos_a_tempo": ["calc-01"]})
    assert not ok and len(erros) == 2


def test_ocupacao_fica_entre_0_e_1_e_cresce_com_a_demanda():
    ctx = _matutino()
    leve = mt.ocupacao(AgenteAnalysis().propor(ctx), ctx)
    for m in ctx.materiais:
        m.horas_estimadas *= 3
    assert 0 < leve < mt.ocupacao(AgenteAnalysis().propor(ctx), ctx) <= 1


def test_tabela_resumo_marca_o_que_nao_atingiu():
    tabela = tabela_resumo({"contrato_valido": 1.0, "aderencia_circadiana": 0.5})
    assert "| Validade do contrato | 100% | 100% | sim |" in tabela
    assert "| Aderência circadiana | ≥ 80% | 50% | **não** |" in tabela
