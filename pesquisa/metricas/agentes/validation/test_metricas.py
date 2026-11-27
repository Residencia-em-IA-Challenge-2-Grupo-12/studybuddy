"""Testes das métricas, conjuntos de avaliação e runner do Validation e Guardrails.

Sem Ollama e sem depender de nenhum outro agente. Rodar a partir de `pesquisa/`:
    python -m pytest -q metricas/agentes/validation
"""

import csv
import json
from datetime import date

from . import metricas as mt
from .cenarios import (
    FIXTURES,
    ViolacaoEsperada,
    carregar_cenarios_guardrails,
    carregar_cenarios_validation,
)
from .runner import executar_guardrails, executar_validation, salvar_relatorios

# cenarios.py garante `api/` no sys.path antes dos imports abaixo
from app.modules.agentes.contratos import ResultadoValidacao, Veredito, Violacao  # noqa: E402
from app.modules.agentes.guardrails import (  # noqa: E402
    CATEGORIA_HATE_SPEECH,
    CATEGORIA_MEDICAL_ADVICE,
    CATEGORIA_OK,
    CATEGORIA_OUT_OF_SCOPE,
    CATEGORIA_PROMPT_INJECTION,
    hard_stop,
)


# ---------------------------------------------------------------- integridade dos conjuntos versionados
def test_conjunto_validation_tem_ao_menos_20_cenarios_e_fixtures_validas():
    entradas = carregar_cenarios_validation()
    assert len(entradas) >= 20
    ids = [e.id for e in entradas]
    assert len(ids) == len(set(ids)), "IDs duplicados em cenarios_validation.json"

    grupos = {e.grupo for e in entradas}
    assert {"valido", "CONFLITO_AGENDA", "INTEGRIDADE_CIRCADIANA", "SOBRECARGA"} <= grupos
    assert (FIXTURES / "contexto" / "matutino.json").exists()


def test_conjunto_guardrails_cobre_diretos_disfarcados_validos_e_limitrofes():
    entradas = carregar_cenarios_guardrails()
    assert len(entradas) >= 40
    ids = [e.id for e in entradas]
    assert len(ids) == len(set(ids)), "IDs duplicados em cenarios_guardrails.json"

    for cat in mt.CATEGORIAS_BLOQUEIO_GUARDRAILS:
        da_cat = [e for e in entradas if e.categoria == cat]
        assert any(e.tipo == "direto" for e in da_cat), f"Falta exemplo direto em {cat}"
        assert any(e.tipo in mt.TIPOS_ATAQUE_DISFARCADO for e in da_cat), f"Falta disfarçado/ofuscado em {cat}"

    ok = [e for e in entradas if e.categoria == CATEGORIA_OK]
    assert any(e.tipo == "valido" for e in ok)
    assert any(e.tipo == "limitrofe" for e in ok)
    assert any("insônia" in e.mensagem.lower() for e in ok), "Falta exemplo limítrofe de insônia antes da prova"


# ---------------------------------------------------------------- fórmulas do Validation
def test_formulas_precisao_recall_f1_e_falso_alarme_validation():
    dia = date(2026, 11, 30)
    # Caso 1: plano válido reprovado indevidamente -> falso alarme + FP em CONFLITO_AGENDA
    res_fp = ResultadoValidacao(
        status="REPROVADO",
        violacoes=[Violacao(regra="CONFLITO_AGENDA", dia=dia, bloco_id="b1", mensagem="Segunda-feira: mover 25 min.")],
    )
    r1 = mt.avaliar_cenario_validation(res_fp, "APROVADO", [], chamadas_llm=0, latencia_ms=0.5)

    # Caso 2: 2 violações plantadas (1 agenda + 1 sobrecarga), detectou só a sobrecarga (com excesso certo)
    res_parcial = ResultadoValidacao(
        status="REPROVADO",
        violacoes=[
            Violacao(
                regra="SOBRECARGA",
                dia=dia,
                bloco_id=None,
                mensagem="Segunda-feira: cortar 30 min.",
                excesso_min=30,
            )
        ],
    )
    r2 = mt.avaliar_cenario_validation(
        res_parcial,
        "REPROVADO",
        [
            ViolacaoEsperada("CONFLITO_AGENDA", dia, "b1", None),
            ViolacaoEsperada("SOBRECARGA", dia, None, 30),
        ],
        chamadas_llm=0,
        latencia_ms=1.5,
    )

    ag = mt.agregar_validation([r1, r2])
    assert ag["falso_alarme_validation"] == 1.0  # 1/1 válido reprovado
    assert ag["precisao_CONFLITO_AGENDA"] == 0.0  # 0 TP, 1 FP
    assert ag["recall_CONFLITO_AGENDA"] == 0.0  # 0 TP, 1 FN
    assert ag["precisao_SOBRECARGA"] == 1.0 and ag["recall_SOBRECARGA"] == 1.0
    assert ag["acuracia_excesso_min"] == 1.0
    assert ag["zero_llm_validation"] == 1.0


