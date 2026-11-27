# Métricas do Research Agent: deterministico

Gerado por `python -m metricas.agentes.research.runner` (a partir de `pesquisa/`), 22 cenários de `metricas/agentes/research/cenarios.json`.

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Validade do contrato ContextoEstudante | 100% | 100% | sim |
| Integridade da persistência SQLite | 100% | 100% | sim |
| Integridade de janelas circadianas e sono | 100% | 100% | sim |
| Precisão do check-in e índice de capacidade | 100% | 100% | sim |
| Consistência de leitura/escrita da agenda | 100% | 100% | sim |
| Acurácia do porteiro de distância L2 | ≥ 95% | 100% | sim |
| Recuperação RAG: Hit Rate@4 | ≥ 90% | 100% | sim |
| Recuperação RAG: MRR (Mean Reciprocal Rank) | ≥ 80% | 80% | sim |
| Acerto integral do cenário esperado | 100% | 100% | sim |
| Curadoria LLM: JSON válido no contrato | ≥ 95% | – | – |
| Curadoria LLM: citação válida após verificador | ≥ 95% | – | – |
| Curadoria LLM: precisão das citações (ALCE) | ≥ 95% | – | – |
| Curadoria LLM: aderência ao cronotipo e estado | ≥ 90% | – | – |
| Curadoria LLM: fidelidade ao contexto (juiz) | ≥ 85% | – | – |
