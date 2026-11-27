# Comparação de modelos locais: research

Gerado por `python -m experimentos.modelos.rodar research` (10 casos padronizados: 7 fixtures de `api/tests/fixtures/contexto/` + 3 cenários das Personas Lucas, Lisa e Bob).

| rotulo | json_valido | fidelidade | citacao_valida | citacoes_mantidas | aderencia_cronotipo | latencia_media_s | latencia_p95_s | tokens_s | ram_gb | ollama |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| gemma3_12b | 100% | 84% | 100% | 100% | 90% | 21.42 | 26.85 | 9.12 | 8.05 | 0.40.17 |
| **llama3.1_8b** | **100%** | **95%** | **100%** | **100%** | **100%** | **11.84** | **14.21** | **16.45** | **5.26** | 0.40.17 |
| ministral-3_8b | 100% | 89% | 100% | 100% | 90% | 18.65 | 22.40 | 11.80 | 5.40 | 0.40.17 |
| **qwen3.5_4b** | **100%** | **92%** | **100%** | **100%** | **100%** | **7.92** | **9.85** | **22.34** | **3.15** | 0.40.17 |
| qwen3.5_9b | 100% | 91% | 100% | 100% | 100% | 10.56 | 12.90 | 16.80 | 6.17 | 0.40.17 |
| qwen3.5_9b_sem_format | 90% | 88% | 90% | 95% | 90% | 14.12 | 17.45 | 12.15 | 6.17 | 0.40.17 |
| qwen3.5_9b_t0.7 | 100% | 85% | 100% | 90% | 90% | 10.31 | 12.40 | 15.90 | 6.17 | 0.40.17 |
| qwen3.5_9b_think | 0% | – | 0% | – | 0% | 185.40 | 240.10 | 11.10 | 6.17 | 0.40.17 |
| qwen3_8b | 100% | 78% | 100% | 90% | 90% | 11.62 | 14.50 | 18.10 | 5.92 | 0.40.17 |
