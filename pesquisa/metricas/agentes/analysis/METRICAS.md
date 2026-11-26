# Métricas do Analysis Agent

Como medir se o Analysis funciona antes de dizer que funciona. O agente tem duas partes com naturezas diferentes, e cada uma é medida de um jeito:

- **Alocação** (heurística determinística, sem LLM): dias, horários, ritmo do Pomodoro, prioridade e reajuste. É medida por regras, como num problema de agendamento com restrições.
- **Justificativa** (LLM): técnica de estudo e texto citando a base de artigos. É medida como a geração de um RAG: formato, citações e fidelidade.

Os comandos rodam a partir de `pesquisa/`:

```bash
python -m metricas.agentes.analysis.runner                          # alocação (sem Ollama, < 1 s)
python -m metricas.agentes.analysis.runner --llm qwen3.5:4b --juiz  # + justificativa e fidelidade
python -m pytest -q metricas/agentes                                # testes das fórmulas
```

| Arquivo | O que faz |
| :-- | :-- |
| `cenarios.json` | Conjunto de avaliação versionado: 27 cenários rotulados, com a resposta esperada |
| `cenarios.py` | Monta cada cenário a partir das fixtures da [0.2] (`api/tests/fixtures/`) |
| `regras.py` | Substituto mínimo do Validation: gera as `Violacao` do contrato a partir das regras das fixtures |
| `metricas.py` | Fórmulas e metas |
| `runner.py` | Roda tudo e grava `metricas/relatorios/analysis_<nome>.{csv,json,md}` |

Nada aqui chama outro agente: o contexto vem das fixtures e as violações do reajuste vêm das fixtures ou de `regras.py`.

## O que a literatura e as ferramentas usam

| Fonte | O que mede | O que aproveitamos |
| :-- | :-- | :-- |
| TravelPlanner (Xie et al., 2024) | Planos de agentes LLM: *delivery rate*, *hard constraint pass rate*, *final pass rate* | Validade do contrato, integridade (regras duras) e acerto da resposta esperada |
| NATURAL PLAN (Zheng et al., 2024) | Agendamento de calendário com resposta exata conhecida | Cenários com rótulo e conferência exata |
| Pinedo, *Scheduling* (2016) | Utilização, atraso (*tardiness*), entregas no prazo | Uso das janelas e cobertura de prazos |
| Minton et al. (1992), reparo por mínimos conflitos | Reparar um plano mexendo só no que conflita | Sucesso do reajuste (resolver sem criar conflito novo) |
| RAGAS (Es et al., 2024) | *Faithfulness*: afirmações sustentadas pelo contexto / total | Fidelidade da justificativa |
| ALCE (Gao et al., 2023) | Precisão e recall de citações | Citação válida e precisão das citações |
| DeepEval | `FaithfulnessMetric`, `JsonCorrectnessMetric` | Mesmas ideias, implementadas aqui sem dependência nova (o juiz e o verificador já existem) |
| JSONSchemaBench (Geng et al., 2025) | Saída estruturada que valida no esquema | JSON válido |
| Zheng et al. (2023), *LLM-as-a-judge* | Vieses do juiz (autopreferência, posição, verbosidade) | O juiz nunca é da família do julgado |
| Dunlosky et al. (2013) | Utilidade das técnicas de estudo | Técnica adequada à carga |
| May & Hasher (1998); Schmidt et al. (2007) | Efeito de sincronia: desempenho cognitivo melhor no pico circadiano | Aderência circadiana |

## Métricas da alocação

Todas rodam sobre os 20 cenários de planejamento, e as três primeiras também sobre os 7 de reajuste (na proposta já reajustada).

### 1. Validade do contrato
- **Definição:** a proposta é uma `PropostaGrade` válida e sobrevive à ida e volta em JSON.
- **Fórmula:** propostas válidas / propostas. **Faixa:** 0–100%. **Meta:** 100%.
- **Erro:** qualquer proposta que não valida.
- **Fonte:** *delivery rate* do TravelPlanner; contrato da [0.1].

### 2. Integridade (regras duras)
- **Definição:** a proposta não fere nenhuma regra dura: bloco fora do tempo disponível (livres − ocupados − sono − refeições), alta carga no vale, bloco no dia do prazo ou depois, blocos sobrepostos.
- **Fórmula:** propostas sem violação (`invariantes.todas` + `regras.detectar`) / propostas. **Faixa:** 0–100%. **Meta:** 100%.
- **Erro:** qualquer violação.
- **Fonte:** *hard constraint pass rate* do TravelPlanner; regras do plano (Arquitetura Multiagente).

