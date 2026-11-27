# Escolha do modelo do Analysis

Tabela completa em [`analysis.md`](analysis.md) (gerada pela harness). Hardware: Apple M4, 24 GB de memória unificada. Mesmas 30 justificativas (8 fixtures, uma por material) para todos os modelos, com o mesmo prompt e os mesmos trechos que a API usa.

**Escolha: `llama3.1:8b`** (`OLLAMA_ANALYSIS_MODEL`, padrão em `api/app/core/config.py`). **Alternativa leve: `qwen3.5:4b`.**

## Os finalistas

| Modelo | JSON, citação e técnica | Fidelidade (juiz padrão) | Fidelidade (juiz único `ministral-3:8b`) | Latência média / p95 | RAM |
| :-- | --: | --: | --: | --: | --: |
| `gemma4:12b` | 100% | 100%¹ | **92%** | 12,7 s / 15,9 s | **19,7 GB** |
| **`llama3.1:8b`** | 100% | **96%** | **90%** | 15,3 s / 17,9 s | 5,3 GB |
| `qwen3.5:4b` | 100% | 93% | 82% | **10,4 s / 12,8 s** | **3,2 GB** |
| `qwen3.5:9b` | 100% | 93% | 81% | 13,2 s / 16,1 s | 6,2 GB |
| `qwen3:8b` (antigo padrão) | 100% | 56% | – | 14,5 s / 18,4 s | 5,9 GB |

¹ Julgado pelo `qwen3:8b`, porque o juiz padrão (`gemma3:12b`) é da mesma família. Por isso a coluna do juiz padrão não compara os Gemma com os outros: a do juiz único é a comparação justa.

## Por que o `llama3.1:8b`

1. **Formato não decide:** depois da normalização do verificador de citações, todos os finalistas têm 100% de JSON válido, citação válida e técnica adequada. O que separa os modelos é a fidelidade.
2. **Fidelidade alta com os dois juízes.** Os dois juízes concordam na ordem: `llama3.1:8b` à frente do `qwen3.5:4b` (96% × 93% e 90% × 82%) e do `qwen3.5:9b`. Só o `gemma4:12b` passa dele no juiz único.
3. **O `gemma4:12b` não cabe na operação:** 19,7 GB de 24 GB, sem sobrar para o `bge-m3` e os modelos dos outros agentes, que dividem o mesmo Ollama.
4. **Custo aceitável:** 5,3 GB e 15 s por material, no mesmo patamar do antigo padrão, com fidelidade de 56% → 96%.

## Por que o `qwen3.5:4b` como alternativa

O mais rápido (10 s) e o mais leve (3,2 GB) entre os que acertam o formato em 100%. Perde 8 pontos de fidelidade no juiz único, então serve para máquinas com pouca memória ou quando a latência pesa mais.

## Descartados

| Configuração | Motivo |
| :-- | :-- |
| `qwen3.5:9b` com reasoning | 0% de JSON válido: 5 minutos por chamada e resposta vazia |
| `muse-glimmer:30b` | 0% de JSON (`<\|eot\|>` grudado), ~1 min por chamada, 15,8 GB |
| `qwen3.5:9b-q8_0` | mais lento (21 s) e quase 2× a RAM do q4, sem ganho de formato |
| `qwen3.5:9b` sem `format` | mais lento (17 s); o JSON Schema como `format` só ajuda |
| `gemma3:12b` | o mais lento (27,5 s) e fidelidade de 79% |
| `gemma4:e4b` | rápido (6 s), mas 84% de fidelidade e 11 GB |
| `ministral-3:8b` | 88% de fidelidade e 24 s por chamada; virou o juiz único da calibração |

## Limitações

- 30 casos por modelo: diferenças de poucos pontos (ex.: 92% × 90%) estão dentro do ruído.
- A fidelidade é a opinião de outro modelo; a calibração com rótulo humano está na [0.4].
- A latência só vale para esta máquina, e as rodadas misturam Ollama 0.32.5 e 0.40.17 (coluna `ollama` da tabela).
