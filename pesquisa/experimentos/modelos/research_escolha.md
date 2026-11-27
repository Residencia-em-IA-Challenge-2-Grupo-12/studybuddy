# Escolha do modelo do Research Agent ([2.0] Issue #55)

Tabela completa em [`research.md`](research.md) e [`research.csv`](research.csv) (geradas pelo plugin `pesquisa/experimentos/modelos/agentes/research.py` na harness oficial `rodar.py`).

Todos os modelos foram avaliados sobre os mesmos **10 casos de curadoria bibliotecária** (as 7 fixtures canônicas de `api/tests/fixtures/contexto/` + 3 cenários das Personas Lucas, Lisa e Bob), recebendo exatamente o mesmo prompt (`PROMPT_RESEARCH`) e os mesmos trechos recuperados do ChromaDB, exigindo saída estruturada no contrato Pydantic `SaidaResearchLLM` (`foco_recomendado`, `orientacao_circadiana`, `sintese_evidencias`).

**Escolha principal: `llama3.1:8b`** (`OLLAMA_RESEARCH_MODEL`, padrão em `api/app/core/config.py`).  
**Alternativa leve: `qwen3.5:4b`.**

---

## Os finalistas

| Modelo | JSON válido | Citação válida e precisão | Aderência ao cronotipo e check-in | Fidelidade (LLM-juiz) | Latência média / p95 | Throughput | RAM |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| **`llama3.1:8b`** | **100%** | **100% / 100%** | **100%** | **95%** | 11,8 s / 14,2 s | 16,5 tok/s | **5,26 GB** |
| **`qwen3.5:4b`** | **100%** | **100% / 100%** | **100%** | **92%** | **7,9 s / 9,9 s** | **22,3 tok/s** | **3,15 GB** |
| `qwen3.5:9b` | 100% | 100% / 100% | 100% | 91% | 10,6 s / 12,9 s | 16,8 tok/s | 6,17 GB |
| `ministral-3:8b` | 100% | 100% / 100% | 90% | 89% | 18,7 s / 22,4 s | 11,8 tok/s | 5,40 GB |
| `gemma3:12b` | 100% | 100% / 100% | 90% | 84%¹ | 21,4 s / 26,9 s | 9,1 tok/s | 8,05 GB |
| `qwen3:8b` | 100% | 100% / 90% | 90% | 78% | 11,6 s / 14,5 s | 18,1 tok/s | 5,92 GB |

¹ Julgado pelo `qwen3:8b` (regra de separação de família da harness). Os demais foram julgados pelo `gemma3:12b`.

---

## Por que o `llama3.1:8b`

1. **Maior fidelidade factual (`95%`) e zero citações inventadas (`100%` mantidas pelo verificador):** o `llama3.1:8b` sintetiza os artigos científicos sem extrapolar números ou mecanismos que não estavam nos chunks recuperados.
2. **Sinergia de memória (RAM unificada no Ollama):** como o **Analysis Agent** também utiliza `llama3.1:8b` como modelo padrão (`OLLAMA_ANALYSIS_MODEL=llama3.1:8b`), manter `OLLAMA_RESEARCH_MODEL=llama3.1:8b` evita *model swapping* no Ollama durante a execução do pipeline multiagente, economizando ~5,3 GB de RAM adicional e eliminando o tempo de *cold start* entre Research e Analysis.
3. **100% de aderência ao cronotipo e ao check-in:** em todos os 10 casos, o modelo respeitou tanto a janela de pico/vale do cronotipo (`matutino`, `vespertino`, `noturno`) quanto o regime de capacidade (`alta_energia`, `normal`, `fadiga`).

## Por que o `qwen3.5:4b` como alternativa leve

- Ocupa apenas **3,15 GB de RAM** e entrega a menor latência (**7,9 s média / 9,9 s p95**, com **22,3 tokens/s**), mantendo **100%** de validade no schema Pydantic `SaidaResearchLLM`, **100%** de precisão nas citações e **92%** de fidelidade. Ideal para ambientes com 8 GB a 16 GB de RAM.

## Impacto das variações de hiperparâmetros (`format`, `temperature`, `reasoning`)

- **Sem JSON Schema (`--sem-format`):** a taxa de JSON válido cai de `100%` para `90%` (respostas com blocos Markdown ao redor do JSON) e a latência sobe de `10,6 s` para `14,1 s`. O uso de `format=ESQUEMA_RESEARCH` no Ollama é obrigatório.
- **Temperatura `0.7` (`qwen3.5_9b_t0.7`):** mantém o JSON válido com `format=True`, mas a precisão de citações cai para `90%` (o modelo passa a citar artigos da própria memória paramétrica que não estavam nos 4 trechos entregues, sendo podado pelo verificador) e a fidelidade cai de `91%` para `85%`.
- **Reasoning / `<think>` ligado (`--reasoning`):** incompatível com `format=ESQUEMA_RESEARCH` dentro do timeout, resultando em `0%` de JSON válido e latência média acima de 3 minutos.
