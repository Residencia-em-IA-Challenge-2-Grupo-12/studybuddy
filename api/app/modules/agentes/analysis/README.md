# Analysis Agent

`ContextoEstudante` -> `PropostaGrade` (contratos em `../contratos.py`). A alocação é determinística, sem LLM.

| Arquivo | O que faz |
| :-- | :-- |
| `janelas.py` | Intervalos em minutos: tempo disponível (livres − ocupados − sono − refeições) recortado em fatias de pico, vale e neutro |
| `alocacao.py` | Encaixe guloso: alta carga em pico → neutro (nunca vale); baixa em vale → neutro → pico; urgentes primeiro; matérias intercaladas e espalhadas pela semana |
| `pomodoro.py` | Tamanho do bloco e da pausa pelo índice de capacidade |
| `prioridade.py` | Ordem por prazo e dificuldade, blocos extras |
| `invariantes.py` | Regras que toda proposta cumpre (usadas pelos testes e pelas métricas) |
| `agente.py` | `AgenteAnalysis.propor(ctx, diretiva)` |

## Pomodoro adaptativo

| Índice de capacidade | Estado | Foco (min) | Pausa (min) |
| :-- | :-- | --: | --: |
| ≥ `ANALYSIS_INDICE_ALTO` (0,7) | energia alta | 50 | 10 |
| entre os limiares | normal | 25 | 5 |
| < `ANALYSIS_INDICE_BAIXO` (0,4) | fadiga | 25 | 10 |
| rota `reducao_danos` | dia leve | 25 | `ANALYSIS_REDUCAO_PAUSA_MIN` (15) |

## Prioridade

- Ordem: prazo mais próximo primeiro; sem prazo, por último; no empate, o mais difícil primeiro.
- Urgente (prazo a até `ANALYSIS_DIAS_URGENCIA` = 3 dias): alocado antes de todos e com +1 bloco. Dificuldade ≥ 4 também ganha +1 bloco.
- Nenhum bloco entra no dia do prazo ou depois dele.

## Redução de danos

Quando a `DiretivaMaestro.rota` é `reducao_danos`: só baixa carga (a alta vai para `fora_da_grade`), pausa de 15 min e no máximo `ANALYSIS_REDUCAO_MAX_BLOCOS_DIA` (3) blocos por dia.
