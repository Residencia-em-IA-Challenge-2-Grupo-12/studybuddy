# Relatório final do Analysis Agent

Avaliação do Analysis Agent com as métricas definidas em [`../agentes/analysis/METRICAS.md`](../agentes/analysis/METRICAS.md), sobre os 27 cenários rotulados de [`../agentes/analysis/cenarios.json`](../agentes/analysis/cenarios.json) (20 de planejamento e 7 de reajuste, todos montados a partir das fixtures da [0.2]).

**Como reproduzir** (a partir de `pesquisa/`, com o Ollama aberto e o índice em `api/chroma_db`):

```bash
python -m metricas.agentes.analysis.runner --llm llama3.1:8b --juiz   # tudo: alocação, Validation, justificativa e juiz (~45 min)
python -m metricas.agentes.analysis.runner                             # só a parte sem LLM (< 1 s)
```

Saídas nesta pasta: `analysis_llama3.1_8b.{csv,json,md}` + `analysis_llama3.1_8b_llm.csv` (uma linha por justificativa, com a resposta crua do LLM no JSON) e `analysis_deterministico.*`. A rodada anterior à correção do verificador ficou em `analysis_llama3.1_8b_antes.*`, para comparação.

Ambiente: Apple M4, 24 GB, Ollama 0.40.17. Gerador `llama3.1:8b` (escolha da [3.0], em [`../../experimentos/modelos/analysis_escolha.md`](../../experimentos/modelos/analysis_escolha.md)), juiz `gemma3:12b`, temperatura 0.

## Tabela-resumo

| Métrica | Meta | Resultado | Atingiu? |
| :-- | :-- | --: | :-: |
| Validade do contrato | 100% | 100% | sim |
| Integridade (regras duras) | 100% | 100% | sim |
| Alta carga no vale | 0 blocos | 0 | sim |
| Aderência circadiana | ≥ 80% | 93% | sim |
| Cobertura de prazos | 100% | 100% | sim |
| Uso das janelas (pior cenário) | ≤ 75% | 75% | sim (no limite) |
| Adequação das pausas | 100% | 100% | sim |
| Sucesso do reajuste | 100% | 100% | sim |
| Acerto da resposta esperada | 100% | 100% | sim |
| Justificativa: JSON válido | ≥ 95% | 100% | sim |
| Justificativa: citação válida | ≥ 95% | 100% (88% antes da correção) | sim |
| Justificativa: precisão das citações | ≥ 95% | 100% | sim |
| Justificativa: técnica adequada | ≥ 95% | 100% (88% antes da correção) | sim |
| Justificativa: fidelidade (juiz) | ≥ 85% | 90% | sim |

Integração com o Validation do épico [4] (informativas, sem meta, porque dependem dos limiares do Validation):

| Medida | Resultado |
| :-- | --: |
| Aprovado pelo Validation sem reajuste | 70% (14 de 20) |
| Aprovado em até 3 reajustes | 100% (os 6 restantes, todos com 1 reajuste) |
| Cobertura de prazos depois do ciclo | 96% |

As metas foram fixadas no código (`metricas.METAS`) antes da primeira rodada.

## 1. Validade do contrato

- **Definição:** a proposta é uma `PropostaGrade` válida e sobrevive à ida e volta em JSON. Sem isso, o Validation e o Communication nem conseguem ler a grade.
- **Método:** `PropostaGrade.model_validate_json(p.model_dump_json()) == p` nos 27 cenários (nos de reajuste, sobre a proposta reajustada).
- **Resultado:** 100% (meta 100%).
- **Análise:** esperado, porque a grade é montada por código e não pelo LLM; o LLM só preenche `tecnica` e `justificativa`, e campo a mais é rejeitado (`extra="forbid"`).
- **Próximos passos:** manter no CI (já está em `test_metricas.py`).

## 2. Integridade (regras duras)