### 3. Alta carga no vale
- **Definição:** blocos de alta carga com o foco num vale (ex.: pós-almoço). Separada da integridade porque é a regra central do agente.
- **Fórmula:** contagem. **Meta:** 0.
- **Fonte:** plano (alta carga nos picos, baixa nos vales); Schmidt et al. (2007).

### 4. Aderência circadiana
- **Definição:** dos blocos de alta carga, a fração com o foco inteiro dentro de um pico. A heurística aceita o horário neutro quando os picos lotam, então a meta não é 100%.
- **Fórmula:** blocos de alta carga contidos num pico / blocos de alta carga (média dos cenários que têm alta carga). **Faixa:** 0–100%. **Meta:** ≥ 80%.
- **Erro:** cenário abaixo de 80% mostra que os picos não bastam para a demanda.
- **Fonte:** May & Hasher (1998); Schmidt et al. (2007).

### 5. Cobertura de prazos
- **Definição:** dos materiais que o rótulo diz que cabem antes do prazo, a fração com as horas estimadas inteiras agendadas antes dele.
- **Fórmula:** materiais com foco antes do prazo ≥ `horas_estimadas` × 60 / materiais rotulados. **Faixa:** 0–100%. **Meta:** 100%.
- **Erro:** material urgente com parte das horas depois do prazo ou de fora.
- **Fonte:** entregas no prazo e *tardiness* (Pinedo, 2016); motivação temporal (Steel, 2007, `artigo_11`).

### 6. Uso das janelas
- **Definição:** quanto do tempo disponível a proposta ocupa. Pouco é desperdício; perto de 100% não deixa folga para imprevistos e descanso.
- **Fórmula:** (foco + pausa) / tempo disponível, por cenário. A meta vale para o **pior cenário**. **Faixa:** 0–100%. **Meta:** ≤ 75%.
- **Erro:** cenário acima de 75%.
- **Complemento:** o relatório mostra também o maior foco num único dia (`pico_diario_min`), comparado às ~4 h de trabalho profundo por dia de Newport (`artigo_06`).
- **Fonte:** utilização (Pinedo, 2016); resíduo de atenção (Leroy, 2009, `artigo_07`).

### 7. Adequação das pausas
- **Definição:** o bloco e a pausa seguem a tabela do Pomodoro adaptativo para o índice do check-in e a rota (50/10, 25/5, 25/10, 25/15).
- **Fórmula:** blocos com (foco, pausa) igual ao rótulo / blocos. **Faixa:** 0–100%. **Meta:** 100%.
- **Fonte:** Cirillo (`artigo_10`), Newport (`artigo_06`), Baumeister (`artigo_14`); tabela em `api/app/modules/agentes/analysis/README.md`.

### 8. Sucesso do reajuste
- **Definição:** das violações devolvidas pelo Validation (aqui, pelas fixtures ou por `regras.py`), quantas o reajuste resolve sem criar outra.
- **Fórmula:** violações resolvidas / violações. Com `bloco_id`, ela some quando o bloco sai ou deixa de violar. `SOBRECARGA` some quando o foco do dia cai pelo menos `excesso_min`. Se o reajuste criar qualquer violação nova, nenhuma do cenário conta. **Faixa:** 0–100%. **Meta:** 100%.
- **Fonte:** reparo por mínimos conflitos (Minton et al., 1992).

### 9. Acerto da resposta esperada
- **Definição:** o cenário inteiro bate com o rótulo: modo, ritmo, o que fica fora da grade, só baixa carga e no máximo 3 blocos por dia na redução de danos, prazos e as violações esperadas no reajuste.
- **Fórmula:** cenários sem divergência / cenários. **Faixa:** 0–100%. **Meta:** 100%.
- **Fonte:** *final pass rate* do TravelPlanner; resposta exata do NATURAL PLAN.

## Métricas da justificativa (com `--llm`)

Uma medida por material justificado, nos 20 cenários de planejamento.

### 10. JSON válido
- **Definição:** a resposta do LLM valida no esquema `{tecnica, justificativa}`, sem campo a mais.
- **Fórmula:** respostas válidas / chamadas. **Meta:** ≥ 95%.
- **Fonte:** JSONSchemaBench (Geng et al., 2025); `JsonCorrectnessMetric` do DeepEval.

