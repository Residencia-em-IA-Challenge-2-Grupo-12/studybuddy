# Communication: avaliação do agente

Modelo gerador: `qwen3:8b`. Juiz: `gemma3:12b`. Cenários: 25 (+0 com erro).

Máquina: Darwin 27.0.0, arm64, 24 GB de RAM, Ollama em http://localhost:11434.

## Resumo

| métrica | meta | resultado | atingiu? |
| --- | ---: | ---: | :---: |
| Fidelidade ao plano | 1 | 1 | sim |
| Planos fiéis (todos os blocos, na ordem) | 1 | 1 | sim |
| Horários inventados | 0 | 0 | sim |
| Citações inválidas | 0 | 0 | sim |
| Citações válidas | 1 | 1 | sim |
| Clareza (Flesch-PT) | 50 | 69.5 | sim |
| Tom pela regra | 1 | 1 | sim |
| Adequação do tom (juiz) | 0.8 | 0.98 | sim |
| Faithfulness (juiz) | 0.9 | 0.7733 | não |
| Latência p95 (s) | 30 | 7.995 | sim |

## Por cenário

| cenário | tom esperado | tom gerado | plano fiel | citações inválidas | clareza | latência (s) |
| --- | --- | --- | :---: | :---: | ---: | ---: |
| fadiga_extrema | acolhedor | acolhedor | sim | 0 | 79.9 | 11.34 |
| estresse_alto | acolhedor | acolhedor | sim | 0 | 71.9 | 8.05 |
| humor_baixo | acolhedor | acolhedor | sim | 0 | 58.4 | 7.713 |
| fadiga_limite | acolhedor | acolhedor | sim | 0 | 76.3 | 5.451 |
| estresse_limite | acolhedor | acolhedor | sim | 0 | 76.9 | 5.219 |
| humor_limite_alta_energia | acolhedor | acolhedor | sim | 0 | 84.5 | 5.414 |
| misto | acolhedor | acolhedor | sim | 0 | 71.3 | 6.487 |
| recuperado | desafiador | desafiador | sim | 0 | 63.4 | 7.775 |
| fim_de_semana | desafiador | desafiador | sim | 0 | 73.3 | 7.498 |
| quase_limite | desafiador | desafiador | sim | 0 | 52.7 | 6.871 |
| energia_moderada | equilibrado | equilibrado | sim | 0 | 69.5 | 6.583 |
| sono_curto | equilibrado | equilibrado | sim | 0 | 72.4 | 5.731 |
| neutro | equilibrado | equilibrado | sim | 0 | 64.1 | 6.455 |
| um_pouco_cansado | equilibrado | equilibrado | sim | 0 | 57.5 | 5.851 |
| stress_leve | equilibrado | equilibrado | sim | 0 | 73.8 | 6.05 |
| humor_bom_cansado | equilibrado | equilibrado | sim | 0 | 59.3 | 6.701 |
| desafiador_limite | desafiador | desafiador | sim | 0 | 63.4 | 6.441 |
| sono_ruim_humor_bom | equilibrado | equilibrado | sim | 0 | 66.5 | 6.31 |
| tudo_no_limite_ruim | acolhedor | acolhedor | sim | 0 | 78.5 | 6.645 |
| energia_maxima | desafiador | desafiador | sim | 0 | 59.2 | 7.562 |
| humor_neutro | equilibrado | equilibrado | sim | 0 | 58.3 | 5.847 |
| prova_amanha | acolhedor | acolhedor | sim | 0 | 79 | 7.29 |
| pos_descanso | desafiador | desafiador | sim | 0 | 67.4 | 6.263 |
| rotina_estavel | equilibrado | equilibrado | sim | 0 | 58.6 | 6.619 |
| exausto_fim_de_semana | acolhedor | acolhedor | sim | 0 | 81.2 | 7.135 |

## O que cada métrica significa

As definições, fórmulas e fontes estão em `METRICAS.md`, na mesma pasta.