- **Definição:** nenhum bloco fora do tempo disponível, nenhuma alta carga no vale, nenhum bloco no dia do prazo ou depois, nenhum bloco sobreposto.
- **Método:** `invariantes.todas` + `regras.detectar` (o substituto mínimo do Validation) nos 27 cenários.
- **Resultado:** 100% (meta 100%).
- **Análise:** inclui os cenários de borda (agenda lotada, prazo passado, redução de danos) e as propostas depois do reajuste.
- **Próximos passos:** trocar `regras.detectar` pelo Validation real ([4.1]) como checagem principal, já que ele entrou na develop.

## 3. Alta carga no vale

- **Definição:** blocos de alta carga com o foco num vale (ex.: pós-almoço). É a regra central do agente.
- **Método:** contagem nos 27 cenários.
- **Resultado:** 0 (meta 0).
- **Análise:** a preferência de fatia da alocação (`alta: pico → neutro`, nunca vale) garante isso por construção; o reajuste também nunca coloca alta carga em vale.
- **Próximos passos:** nenhum.

## 4. Aderência circadiana

- **Definição:** dos blocos de alta carga, a fração com o foco inteiro dentro de um pico.
- **Método:** média dos 16 cenários de planejamento que têm alta carga.
- **Resultado:** 93% (meta ≥ 80%).

| Cenário | Aderência |
| :-- | --: |
| 11 cenários | 100% |
| `fadiga`, `abaixo_do_limiar` | 94% |
| `prazo_apertado` | 86% |
| `sem_espaco` | 84% |
| **`dois_prazos_terca`** | **33%** |

- **Análise:** onde a demanda cabe nos picos, a aderência é 100%. Ela cai quando o prazo comprime o tempo: em `dois_prazos_terca`, Cálculo e Programação vencem na terça e só a segunda serve, que tem um pico de 3 h para ~6 h de alta carga. O resto vai para o horário neutro, como a heurística permite (nunca para o vale).
- **Próximos passos:** com prazo apertado, avisar o estudante que parte da alta carga ficou fora do pico, em vez de só aceitar o neutro em silêncio.

## 5. Cobertura de prazos

- **Definição:** dos materiais que o rótulo diz que cabem antes do prazo, a fração com as horas estimadas inteiras agendadas antes dele.
- **Método:** 17 materiais com prazo rotulado, nos cenários de planejamento.
- **Resultado:** 100% (meta 100%). **Depois do ciclo com o Validation: 96%.**
- **Análise:** o Analysis sozinho cumpre todos os prazos. O problema aparece na integração: em `dois_prazos_terca` o Analysis põe 350 min de foco na segunda; o Validation limita a 240 min/dia e devolve `SOBRECARGA`; o reajuste corta pelo material de menor prioridade e o **`prog-01` fica com 50 de 90 min antes do prazo**, enquanto o **`calc-01` fica com 175 de 120 min**, porque mantém os blocos extras que a prioridade dá a urgentes e difíceis.
- **Próximos passos:** (1) no corte de `SOBRECARGA`, tirar primeiro os blocos **extras** de quem já cumpriu as horas, antes de tirar horas necessárias de outro material com prazo; (2) o Analysis respeitar um teto diário configurável (o mesmo do Validation), para não depender do loop.

## 6. Uso das janelas

- **Definição:** tempo agendado (foco + pausa) / tempo disponível; a meta vale para o pior cenário.
- **Método:** 20 cenários de planejamento.
- **Resultado:** pior cenário **75%** (meta ≤ 75%), média 31%. Maior foco num único dia: 50 a 350 min.
- **Análise:** o pior caso é `sem_espaco` (40 h de demanda numa agenda com só manhãs cedo e noites): a alocação enche tudo o que pode, exatamente no limite da meta. Não há teto de ocupação na alocação; o que segura é só a falta de janela. O maior foco diário passa das ~4 h de trabalho profundo de Newport (`artigo_06`) em 5 cenários (250 min com blocos de 50 min e 350 min em `dois_prazos_terca`). São esses 5 que o Validation reprova por `SOBRECARGA`, mais o `fadiga`: lá o limite cai de 240 para 168 min pelo check-in (estresse 5, 4 h de sono), e os 175 min do dia passam.
- **Próximos passos:** o mesmo teto diário do item 5; com ele, `sem_espaco` deixaria mais material em `fora_da_grade` em vez de lotar a semana.