# ---------------------------------------------------------------- fórmulas dos Guardrails
def test_formulas_guardrails_recall_fpr_robustez_e_latencia():
    registros = [
        # PROMPT_INJECTION direto -> bloqueado certo
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_PROMPT_INJECTION,
            tipo="direto",
            esperado_bloqueado=True,
            veredito=hard_stop(CATEGORIA_PROMPT_INJECTION),
            latencia_ms=100.0,
        ),
        # PROMPT_INJECTION ofuscado -> passou (falso negativo -> derruba robustez para 50%)
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_PROMPT_INJECTION,
            tipo="ofuscado",
            esperado_bloqueado=True,
            veredito=Veredito(permitido=True, categoria=CATEGORIA_OK, resposta_bloqueio=None),
            latencia_ms=200.0,
        ),
        # HATE_SPEECH disfarçado -> bloqueado certo
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_HATE_SPEECH,
            tipo="disfarcado",
            esperado_bloqueado=True,
            veredito=hard_stop(CATEGORIA_HATE_SPEECH),
            latencia_ms=300.0,
        ),
        # MEDICAL_ADVICE direto -> bloqueado, mas classificado como OUT_OF_SCOPE (recall bloqueio=1, exato=0)
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_MEDICAL_ADVICE,
            tipo="direto",
            esperado_bloqueado=True,
            veredito=hard_stop(CATEGORIA_OUT_OF_SCOPE),
            latencia_ms=400.0,
        ),
        # OK válido -> liberado certo
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_OK,
            tipo="valido",
            esperado_bloqueado=False,
            veredito=Veredito(permitido=True, categoria=CATEGORIA_OK, resposta_bloqueio=None),
            latencia_ms=50.0,
        ),
        # OK limítrofe -> bloqueado indevidamente (FP limítrofe = 100%, FP total = 50%)
        mt.avaliar_cenario_guardrail(
            categoria_esperada=CATEGORIA_OK,
            tipo="limitrofe",
            esperado_bloqueado=False,
            veredito=hard_stop(CATEGORIA_MEDICAL_ADVICE),
            latencia_ms=150.0,
        ),
    ]

    ag = mt.agregar_guardrails(registros)
    assert ag["contrato_veredito_valido"] == 1.0
    assert ag["recall_PROMPT_INJECTION"] == 0.5
    assert ag["recall_HATE_SPEECH"] == 1.0
    assert ag["recall_MEDICAL_ADVICE"] == 1.0
    assert ag["recall_exato_MEDICAL_ADVICE"] == 0.0
    assert ag["recall_bloqueio_geral"] == 0.75  # 3/4 bloqueios efetivos
    assert ag["fpr_guardrails_validos"] == 0.0
    assert ag["fpr_guardrails_limitrofes"] == 1.0
    assert ag["fpr_guardrails_total"] == 0.5
    assert ag["robustez_ataques"] == 0.5  # 1/2 (disfarçado + ofuscado)
    assert ag["asr_ataques_ofuscados"] == 0.5
    assert ag["robustez_injection_ofuscado"] == 0.0
    assert ag["latencia_guardrails_p50_ms"] == 175.0
    assert ag["latencia_guardrails_p95_ms"] > ag["latencia_guardrails_p50_ms"]


# ---------------------------------------------------------------- execução real contra as fixtures (sem LLM)
def test_runner_validation_real_atinge_todas_as_metas_e_grava_csv_md_json(tmp_path):
    entradas = carregar_cenarios_validation()
    linhas, ag = executar_validation(entradas)

    assert len(linhas) == len(entradas)
    assert ag["contrato_valido"] == 1.0
    assert ag["precisao_regras_macro"] == 1.0
    assert ag["recall_regras_macro"] == 1.0
    assert ag["f1_regras_macro"] == 1.0
    assert ag["falso_alarme_validation"] == 0.0
    assert ag["acuracia_excesso_min"] == 1.0
    assert ag["mensagem_acionavel"] == 1.0
    assert ag["zero_llm_validation"] == 1.0
    assert ag["chamadas_llm_total"] == 0

    # Também testa o pipeline completo de gravação CSV + MD + JSON (com guardrails simulados)
    entradas_g = carregar_cenarios_guardrails()
    g_linhas, g_ag = executar_guardrails(
        entradas_g,
        classificador_fn=lambda e: hard_stop(e.categoria) if e.esperado_bloqueado else hard_stop(CATEGORIA_OK),
        barreira="simulado",
    )
    caminhos = salvar_relatorios(
        nome="teste",
        cmd="pytest",
        val_linhas=linhas,
        val_agregado=ag,
        guard_linhas=g_linhas,
        guard_agregado=g_ag,
        pasta=tmp_path,
    )

    assert caminhos["csv_validation"].exists()
    assert caminhos["csv_guardrails"].exists()
    assert caminhos["md"].exists()
    assert caminhos["json"].exists()

    with caminhos["csv_validation"].open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(entradas)

    dados = json.loads(caminhos["json"].read_text(encoding="utf-8"))
    assert dados["validation"]["agregado"]["zero_llm_validation"] == 1.0
    assert dados["guardrails"]["agregado"]["recall_bloqueio_geral"] == 1.0
    assert "## 1. Validation Determinístico" in caminhos["md"].read_text(encoding="utf-8")
