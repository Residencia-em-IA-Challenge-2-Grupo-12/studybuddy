# Métricas do Validation e Guardrails: `completo`

Gerado por `python -m metricas.agentes.validation.runner --guardrails` (a partir de `pesquisa/`), sobre `cenarios_validation.json` (24 cenários) e `cenarios_guardrails.json` (64 cenários).

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
| Latência Validation p95 | ≤ 10 ms | 0.15 ms | sim |

## 2. Guardrails (Barreiras 4.4 a 4.7)

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Conformidade do contrato Veredito (fail-closed) | 100% | 100.0% | sim |
| Bloqueio correto — Recall geral | ≥ 95% | 97.7% | sim |
| Bloqueio correto — PROMPT_INJECTION | ≥ 95% | 100.0% | sim |
| Bloqueio correto — HATE_SPEECH | ≥ 95% | 91.7% | **não** |
| Bloqueio correto — MEDICAL_ADVICE | ≥ 95% | 100.0% | sim |
| Bloqueio correto — OUT_OF_SCOPE | ≥ 90% | 100.0% | sim |
| Acurácia de categoria exata (nos bloqueios) | ≥ 90% | 95.5% | sim |
| Falso positivo dos Guardrails (FPR total) | ≤ 5% | 5.0% | sim |
| Falso positivo — pedidos válidos diretos | 0% | 0.0% | sim |
| Falso positivo — pedidos limítrofes | ≤ 10% | 8.3% | sim |
| Robustez a ataques disfarçados/ofuscados (1 - ASR) | ≥ 90% | 95.5% | sim |
| Robustez — PROMPT_INJECTION disfarçado/ofuscado | ≥ 90% | 100.0% | sim |
| F1 de bloqueio dos Guardrails | ≥ 95% | 97.7% | sim |
| Latência Guardrails p50 | – | 3084.70 ms | – |
| Latência Guardrails p95 | ≤ 8000 ms | 3483.50 ms | sim |

### Latência por categoria (ms)

| Categoria | n | Média (ms) | p50 (ms) | p95 (ms) |
| :-- | --: | --: | --: | --: |
| `PROMPT_INJECTION` | 12 | 3221.59 | 3235.36 | 3635.77 |
| `HATE_SPEECH` | 12 | 3148.47 | 3199.90 | 3417.39 |
| `MEDICAL_ADVICE` | 10 | 3182.38 | 3200.11 | 3455.62 |
| `OUT_OF_SCOPE` | 10 | 2792.18 | 2759.53 | 3222.73 |
| `OK` | 20 | 3027.09 | 3017.97 | 3497.54 |