## 7. Adequação das pausas

- **Definição:** foco e pausa seguem a tabela do Pomodoro adaptativo (50/10, 25/5, 25/10, 25/15).
- **Método:** todos os blocos dos 20 cenários de planejamento, contra o ritmo do rótulo (inclui os limiares exatos 0,7, 0,4 e 0,39).
- **Resultado:** 100% (meta 100%).
- **Análise:** os limiares são `>=` 0,7 para energia alta e `<` 0,4 para fadiga, e os cenários de borda confirmam isso.
- **Próximos passos:** nenhum na alocação; a escolha dos limiares em si ainda é uma decisão de projeto sem dado de estudante real.

## 8. Sucesso do reajuste

- **Definição:** das violações devolvidas, quantas o reajuste resolve sem criar outra.
- **Método:** 7 cenários com 10 violações (das fixtures e plantadas: conflito com aula, sono, vale, refeição, sobrecarga e um caso sem solução).
- **Resultado:** 100% (meta 100%).
- **Análise:** o reajuste mexe só nos blocos apontados e, quando não há onde encaixar (`reajuste_sem_solucao`), reduz a carga e põe o material em `fora_da_grade`. Com o Validation real, todos os 6 cenários reprovados ficam aprovados com 1 reajuste.
- **Próximos passos:** a regra de corte do item 5.

## 9. Acerto da resposta esperada

- **Definição:** o cenário inteiro bate com o rótulo (modo, ritmo, `fora_da_grade`, redução de danos, prazos, violações).
- **Método:** 27 cenários.
- **Resultado:** 100% (meta 100%).
- **Análise:** os rótulos foram escritos a partir da especificação das issues [3.1]–[3.3], não da saída do agente; os testes de `test_metricas.py` conferem que as fórmulas acusam propostas erradas (ex.: a fixture `violacoes` derruba integridade e aderência).
- **Próximos passos:** acrescentar cenários quando o Research ([2.5]) gerar contextos reais.

## 10. JSON válido

- **Definição:** a resposta do LLM valida no esquema `{tecnica, justificativa}`.
- **Método:** 68 justificativas (uma por material nos 20 cenários de planejamento), com o JSON Schema passado como `format` ao Ollama.
- **Resultado:** 100% (meta ≥ 95%).
- **Análise:** a saída estruturada do Ollama resolve o formato; na [3.0], sem `format` o mesmo modelo ficou mais lento sem ganhar nada.
- **Próximos passos:** nenhum.

## 11. Citação válida

- **Definição:** depois do verificador, sobra ao menos uma citação de artigo recebido (senão a API cai na técnica padrão).
- **Método:** 68 justificativas.
- **Resultado:** **100%** (meta ≥ 95%). Na primeira rodada: **88%**.
- **Análise:** na primeira rodada, 8 justificativas caíram na técnica padrão, todas do `ing-01` (flashcards de inglês) nos cenários de ritmo normal. A resposta crua mostrou a causa: o `llama3.1:8b` citou `[Fragmento #1]` em vez de `[Fonte: artigo_02...]`, e o verificador não reconhecia esse formato. Com o mesmo prompt, o mesmo modelo tinha citado no formato certo na [3.0], que rodou no Ollama 0.32.5; esta rodada foi no 0.40.17. Temperatura 0 é estável dentro de uma versão, não entre versões do runtime. Correção: o verificador passou a resolver `[Fragmento #N]` pelo número do trecho (os trechos chegam numerados) e a remover números que não existem.
- **Próximos passos:** fixar a versão do Ollama no `docker-compose`/README ([0.5]) e rodar este runner a cada troca de versão ou de modelo.

## 12. Precisão das citações

