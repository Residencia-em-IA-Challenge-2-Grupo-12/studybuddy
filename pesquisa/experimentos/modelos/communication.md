# Communication: comparação de modelos locais

Máquina: Darwin 27.0.0, arm64, 24 GB de RAM, Ollama em http://localhost:11434.

Cada modelo respondeu aos mesmos 10 check-in(s) sobre a mesma grade aprovada, com 1 repetição(ões) por cenário. O plano é montado sem LLM, então a diferença entre modelos aparece na abertura: tom, naturalidade e custo.

Tom e plano são determinísticos (a regra de tom e a montagem da grade não usam LLM) e por isso não discriminam modelos; servem como trava contra regressão. As métricas que de fato diferenciam são horários inventados, citações inválidas, caracteres úteis e custo.

## Resultado por modelo

| modelo | erros | tom correto | plano fiel | horários inventados | citações inválidas | latência LLM mediana (s) | p95 (s) | tokens/s | chars úteis | VRAM (MB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen3:8b` | 0 | 1.0 | 1.0 | 0 | 0 | 7.92 | 9.98 | 19.3 | 383.5 | 5645.6 |
| `llama3.1:8b` | 0 | 1.0 | 1.0 | 0 | 0 | 13.55 | 16.73 | 7.9 | 274.0 | 5019.5 |
| `gemma3:12b` | 0 | 1.0 | 1.0 | 0 | 0 | 24.55 | 31.56 | 5.25 | 357.5 | 7676.3 |
| `qwen3:4b` | 0 | 1.0 | 1.0 | 0 | 0 | 297.83 | 371.05 | 21.25 | 349.0 | 3022.9 |

Fração descartada da saída bruta (raciocínio que não chega ao usuário): `qwen3:8b`=0.0, `llama3.1:8b`=0.0, `gemma3:12b`=0.0, `qwen3:4b`=0.971

## Escolha

Modelo padrão proposto para o Communication: **`qwen3:8b`**.

Critério, nesta ordem: menos erros, nenhum horário inventado, nenhuma citação inválida, depois tom e plano corretos, e por fim a latência mediana (o p95 desempata). A naturalidade fica com a leitura cega (`communication_cego.md`), porque nenhuma métrica automática a mede.

As aberturas de cada execução estão em `communication_resultados.json`. O gabarito da leitura cega está em `communication_gabarito.json`.
