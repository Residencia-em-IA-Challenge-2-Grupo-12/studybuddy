# Analysis Agent

`ContextoEstudante` -> `PropostaGrade` (contratos em `../contratos.py`). A alocação é determinística, sem LLM.

| Arquivo | O que faz |
| :-- | :-- |
| `janelas.py` | Intervalos em minutos: tempo disponível (livres − ocupados − sono − refeições) recortado em fatias de pico, vale e neutro |
| `alocacao.py` | Encaixe guloso: alta carga em pico → neutro (nunca vale); baixa em vale → neutro → pico; urgentes primeiro; matérias intercaladas e espalhadas pela semana |
| `pomodoro.py` | Tamanho do bloco e da pausa pelo índice de capacidade |
| `prioridade.py` | Ordem por prazo e dificuldade, blocos extras |
| `invariantes.py` | Regras que toda proposta cumpre (usadas pelos testes e pelas métricas) |
| `justificativa.py` | Técnica + justificativa por LLM, uma chamada por material, com citações conferidas |
| `reajuste.py` | Refaz só os blocos e dias apontados pelas violações do Validation |
| `agente.py` | `AgenteAnalysis.propor(ctx, diretiva)` e `AgenteAnalysis.reajustar(proposta, violacoes, ctx)` e `AgenteAnalysis.justificar(proposta, ctx)` |

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

## Reajuste

`reajustar(proposta, violacoes, ctx)` mexe **só** no que foi apontado. Os outros blocos ficam com o mesmo id, dia e horário.

| Regra | O que o reajuste faz |
| :-- | :-- |
| `CONFLITO_AGENDA`, `INTEGRIDADE_CIRCADIANA` | Tira o bloco e o realoca no tempo que sobrou. O horário reprovado fica proibido. Sem `bloco_id`, saem os blocos do dia que os invariantes acusam |
| `SOBRECARGA` | Corta do dia, começando pelo bloco de menor prioridade, até somar `excesso_min` de foco. Os cortados só vão para outros dias |

Nenhum dia que recebe bloco novo passa do limite: o maior dia da proposta original ou, havendo `SOBRECARGA`, o que sobrou no dia cortado. O que não couber vai para `fora_da_grade`. Os blocos novos ganham o id `r<iteracao>-NN`, e a `iteracao` sobe 1.

## Justificativa por LLM

`justificar(proposta, ctx)` devolve a proposta com técnica e justificativa em cada bloco, mais um `Relato` por material: se usou o LLM, citações válidas e removidas, tempo e o motivo quando ficou a técnica padrão.

- O LLM só escreve texto. Dia, horário, carga e pausa não mudam, e um campo a mais no JSON (ex.: `"dia"`) é rejeitado.
- Uma chamada por material. A busca e as técnicas aceitas dependem da carga: alta → active recall, prática intercalada, Feynman; baixa → flashcards, repetição espaçada.
- O verificador de citações (`rag/verificador.py`) tira `[Fonte: ...]` de artigos que o modelo não recebeu. Se não sobrar nenhuma citação válida, fica a técnica padrão (`tecnicas.py`), o mesmo que acontece se o Ollama falhar ou o JSON vier inválido.
- Modelo em `OLLAMA_ANALYSIS_MODEL` (padrão `llama3.1:8b`; alternativa leve `qwen3.5:4b`), separado do gerador e da Triagem. A escolha está em `pesquisa/experimentos/modelos/analysis_escolha.md`.
- O Maestro chama só depois que o Validation aprova, para o loop de reajuste não gastar chamadas ao LLM.