- **Definição:** das citações de artigo, a fração que o verificador manteve.
- **Método:** 68 justificativas.
- **Resultado:** 100% (meta ≥ 95%).
- **Análise:** o modelo não citou nenhum artigo que não recebeu. A métrica não diz se o artigo citado **sustenta** a frase; isso é a fidelidade (item 14) e a checagem de suporte de citação da [0.4].
- **Próximos passos:** suporte de citação por frase ([0.4]).

## 13. Técnica adequada

- **Definição:** a técnica combina com a carga e alta carga não recebe flashcards.
- **Método:** 68 justificativas (técnica padrão por falha conta como erro).
- **Resultado:** **100%** (meta ≥ 95%). Na primeira rodada: 88%, pelas mesmas 8 falhas do item 11.
- **Análise:** a escolha é pouco variada: **todos os 32 materiais de alta carga receberam "Prática intercalada"**, nunca active recall nem Feynman, e a baixa carga ficou entre "Repetição espaçada" e "Flashcards com repetição espaçada". A busca da alta carga traz sobretudo trechos de `artigo_03_interleaving`, e o modelo escolhe a técnica que aparece nos trechos. É adequada, mas não personalizada.
- **Próximos passos:** variar a consulta por tipo de material (lista de exercícios → active recall; conceito novo → Feynman) e medir a diversidade de técnicas como métrica nova.

## 14. Fidelidade

- **Definição:** as afirmações da justificativa estão nos dados da grade ou nos trechos recebidos.
- **Método:** juiz `gemma3:12b` (outra família do gerador) quebra cada justificativa em afirmações e julga cada uma; nota = sustentadas / total. 68 justificativas, 285 afirmações.
- **Resultado:** **90%** (meta ≥ 85%). 36 das 285 afirmações não sustentadas.

| Carga | Justificativas | Fidelidade |
| :-- | --: | --: |
| alta | 32 | 81% |
| baixa | 36 | 97% |

- **Análise:** a queda está na alta carga, como já tinha aparecido na [3.0]. As afirmações reprovadas não são fatos inventados, e sim **pontes** entre o artigo e o material: "a discriminação categórica é importante para o Cálculo I", "a prática intercalada não cria proficiência ilusória" (o artigo diz que a prática em blocos cria; o contrário é inferência). O juiz está certo em reprovar: o trecho não diz isso.
- **Próximos passos:** (1) ajustar o prompt para descrever o que o artigo mostra sem aplicar ao conteúdo da disciplina; (2) calibrar o juiz contra rótulo humano ([0.4]): 90% é a opinião do `gemma3:12b`.

## Latência

Média de 13,9 s por material e p95 de 19,9 s (só a chamada do gerador, sem o juiz). Uma semana com 4 materiais leva ~1 min de justificativa, chamada só depois que o Validation aprova a grade.

## Limitações

- **Dados sintéticos:** os 27 cenários vêm das 7 fixtures da [0.2], todas com a mesma semana e quase os mesmos 4 materiais. Não há contexto real de estudante (depende do Research, [2.5]).
- **Tamanho:** 27 cenários e 68 justificativas. Diferenças de poucos pontos estão dentro do ruído.
- **Viés do juiz:** a fidelidade é a opinião de um modelo (`gemma3:12b`). Na [3.0], dois juízes diferentes deram notas diferentes para o mesmo modelo (96% e 90%). Falta a calibração com rótulo humano ([0.4]).
- **Versão do runtime:** a mesma configuração mudou de comportamento entre o Ollama 0.32.5 e o 0.40.17 (item 11).
- **Rótulos escritos pela mesma pessoa que fez o agente:** os testes conferem que as fórmulas acusam erros plantados, mas uma revisão dos rótulos por outra pessoa do grupo reduziria esse viés.
- **Integração parcial:** a parte do Validation usa o agente real ([4.1]–[4.3]); o loop real do Maestro ([1.3]) ainda não existe, então o ciclo de reajuste foi simulado no runner, com até 3 iterações.
