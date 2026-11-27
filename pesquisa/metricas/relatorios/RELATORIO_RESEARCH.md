# Relatório Final do Research Agent ([2.7] Issue #42)

> Relatório completo espelhado em [`docs/research_final_report.md`](../../../docs/research_final_report.md).

Avaliação consolidada do **Research Agent** (`api/app/modules/agentes/research/`) com as métricas definidas em [`docs/research_metrics.md`](../../../docs/research_metrics.md) e [`../agentes/research/METRICAS.md`](../agentes/research/METRICAS.md), sobre os **22 cenários rotulados** de [`../agentes/research/cenarios.json`](../agentes/research/cenarios.json) e o benchmark de modelos locais de [`../../experimentos/modelos/research_escolha.md`](../../experimentos/modelos/research_escolha.md).

**Como reproduzir** (a partir de `pesquisa/`):

```bash
python -m metricas.agentes.research.runner                          # determinístico + RAG (< 1 s)
python -m metricas.agentes.research.runner --llm llama3.1:8b --juiz # + curadoria LLM e juiz
python -m pytest -q metricas/agentes/research                       # testes automatizados no CI
```

## Tabela-Resumo

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Validade do contrato `ContextoEstudante` | 100% | 100% | sim |
| Integridade da persistência SQLite | 100% | 100% | sim |
| Integridade de janelas circadianas e sono | 100% | 100% | sim |
| Precisão do check-in e índice de capacidade | 100% | 100% | sim |
| Consistência de leitura/escrita da agenda | 100% | 100% | sim |
| Acurácia do porteiro de distância L2 | ≥ 95% | 100% | sim |
| Recuperação RAG: Hit Rate@4 | ≥ 90% | 100% | sim |
| Recuperação RAG: MRR (*Mean Reciprocal Rank*) | ≥ 80% | 80% | sim |
| Acerto integral do cenário esperado | 100% | 100% | sim |
| Curadoria LLM (`llama3.1:8b`): JSON válido no contrato | ≥ 95% | 100% | sim |
| Curadoria LLM (`llama3.1:8b`): citação válida após verificador | ≥ 95% | 100% | sim |
| Curadoria LLM (`llama3.1:8b`): precisão das citações (ALCE) | ≥ 95% | 100% | sim |
| Curadoria LLM (`llama3.1:8b`): aderência ao cronotipo e estado | ≥ 90% | 100% | sim |
| Curadoria LLM (`llama3.1:8b`): fidelidade ao contexto (juiz) | ≥ 85% | 95% | sim |

Consulte [`docs/research_final_report.md`](../../../docs/research_final_report.md) para a arquitetura detalhada, diagrama Mermaid, tabela completa de comparação dos 9 modelos locais do Ollama e análise crítica métrica a métrica.
