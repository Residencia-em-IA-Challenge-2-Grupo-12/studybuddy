# Métricas do Analysis: llama3.1_8b, antes da correção do verificador ([Fragmento #N] não era reconhecido)

Gerado por `python -m metricas.agentes.analysis.runner --llm llama3.1:8b --juiz` (a partir de `pesquisa/`), 27 cenários de `metricas/agentes/analysis/cenarios.json`, 68 justificativas do `llama3.1:8b`, juiz `gemma3:12b`.

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Validade do contrato | 100% | 100% | sim |
| Integridade (regras duras) | 100% | 100% | sim |
| Alta carga no vale | 0 blocos | 0 | sim |
| Aderência circadiana | ≥ 80% | 93% | sim |
| Cobertura de prazos | 100% | 100% | sim |
| Uso das janelas (pior cenário) | ≤ 75% | 75% | sim |
| Adequação das pausas | 100% | 100% | sim |
| Sucesso do reajuste | 100% | 100% | sim |
| Acerto da resposta esperada | 100% | 100% | sim |
| Justificativa: JSON válido | ≥ 95% | 100% | sim |
| Justificativa: citação válida | ≥ 95% | 88% | **não** |
| Justificativa: precisão das citações | ≥ 95% | 100% | sim |
| Justificativa: técnica adequada | ≥ 95% | 88% | **não** |
| Justificativa: fidelidade (juiz) | ≥ 85% | 88% | sim |
