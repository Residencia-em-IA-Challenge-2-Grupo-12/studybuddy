# Harness de modelos locais

Compara modelos do Ollama no prompt de um agente, sobre as fixtures da [0.2] (`api/tests/fixtures/`). Serve para as issues [x.0] de todos os épicos. Os comandos rodam a partir de `pesquisa/`.

```bash
python -m experimentos.modelos.rodar analysis                       # configurações padrão do agente
python -m experimentos.modelos.rodar analysis --modelos qwen3:8b gemma3:12b --limite 3   # rodada rápida
python -m experimentos.modelos.rodar analysis --modelos qwen3:8b --reasoning            # uma variação
python -m experimentos.modelos.rodar analysis --juiz                # fidelidade (LLM-juiz) do que já rodou
python -m experimentos.modelos.rodar analysis --resumo              # só refaz o CSV e o Markdown
python -m pytest -q experimentos                                    # testes da harness, sem Ollama
```

| Opção | Efeito |
| :-- | :-- |
| `--temperature 0.7` | temperatura (padrão 0) |
| `--reasoning` | liga o modo `<think>` (só modelos que suportam, como o qwen3) |
| `--sem-format` | não passa o JSON Schema do contrato como `format` (o JSON fica só pedido no prompt) |
| `--pull` | baixa com `ollama pull` os modelos que faltarem (sem isso, a harness para e avisa) |
| `--refazer` | roda de novo uma configuração que já tem resultado |

O Ollama é o de `OLLAMA_BASE_URL` (padrão `http://localhost:11434`). Funciona com o Ollama local e com o do `docker-compose.yml`.

## O que é medido

Para cada configuração × caso, a harness salva em `resultados/<agente>/<rotulo>.jsonl`:
- a saída bruta e o tempo de resposta;
- os tokens/s, tirados dos metadados do Ollama;
- se o JSON validou no contrato e, se não validou, o erro;
- a RAM ocupada pelo modelo (`/api/ps`).

A primeira chamada de cada modelo só serve para carregá-lo e não entra na latência.

O resumo fica em `<agente>.csv` e `<agente>.md`, nesta pasta, com o hardware de quem rodou. A latência só é comparável na mesma máquina.

Na fase `--juiz`, a fidelidade de cada resposta ao contexto é medida pelo juiz de `metricas/geracao/juiz.py`: afirmações sustentadas / total, no mesmo método do faithfulness do RAGAS. O juiz é sempre diferente do modelo julgado. O padrão é `gemma3:12b` (`OLLAMA_JUIZ_MODEL`); quando o julgado é o próprio gemma3, o juiz passa a ser `qwen3:8b` (`OLLAMA_JUIZ_ALT`).

## Plugar o seu agente

1. Crie `agentes/<nome>.py` com uma classe no formato do `Protocol` `Agente` (em `rodar.py`):
   - `contrato`: o modelo Pydantic que a saída precisa validar;
   - `casos()`: um `Caso(id, prompt, contexto, dados)` por fixture, com o **mesmo prompt** que o agente usa na API;
   - `avaliar(caso, objeto)`: as métricas próprias do agente, como dict;
   - `resposta(objeto)`: o texto que o juiz confere;
   - `metricas()`: as colunas do resumo;
   - `configs_padrao`: os modelos e variações a comparar.
2. Registre a classe em `_agentes()`, no `rodar.py`.

Um exemplo completo é o `agentes/analysis.py`.
