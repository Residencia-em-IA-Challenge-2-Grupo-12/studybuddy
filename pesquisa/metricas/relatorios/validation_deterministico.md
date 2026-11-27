# Métricas do Validation e Guardrails: `deterministico`

Gerado por `python -m metricas.agentes.validation.runner` (a partir de `pesquisa/`), sobre `cenarios_validation.json` (24 cenários).

## 1. Validation Determinístico (sem LLM)

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Validade do contrato (ResultadoValidacao) | 100% | 100.0% | sim |
| Acerto das regras — Precisão macro | 100% | 100.0% | sim |
| Acerto das regras — Recall macro | 100% | 100.0% | sim |
| Acerto das regras — F1 macro | 100% | 100.0% | sim |
| Precisão CONFLITO_AGENDA | 100% | 100.0% | sim |
| Recall CONFLITO_AGENDA | 100% | 100.0% | sim |
| Precisão INTEGRIDADE_CIRCADIANA | 100% | 100.0% | sim |
| Recall INTEGRIDADE_CIRCADIANA | 100% | 100.0% | sim |
| Precisão SOBRECARGA | 100% | 100.0% | sim |
| Recall SOBRECARGA | 100% | 100.0% | sim |
| Falso alarme do Validation (FPR em válidos) | 0% | 0.0% | sim |
| Acurácia do excesso_min (SOBRECARGA) | 100% | 100.0% | sim |
| Mensagens acionáveis (dia + cortar/mover) | 100% | 100.0% | sim |
| Zero chamadas a LLM no Validation | 100% | 100.0% | sim |
| Latência Validation p50 | – | 0.08 ms | – |
| Latência Validation p95 | ≤ 10 ms | 0.10 ms | sim |
