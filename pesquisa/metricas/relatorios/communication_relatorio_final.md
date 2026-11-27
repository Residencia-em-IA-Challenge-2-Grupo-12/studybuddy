# Relatório final — Communication Agent

Fechamento da issue [#52](https://github.com/Residencia-em-IA-Challenge-2-Grupo-12/studybuddy/issues/52). Avalia o Communication Agent (issue [#20](https://github.com/Residencia-em-IA-Challenge-2-Grupo-12/studybuddy/issues/20)) com as métricas definidas na [#51](https://github.com/Residencia-em-IA-Challenge-2-Grupo-12/studybuddy/issues/51), sobre o conjunto de 25 cenários de `metricas/agentes/communication/cenarios.json`.

## Configuração da rodada

| Item | Valor |
| :--- | :--- |
| Gerador | `qwen3:8b` (temperatura 0, raciocínio desligado) |
| Juiz | `gemma3:12b` (modelo diferente do gerador) |
| Cenários | 25 |
| Grade | 3 blocos (segunda 19:00–20:00, quarta 20:00–21:00, sexta 19:30–21:00) |
| Evidências | `artigo_05_sleep.txt`, `artigo_19_clt.txt` |
| Máquina | Darwin 27.0.0, arm64, 24 GB de RAM, Ollama local |
| Data | 2026-11-25 |

Arquivos desta rodada:

- `communication_qwen3_8b.json` — resultados completos (por cenário e agregados)
- `communication_qwen3_8b.csv` — uma linha por cenário
- `communication_qwen3_8b.md` — relatório automático do runner
- `communication_respostas_qwen3_8b.json` — saídas brutas do gerador
- `communication_relatorio_final.md` — este documento

## Tabela-resumo

| Métrica | Meta | Resultado | Atingiu? |
| :--- | ---: | ---: | :---: |
| Fidelidade ao plano | 1,0 | **1,0** | sim |
| Planos fiéis (todos os blocos, na ordem) | 1,0 | **1,0** | sim |
| Horários inventados | 0 | **0** | sim |
| Citações válidas | 1,0 | **1,0** | sim |
| Citações inválidas | 0 | **0** | sim |
| Adequação do tom (juiz) | ≥ 0,8 | **0,98** | sim |
| Tom pela regra | 1,0 | **1,0** | sim |
| Faithfulness (juiz) | ≥ 0,9 | **0,7733** | **não** |
| Clareza (Flesch-PT) | ≥ 50 | **69,5** (mediana) | sim |
| Latência p95 | ≤ 30 s | **7,995 s** | sim |

**Resumo:** 9 de 10 métricas bateram a meta. A única abaixo é a faithfulness (0,77 contra 0,90), e a análise mostra que a causa é majoritariamente de escopo da métrica, não invenção de fato (ver seção 8).

## 1. Fidelidade ao plano

**Definição.** Fração de blocos da grade reproduzidos com dia, horário, disciplina e material exatos.

**Método.** Para cada cenário, o runner procura no Markdown a linha exata que a grade deveria gerar (ex.: `- segunda, 19:00-20:00: Matemática. Material: [...]`). Um bloco só conta se a linha inteira aparecer. São 3 blocos × 25 cenários = 75 blocos possíveis.

**Resultado.** 1,0 — 75 de 75 blocos presentes.

**Análise.** O plano é montado por código a partir da `PropostaGrade`, não pelo LLM. O resultado confirma que o formatador não altera horário, disciplina nem material. Como é determinístico, a métrica funciona como teste de regressão.

**Próximos passos.** Ampliar o conjunto com grades maiores, blocos no mesmo dia e material ausente, para cobrir casos que a grade única de 3 blocos não exercita.

## 2. Planos fiéis (todos os blocos, na ordem)

**Definição.** Fração de cenários em que todos os blocos aparecem **e** na ordem aprovada.

**Método.** Além da presença, compara as posições das linhas no texto; se a ordem foi embaralhada, o cenário não é fiel mesmo com todos os blocos presentes.

**Resultado.** 1,0 — 25 de 25 cenários fiéis.

**Análise.** Nenhum cenário teve bloco ausente ou fora de ordem. A ordem do plano é estável porque vem da iteração sobre a lista de blocos da grade.

**Próximos passos.** Nenhum para o formato atual. A cobertura cresce junto com a ampliação da grade (seção 1).

## 3. Horários inventados

**Definição.** Horários citados na abertura que não existem na grade aprovada.

**Método.** Aplica a regex `\b\d{1,2}:\d{2}\b` apenas na abertura escrita pelo LLM (o plano não entra) e subtrai o conjunto de horários de início e fim da grade.

**Resultado.** 0 horários inventados nos 25 cenários.

**Análise.** O agente não citou horários novos: qualquer `HH:MM` presente na abertura coincide com a grade. Isso é coerente com o prompt, que separa o plano (montado por código) da abertura (texto do mentor).

**Próximos passos.** Manter a checagem; ela pega regressões se o prompt passar a pedir que o LLM repita horários.

## 4. Citações válidas

**Definição.** Fração de citações rastreáveis que apontam para artigos entregues ao agente.

**Método.** Mesma convenção do verificador da API (`rag/verificador.py`): conta `[Fonte: artigo_NN]` e compara com os artigos das evidências. Citação a artigo fora das evidências é inválida.

**Resultado.** 1,0 — todas as citações apontaram para `artigo_05` ou `artigo_19`.

**Análise.** O agente só citou os artigos disponíveis. A verificação é feita pelo próprio verificador da API, não por uma reimplementação, então o resultado reflete o comportamento real do serviço.

**Próximos passos.** Incluir cenários em que a evidência relevante não existe, para testar se o agente prefere não citar a inventar.

## 5. Citações inválidas

**Definição.** Citações removidas pelo verificador (`fora_do_contexto`).

**Método.** Contagem direta do que o verificador da API classificou como fora do contexto entregue.

**Resultado.** 0 citações inválidas nos 25 cenários.

**Análise.** Nenhum artigo inventado. Junto com a seção 4, indica que a instrução de citação está sendo obedecida.

**Próximos passos.** Nenhum imediato; a seção 4 cobre a evolução do conjunto.

## 6. Adequação do tom (juiz)

**Definição.** Se o tom da abertura combina com o estado do check-in, numa rubrica de 0 a 2.

**Método.** O juiz `gemma3:12b` recebe check-in, tom esperado e abertura, e devolve JSON com `nota` (0, 1 ou 2) e justificativa. A nota é normalizada em Python (`nota / 2`) e agregada por média.

**Resultado.** 0,98 — 24 cenários com nota 2 e 1 com nota 1.

**Análise.** O único caso abaixo do máximo foi `estresse_limite`: o juiz considerou a sugestão "começar o dia com um sono mais reparador" direta demais para alguém já exausto, embora tenha reconhecido que a mensagem acolhe e incentiva. Ou seja, a classificação de tom está correta; o que o juiz penalizou foi a formulação de uma solução imediata. Isso é útil: mostra que a rubrica distingue "tom certo" de "redação do tom".

**Próximos passos.** Ajustar o prompt para, em check-ins de estresse/fadiga altos, validar o estado antes de propor solução. Reavaliar com o mesmo juiz e comparar.

## 7. Tom pela regra

**Definição.** Se `MensagemFinal.tom` é igual ao tom esperado pelo cenário.

**Método.** Comparação direta entre o tom que o agente registrou e o rótulo do `cenarios.json`.

**Resultado.** 1,0 — 25 de 25 acertos.

**Análise.** Métrica de regressão, não de qualidade: confirma que `escolher_tom` continua reproduzindo os rótulos, inclusive nos casos de fronteira e de precedência (humor baixo vence alta energia). A qualidade do tom fica com a seção 6.

**Próximos passos.** Nenhum; a regra está coberta também pelos testes de integridade do conjunto.

## 8. Faithfulness (juiz)

**Definição.** Fração das afirmações da abertura sustentadas pelas evidências entregues ao agente (estilo RAGAS).

**Método.** O juiz quebra a abertura em afirmações e marca cada uma como sustentada ou não pelos trechos de `artigo_05` e `artigo_19`. O score do cenário é `sustentadas ÷ total`; o agregado é a média dos cenários.

**Resultado.** 0,7733 (meta 0,9) — **abaixo**. Foram 52 afirmações sustentadas de 64 (81,25% no micro-agregado); 10 dos 25 cenários ficaram abaixo de 0,9. Casos mais baixos: `misto` (0/2), `estresse_limite` (1/3), e vários com 1/2.

**Análise.** As 12 afirmações não sustentadas caem em duas categorias:

1. **Encorajamento genérico (8):**
   - "Pequenas conquistas são importantes" — `estresse_alto`, `estresse_limite`, `misto`;
   - "Pequenas conquistas fazem toda a diferença" — `exausto_fim_de_semana`;
   - "Cuidar da sua saúde é parte essencial do processo" — `estresse_limite`;
   - "Dormir bem é um grande passo." — `humor_limite_alta_energia`;
   - "Manter um equilíbrio razoável entre os desafios do dia a dia é importante." — `neutro`;
   - "Há um equilíbrio razoável entre energia e foco." — `rotina_estavel`.

2. **Reformulação do check-in (4):**
   - "Você está em um bom momento, com um humor leve e estresse controlado" — `sono_curto`, `um_pouco_cansado`, `sono_ruim_humor_bom`;
   - "Mesmo que o sono tenha sido difícil, você já está aqui, pronto para aprender." — `misto`.

A causa provável é de **escopo da métrica**, não de invenção de fato. O juiz de faithfulness recebe apenas os trechos das evidências — não recebe o check-in. Assim, frases que refletem o estado informado pelo estudante (categoria 2) são corretamente verdadeiras no contexto da conversa, mas não têm como ser sustentadas por `artigo_05`/`artigo_19`. Já as frases da categoria 1 são encorajamento, não afirmação factual, e o prompt do juiz não as distingue de uma alegação que exigiria fonte.

**Próximos passos.**
- Passar o check-in ao juiz como contexto adicional, para que reformulações do estado não contem como não sustentadas;
- Instruir o juiz a ignorar encorajamento genérico e só avaliar afirmações factuais;
- Alternativa complementar: separar "faithfulness factual" (só o que exige fonte) de "aderência ao check-in" (o que o agente diz sobre o estado do estudante);
- Re-medir e comparar antes/depois, mantendo o mesmo juiz.

## 9. Clareza (Flesch-PT)

**Definição.** Facilidade de leitura da abertura.

**Método.** Remove citações, links e marcação de Markdown; conta palavras (regex de letras), frases (divisão em `.`, `!`, `?`) e sílabas (aproximação por grupos de vogais). Aplica `248,835 − 1,015 × (palavras/frases) − 84,6 × (sílabas/palavras)`.

**Resultado.** Mediana 69,5; mínimo 52,7 (`quase_limite`); máximo 84,5 (`humor_limite_alta_energia`). Todos os cenários acima da meta de 50.

**Análise.** As aberturas são curtas e diretas. O mínimo de 52,7 ainda é leitura "fácil" pela escala; não há caso de texto difícil. A variação acompanha o tamanho e a estrutura das frases, não o tom.

**Próximos passos.** Nenhum para o texto atual. Se o prompt de tom mudar (seção 6), re-medir para garantir que a clareza não caiu.

## 10. Latência p95

**Definição.** Tempo da chamada ao LLM por cenário, no percentil 95.

**Método.** Cada chamada é cronometrada com `time.perf_counter`; o agregado usa interpolação linear no p95.

**Resultado.** p50 de 6,58 s, p95 de 7,995 s, mínimo de 5,22 s e máximo de 11,34 s (o primeiro cenário, que inclui o carregamento do modelo).

**Análise.** Bem abaixo da meta de 30 s, com pouca dispersão depois do aquecimento. O valor é específico desta máquina (24 GB de RAM, Ollama local) e não é transferível para outro hardware.

**Próximos passos.** Repetir a medição no ambiente de apresentação e registrar o hardware, como já feito aqui.

## Limitações

- **Dados sintéticos:** 25 check-ins não cobrem a variabilidade real de humor e rotina.
- **Grade única:** a fidelidade é testada com 3 blocos; grades maiores e blocos no mesmo dia ainda não estão no conjunto.
- **Faithfulness de escopo restrito:** o juiz vê só as evidências, não o check-in; por isso penaliza reformulações legítimas do estado. A meta de 0,9 não foi atingida, e a análise acima separa o que é limitação da métrica do que é comportamento do agente.
- **Flesch-PT aproximado:** a contagem de sílabas é por grupos de vogais, não por silabação real.
- **Viés do juiz:** o juiz é um modelo diferente do gerador (evita autopreferência), mas verbosidade e idiossincrasias do `gemma3:12b` continuam possíveis. A calibração contra leitura humana fica para a etapa de kappa de Cohen.
- **Latência dependente do hardware:** os tempos valem para esta máquina e esta carga do Ollama.
- **Um modelo por rodada:** esta rodada avalia o agente com `qwen3:8b`; a comparação entre modelos é da issue [#58](https://github.com/Residencia-em-IA-Challenge-2-Grupo-12/studybuddy/issues/58).

## Como reproduzir

Um único comando, a partir de `pesquisa/`:

```bash
PYTHONPATH=. python -m metricas.agentes.communication.runner --nome qwen3_8b
```

O runner gera as respostas, roda as métricas determinísticas e o juiz, e grava JSON/CSV/MD em `metricas/agentes/communication/saidas/`. Para trocar o juiz:

```bash
OLLAMA_JUIZ_MODEL=outro:modelo PYTHONPATH=. python -m metricas.agentes.communication.runner --nome qwen3_8b
```

Para rodar só as métricas determinísticas (sem juiz):

```bash
PYTHONPATH=. python -m metricas.agentes.communication.runner --nome qwen3_8b --sem-juiz
```

Os arquivos deste relatório são cópias versionadas das saídas dessa execução.
