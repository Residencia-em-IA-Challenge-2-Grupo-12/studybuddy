"""Testes unitários das métricas e do conjunto de avaliação do Research Agent ([2.6] Issue #41).
Sem Ollama. Rodar a partir de `pesquisa/`: `python -m pytest -q metricas/agentes/research`."""

from __future__ import annotations

from datetime import time

from .cenarios import carregar, entradas, montar
from . import metricas as mt
from .runner import avaliar, tabela_resumo


def test_conjunto_tem_pelo_menos_20_cenarios_com_ids_unicos_e_rotulo():
    cs = carregar()
    assert len(cs) >= 20
    assert len({c["id"] for c in cs}) == len(cs)
    assert all(c.get("esperado") for c in cs)
    assert len(entradas()) == len(cs)


def test_todos_os_cenarios_batem_com_o_rotulo():
    falhas = {e.id: linha["erros"] for e in entradas() if not (linha := avaliar(e)[0])["rotulo"]}
    assert falhas == {}


def test_contexto_com_pico_ou_capacidade_errada_derruba_metricas():
    e = montar(carregar()[0])  # matutino
    ctx_errado = e.ctx_montado.model_copy(
        update={
            "indice_capacidade": 0.25,
            "picos": [
                j.model_copy(update={"inicio": time(14, 0), "fim": time(16, 0)})
                for j in e.ctx_montado.picos
            ],
        }
    )
    assert mt.precisao_checkin_capacidade(ctx_errado, e.esperado) == 0.0
    assert mt.integridade_circadiana_janelas(ctx_errado, e.esperado) == 0.0


def test_tabela_resumo_formata_metas_atingidas_e_nao_atingidas():
    tabela = tabela_resumo({"contrato_valido": 1.0, "hit_rate": 0.5})
    assert "| Validade do contrato ContextoEstudante | 100% | 100% | sim |" in tabela
    assert "| Recuperação RAG: Hit Rate@4 | ≥ 90% | 50% | **não** |" in tabela