### 11. Citação válida
- **Definição:** depois do verificador, sobrou ao menos uma citação de artigo que o modelo recebeu. Sem isso, a API cai na técnica padrão.
- **Fórmula:** materiais com citação válida / materiais. **Meta:** ≥ 95%.
- **Fonte:** ALCE (Gao et al., 2023); verificador da Semana 3 (`api/app/modules/rag/verificador.py`).

### 12. Precisão das citações
- **Definição:** das citações de artigo, a fração que o verificador manteve. As inventadas saem.
- **Fórmula:** citações mantidas / citações feitas. **Meta:** ≥ 95%.
- **Fonte:** *citation precision* do ALCE.

### 13. Técnica adequada
- **Definição:** a técnica combina com a carga (alta: active recall, prática intercalada, Feynman, Pomodoro, deep work; baixa: flashcards, repetição espaçada, leitura, resumo), e alta carga não recebe flashcards.
- **Fórmula:** técnicas adequadas / materiais (técnica padrão por falha conta como erro). **Meta:** ≥ 95%.
- **Fonte:** Dunlosky et al. (2013); base `artigo_01`, `02`, `03`, `20`.

### 14. Fidelidade
- **Definição:** as afirmações da justificativa estão nos dados da grade ou nos trechos recebidos.
- **Fórmula:** afirmações sustentadas / afirmações, pelo juiz de `metricas/geracao/juiz.py` (padrão `gemma3:12b`, ou `qwen3:8b` quando o julgado é Gemma). **Faixa:** 0–100%. **Meta:** ≥ 85%.
- **Erro:** afirmação que o contexto não sustenta, mesmo que verdadeira no mundo real.
- **Fonte:** *faithfulness* do RAGAS (Es et al., 2024); vieses do juiz em Zheng et al. (2023).

As metas foram fixadas no código (`metricas.METAS`) antes da primeira rodada.

## Conjunto de avaliação

`cenarios.json` (versão 1) tem 27 cenários, todos sobre as 7 fixtures de contexto da [0.2]:

| Grupo | Cenários | O que cobre |
| :-- | --: | :-- |
| Cronotipo e energia | 7 | as 7 fixtures como estão |
| Limiares do Pomodoro | 4 | índice 0,7, 0,4 e 0,39; noturno com energia alta |
| Prazos | 4 | prazo em 2 dias, dois prazos na terça, prazo já passado, demanda maior que a agenda |
| Carga | 2 | só baixa carga, só alta carga |
| Redução de danos | 3 | com fadiga, normal e com energia alta |
| Reajuste | 7 | as fixtures reprovadas e violações plantadas (conflito, sono, vale, refeição, sem solução) |

Cada cenário tem `esperado` com a resposta certa. Para acrescentar um cenário, basta uma entrada nova no JSON; os testes conferem que todos montam e batem com o rótulo.

## Referências

- Dunlosky, J. et al. (2013). Improving students' learning with effective learning techniques. *Psychological Science in the Public Interest*, 14(1).
- Es, S. et al. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. *EACL (demo)*.
- Gao, T. et al. (2023). Enabling Large Language Models to Generate Text with Citations (ALCE). *EMNLP*.
- Geng, S. et al. (2025). Generating Structured Outputs from Language Models: Benchmark and Studies (JSONSchemaBench). arXiv:2501.10868.
- May, C. P., & Hasher, L. (1998). Synchrony effects in inhibitory control over thought and action. *JEP: Human Perception and Performance*, 24(2).
- Minton, S. et al. (1992). Minimizing conflicts: a heuristic repair method for constraint satisfaction and scheduling problems. *Artificial Intelligence*, 58.
- Pinedo, M. (2016). *Scheduling: Theory, Algorithms, and Systems* (5ª ed.). Springer.
- Schmidt, C. et al. (2007). A time to think: circadian rhythms in human cognition. *Cognitive Neuropsychology*, 24(7).
- Xie, J. et al. (2024). TravelPlanner: A Benchmark for Real-World Planning with Language Agents. *ICML*.
- Zheng, H. S. et al. (2024). NATURAL PLAN: Benchmarking LLMs on Natural Language Planning. arXiv:2406.04520.
- Zheng, L. et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. *NeurIPS*.
- DeepEval: https://docs.confident-ai.com/docs/metrics-introduction
- Base de artigos do projeto: `api/data/artigo_*.txt`.
