# Comparação de modelos locais: analysis

Gerado por `python -m experimentos.modelos.rodar analysis`. Hardware: Apple M4, 24 GB de memória unificada, Darwin 25.6.0. A latência só é comparável entre linhas com a mesma versão do Ollama.

| rotulo | json_valido | fidelidade | fidelidade_ministral | citacao_valida | citacoes_mantidas | tecnica_adequada | latencia_media_s | latencia_p95_s | tokens_s | ram_gb | ollama |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| gemma3_12b | 100% | – | – | 100% | 100% | 100% | 27.534 | 35.05 | 8.587 | 8.05 | 0.32.5 |
| gemma4_12b | 100% | – | – | 100% | 100% | 100% | 12.708 | 15.92 | 19.123 | 19.7 | 0.40.17 |
| gemma4_e4b | 100% | – | – | 100% | 100% | 100% | 6.136 | 7.97 | 41.15 | 11.03 | 0.40.17 |
| llama3.1_8b | 100% | 96% | – | 100% | 100% | 100% | 15.263 | 17.89 | 14.52 | 5.26 | 0.32.5 |
| ministral-3_8b | 100% | 88% | – | 100% | 100% | 100% | 23.9 | 29.05 | 10.69 | 1.2 | 0.40.17 |
| muse-glimmer_30b_teste | 0% | – | – | 0% | – | 0% | 58.907 | 61.49 | 3.8 | 15.82 | 0.40.17 |
| qwen3.5_4b | 100% | 93% | – | 100% | 100% | 100% | 10.386 | 12.81 | 19.727 | 3.15 | 0.32.5 |
| qwen3.5_9b-q8_0 | 100% | – | – | 100% | 100% | 100% | 21.077 | 24.01 | 8.367 | 10.07 | 0.32.5 |
| qwen3.5_9b | 100% | 93% | – | 100% | 100% | 100% | 13.154 | 16.05 | 15.153 | 6.17 | 0.32.5 |
| qwen3.5_9b_sem_format | 100% | – | – | 100% | 100% | 100% | 17.374 | 20.11 | 11.39 | 6.17 | 0.32.5 |
| qwen3.5_9b_t0.7 | 100% | – | – | 100% | 100% | 100% | 12.865 | 14.13 | 10.623 | 6.17 | 0.32.5 |
| qwen3.5_9b_think | 0% | – | – | 0% | – | 0% | 300.324 | 331.01 | 11.42 | 4.78 | 0.40.17 |
| qwen3_8b | 100% | 56% | – | 100% | 100% | 100% | 14.495 | 18.42 | 17.237 | 5.92 | 0.32.5 |
