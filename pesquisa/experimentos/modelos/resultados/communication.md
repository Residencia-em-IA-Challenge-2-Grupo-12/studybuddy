# Communication: comparação de modelos locais

Máquina: Darwin 27.0.0, arm64, 24 GB de RAM, Ollama em http://localhost:11434.

Cada modelo respondeu aos mesmos 10 check-in(s) sobre a mesma grade aprovada, com 3 repetição(ões) por cenário. O plano é montado sem LLM, então a diferença entre modelos aparece na abertura: tom, naturalidade e custo.

Tom e plano são determinísticos (a regra de tom e a montagem da grade não usam LLM) e por isso não discriminam modelos; servem como trava contra regressão. As métricas que de fato diferenciam são horários inventados, citações inválidas, caracteres úteis e custo.

## Resultado por modelo

| modelo | erros | tom correto | plano fiel | horários inventados | citações inválidas | latência LLM mediana (s) | p95 (s) | tokens/s | chars úteis | VRAM (MB) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `llama3.1:8b` | 0 | 1.0 | 1.0 | 0 | 0 | 13.71 | 18.0 | 6.5 | 281.0 | 5019.5 |
| `gemma3:12b` | 0 | 1.0 | 1.0 | 0 | 0 | 21.55 | 32.05 | 4.5 | 357.5 | 7676.3 |
| `qwen3:4b` | 0 | 1.0 | 1.0 | 0 | 0 | 168.12 | 347.52 | 21.05 | 350.5 | 3022.9 |

Fração descartada da saída bruta (raciocínio que não chega ao usuário): `llama3.1:8b`=0.0, `gemma3:12b`=0.0, `qwen3:4b`=0.97

## Escolha

Modelo padrão proposto para o Communication: **`llama3.1:8b`**.

Critério, nesta ordem: menos erros, nenhum horário inventado, nenhuma citação inválida, depois tom e plano corretos, e por fim a latência mediana (o p95 desempata). A naturalidade fica com a leitura cega (`communication_cego.md`), porque nenhuma métrica automática a mede.

As aberturas de cada execução estão em `communication_resultados.json`. O gabarito da leitura cega está em `communication_gabarito.json`.
