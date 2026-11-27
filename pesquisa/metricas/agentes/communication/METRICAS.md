# Métricas do Communication Agent

Esta pasta define **como medir** o agente da issue [#51](https://github.com/Residencia-em-IA-Challenge-2-Grupo-12/studybuddy/issues/51). O agente tem duas partes com naturezas diferentes:

- **Plano:** montado por código a partir da `PropostaGrade` aprovada, sem LLM. A cobrança é fidelidade exata.
- **Abertura:** escrita pelo LLM com o tom escolhido pelo check-in. A cobrança é tom, sustentação nas evidências, citações e legibilidade.

O conjunto de avaliação (`cenarios.json`) roda contra as fixtures da `0.2` (`pesquisa/fixtures/communication/`), sem depender do Maestro, do Research, do Analysis ou do Validation.

## Conjunto de avaliação

- **25 cenários** de check-in (humor, estresse, sono e fadiga, de 1 a 5), rotulados com o tom esperado.
- A mesma `grade.json` aprovada em todos os cenários: o agente **não pode** alterá-la.
- As mesmas `evidencias.json`: só esses dois artigos podem ser citados.
- Os rótulos de tom foram conferidos contra a regra real do agente (`communication.escolher_tom`), inclusive nos casos de fronteira e de precedência (humor baixo vence alta energia).

O conjunto é sintético e pequeno por decisão de escopo: serve para regressão e para comparar modelos, não para estimar desempenho em produção.

## Definições

| Métrica | Definição | Fórmula | Faixa | Meta | Conta como erro | Fonte |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Fidelidade ao plano** | fração de blocos da grade reproduzidos com dia, horário, disciplina e material exatos | blocos corretos ÷ total de blocos | 0–1 | 1,0 | bloco ausente, horário alterado ou material trocado | contrato da `0.1` e regra do agente |
| **Planos fiéis** | fração de cenários em que todos os blocos aparecem **e** na ordem aprovada | cenários fiéis ÷ total | 0–1 | 1,0 | qualquer bloco fora de ordem conta como alteração | regra do agente |
| **Horários inventados** | horários citados na abertura que não existem na grade | contagem de `HH:MM` da abertura − horários da grade | inteiro ≥ 0 | 0 | qualquer horário fora da grade | regra do agente |
| **Citações válidas** | fração de citações rastreáveis que apontam para artigos entregues ao agente | citações válidas ÷ citações totais | 0–1 | 1,0 | citar `artigo_NN` que não está nas evidências | `rag/verificador.py`; convenção de [Es et al., 2023] |
| **Citações inválidas** | citações removidas pelo verificador | contagem em `fora_do_contexto` | inteiro ≥ 0 | 0 | qualquer citação inventada | `rag/verificador.py` |
| **Adequação do tom (juiz)** | o tom da abertura combina com o estado do check-in | média das notas 0–2, normalizada para 0–1 | 0–1 | ≥ 0,8 | tom oposto ao estado (nota 0) | rubrica própria, inspirada em [Zheng et al., 2023] e [Liu et al., 2023] |
| **Tom pela regra** | `MensagemFinal.tom` é igual ao tom esperado | acertos ÷ total | 0–1 | 1,0 | divergência entre a regra e o rótulo | regra do agente |
| **Faithfulness (juiz)** | fração das afirmações da abertura sustentadas pelas evidências | afirmações sustentadas ÷ total | 0–1 | ≥ 0,9 | afirmação sem apoio nos trechos | [Es et al., 2023] |
| **Clareza (Flesch-PT)** | facilidade de leitura da abertura | 248,835 − 1,015 × (palavras/frases) − 84,6 × (sílabas/palavras) | 0–100 | ≥ 50 | abaixo de 50 = leitura difícil | [Flesch, 1948]; adaptação de [Martins et al., 1996] |
| **Latência p95** | tempo da chamada ao LLM por cenário | percentil 95 das latências | segundos | ≤ 30 s | p95 acima da meta no hardware de referência | prática de avaliação de sistemas interativos |

Metas numéricas ficam em `runner.py` (`METAS`) e aparecem no relatório de cada execução.

RAGAS e DeepEval são as ferramentas de referência para faithfulness e métricas de RAG. As fórmulas deste módulo foram implementadas à mão (stdlib puro) para o runner não ganhar dependência extra, seguindo as mesmas definições.

## Métricas pesquisadas e não incluídas nesta entrega

| Métrica | Por quê não agora | Fonte |
| :--- | :--- | :--- |
| **Usabilidade da web (SUS)** | depende das telas da `5.3`, que ainda não existem | [Brooke, 1996] |
| **Concordância juiz × humano (kappa)** | exige a amostra avaliada pelo grupo; entra no relatório final da `5.5` | [Cohen, 1960] |
| **Precisão/recall de fatos** | o Communication não responde perguntas; ele comunica um plano já aprovado | — |

## Método

1. **Gerar** (`--so-gerar`): o agente roda cada cenário com o modelo configurado em `OLLAMA_COMMUNICATION_MODEL`. A saída bruta e a latência ficam em `saidas/communication_respostas_<nome>.json`.
2. **Avaliar** (`--so-avaliar`): as métricas determinísticas são calculadas sobre o texto salvo; o juiz, quando habilitado, roda em modelo **diferente** do gerador (padrão `gemma3:12b` julgando `qwen3:8b`).
3. **Agregar**: médias, medianas e percentis vão para `saidas/communication_<nome>.json`, `.csv` e `.md`.

Comandos, a partir de `pesquisa/`:

```bash
python -m metricas.agentes.communication.runner --nome qwen3_8b
python -m metricas.agentes.communication.runner --nome smoke --limite 3
python -m metricas.agentes.communication.runner --nome qwen3_8b --sem-juiz
python -m pytest metricas/agentes/communication/test_metrics.py
```

## Cuidados com o juiz

O LLM-juiz não é neutro. A literatura documenta três vieses que afetam esta avaliação ([Zheng et al., 2023]):

- **autopreferência:** o juiz tende a favorecer texto do próprio modelo — por isso o juiz nunca é o gerador;
- **verbosidade:** textos mais longos parecem melhores — por isso a rubrica de tom pede só o tom, e a clareza é medida à parte;
- **posição:** a ordem das respostas muda a nota — aqui cada abertura é julgada isoladamente, então o viés de posição não entra, mas o de autopreferência e o de verbosidade continuam possíveis.

A nota do juiz é sempre calculada em Python a partir do veredito estruturado, nunca pedida em texto livre. A calibração contra leitura humana fica para a `5.5`, com kappa de Cohen.

## Limitações

- **Dados sintéticos:** 25 check-ins não cobrem a variabilidade real de humor e rotina.
- **Grade única:** a fidelidade ao plano é testada com uma grade de três blocos; grades maiores ou com blocos no mesmo dia ainda não estão no conjunto.
- **Flesch-PT** é uma aproximação: a contagem de sílabas é por grupos de vogais, não por silabação real.
- **Um modelo por rodada:** a comparação entre modelos é da issue `5.0`; aqui o objetivo é medir o agente, não escolher modelo.
- **Tom esperado vem da regra:** a métrica "tom pela regra" mede regressão, não qualidade. A qualidade do tom fica com a rubrica do juiz e, depois, com a leitura humana.

## Referências

- BROOKE, J. **SUS: A quick and dirty usability scale.** In: Usability Evaluation in Industry, 1996.
- COHEN, J. **A coefficient of agreement for nominal scales.** Educational and Psychological Measurement, v. 20, n. 1, 1960.
- DEEPEVAL. **The Open-Source LLM Evaluation Framework.** Confident AI, 2024.
- ES, S.; JAMES, J.; ESPINOSA-ANKE, L.; SCHOCKAERT, S. **RAGAS: Automated Evaluation of Retrieval Augmented Generation.** arXiv:2309.15217, 2023.
- FLESCH, R. **A new readability yardstick.** Journal of Applied Psychology, v. 32, n. 3, 1948.
- LIU, Y. et al. **G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.** arXiv:2303.16634, 2023.
- MARTINS, T. B. F. et al. **Readability formulas applied to textbooks in Brazilian Portuguese.** Notas do ICMC-USP, 1996.
- ZHENG, L. et al. **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.** arXiv:2306.05685, 2023.
