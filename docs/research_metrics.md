# Métricas do Research Agent: Pesquisa e Definição ([2.6] Issue #41)

O **Research Agent** é o agente bibliotecário e montador de contexto do sistema multiagente. Ele possui duas frentes:

1. **Montagem Determinística do `ContextoEstudante` e Integração Externa (sem LLM):** persiste o perfil, acervo e histórico no banco do estudante (`RepositorioEstudante` SQLite, `[2.1]`), converte as escalas do check-in e calcula o `indice_capacidade` (`[2.2]`), deriva as janelas circadianas (`picos`, `vales`, `sono` com quebra na meia-noite e `refeicoes`, `[2.2]`) e lê/grava blocos de estudo no Google Calendar (`ProvedorAgenda`, `[2.4]`).
2. **Recuperação no Acervo Científico (ChromaDB RAG) e Curadoria via Modelo Local (com LLM):** formula consultas semânticas calibradas pelo cronotipo, check-in e carga cognitiva (`[2.3]`), recupera os trechos mais próximos no ChromaDB respeitando o porteiro de distância Euclidiana ($L_2$, $\tau = 1.026$) e sintetiza a orientação bibliotecária (`SaidaResearchLLM`) com citações conferidas pelo verificador determinístico (`[2.5]`).

Por isso, a avaliação é dividida em **9 métricas determinísticas e de recuperação (IR/RAG)** e **5 métricas de curadoria por LLM local**, implementadas em [`pesquisa/metricas/agentes/research/metricas.py`](../pesquisa/metricas/agentes/research/metricas.py) e executadas por [`pesquisa/metricas/agentes/research/runner.py`](../pesquisa/metricas/agentes/research/runner.py) sobre os **22 cenários** de [`pesquisa/metricas/agentes/research/cenarios.json`](../pesquisa/metricas/agentes/research/cenarios.json).

```bash
# A partir de pesquisa/
python -m metricas.agentes.research.runner                          # determinístico + RAG (sem Ollama)
python -m metricas.agentes.research.runner --llm llama3.1:8b        # + curadoria pelo LLM local
python -m metricas.agentes.research.runner --llm llama3.1:8b --juiz # + fidelidade pelo LLM-juiz
python -m pytest -q metricas/agentes/research                       # testes unitários das métricas
```

---

## 1. Métricas Determinísticas de Contexto, Banco, Ritmo Circadiano e Agenda

### 1.1. Validade do Contrato `ContextoEstudante` (`contrato_valido`)
- **Definição:** o objeto `ContextoEstudante` produzido por `AgenteResearch.montar_contexto()` valida integralmente no JSON Schema do contrato da `[0.1]` (`extra="forbid"`, tipos `date` e `time`, invariantes `inicio < fim` em todas as janelas e `0 <= indice_capacidade <= 1`).
- **Fórmula:** $\frac{\text{contextos válidos no round-trip JSON}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.
- **Fonte:** JSONSchemaBench (Geng et al., 2025); contrato `api/app/modules/agentes/contratos.py`.

### 1.2. Integridade da Persistência SQLite (`persistencia_integra`)
- **Definição:** o snapshot de `ContextoEstudante`, a lista ordenada de `Material` e o último `RegistroCheckIn` salvos em `RepositorioEstudante` são recuperados do banco SQLite sem perda ou mutação de campos.
- **Fórmula:** $\frac{\text{cenários com round-trip SQLite idêntico}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.

### 1.3. Integridade de Janelas Circadianas e Sono (`integridade_circadiana`)
- **Definição:** nenhuma `Janela` cruza a meia-noite (`inicio < fim`); horários de sono que cruzam `00:00` (ex.: `22:00`–`06:00`) são quebrados em 2 janelas diárias (`22:00`–`23:59` e `00:00`–`06:00`), enquanto sono intradia (`02:00`–`10:00` do cronotipo `noturno`) permanece em 1 janela; e as janelas de `picos` e `vales` correspondem ao cronotipo (`matutino`: pico `08:00`–`11:00`, vale `13:00`–`15:00`; `vespertino`: pico `15:30`–`18:30`, vale `13:30`–`15:00`; `noturno`: pico `19:30`–`22:30`, vale `14:00`–`16:00`), com realocação automática quando o expediente bloqueia o pico padrão (`agenda_cheia`: `06:00`–`07:00` e `19:00`–`20:30`).
- **Fórmula:** $\frac{\text{cenários com janelas circadianas íntegras}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.
- **Fonte:** Roenneberg et al. (2007), *Epidemiology of the human circadian clock*; Schmidt et al. (2007); base `artigo_05`, `artigo_14` e `artigo_19`.

### 1.4. Precisão do Check-in e Índice de Capacidade (`precisao_capacidade`)
- **Definição:** o mapeamento das 4 escalas da UI (`energia = 6 - fadiga`, `estresse`, `horas_sono`) e o cálculo do `indice_capacidade` $\in [0, 1]$ e de sua classe operacional (`alta_energia` $\ge 0.70$, `normal` $\in [0.40, 0.70)$, `fadiga` $< 0.40$) reproduzem exatamente o gabarito das fixtures da `[0.2]` (`0.90`, `0.60`, `0.20`) e os limiares intermediários.
- **Fórmula:** $\frac{\text{cenários com índice e estado exatos}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.
- **Fonte:** Modelo de Dois Processos da Regulação do Sono (Borbély, 1982); Walker (2009, `artigo_05`); Baumeister et al. (1998, `artigo_14`).

### 1.5. Consistência de Leitura e Escrita da Agenda (`consistencia_agenda`)
- **Definição:** o `ProvedorAgenda` (`GoogleCalendarProvedor` / `AgendaFake`) filtra eventos cancelados (`status="cancelled"`), divide eventos noturnos que cruzam a meia-noite em janelas diárias válidas e grava `BlocoEstudo` retornando IDs de eventos criados.
- **Fórmula:** $\frac{\text{cenários com leitura e sincronização válidas}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.

---

## 2. Métricas de Recuperação no Acervo Científico (ChromaDB RAG)

### 2.1. Acurácia do Porteiro de Distância L2 (`porteiro_ok`)
- **Definição:** consultas dentro do domínio de estudos/produtividade passam pelo porteiro ($d_1 \le \tau$, com $\tau = 1.026$ para `bge-m3`) e retornam evidências científicas, enquanto consultas fora de escopo ($d_1 > \tau$, ex.: receita culinária) são barradas imediatamente com 0 chamadas ao LLM.
- **Fórmula:** $\frac{\text{decisões corretas do porteiro}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **$\ge 95\%$**.
- **Fonte:** calibração do porteiro da Semana 3 (`pesquisa/relatorio/final/03-decisao.md`).

### 2.2. Hit Rate@4 de Evidências Científicas (`hit_rate`)
- **Definição:** proporção dos cenários dentro do escopo em que ao menos um dos artigos científicos canônicos esperados para o perfil/dor do estudante está presente nos Top-4 fragmentos recuperados pelo Research Agent (`K = 4`, filtrando chunks puramente bibliográficos de cabeçalho).
- **Fórmula:** $\frac{1}{|Q|} \sum_{q \in Q} \mathbb{I}(\text{Top-4}(q) \cap \text{Gabarito}(q) \neq \emptyset)$. **Faixa:** 0–100%. **Meta:** **$\ge 90\%$**.
- **Fonte:** Manning, Raghavan & Schütze (2008), *Introduction to Information Retrieval*.

### 2.3. Mean Reciprocal Rank (`mrr`)
- **Definição:** média do inverso da posição ($\frac{1}{\text{rank}}$) do primeiro artigo relevante recuperado entre os Top-4 trechos de cada cenário. Mede se a evidência mais importante aparece logo no topo.
- **Fórmula:** $\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \frac{1}{\text{rank}_q}$. **Faixa:** 0–100%. **Meta:** **$\ge 80\%$**.
- **Fonte:** Voorhees (1999), *TREC-8 Question Answering Track Report*.

### 2.4. Acerto Integral do Cenário Esperado (`rotulo`)
- **Definição:** o cenário cumpre simultaneamente o contrato, a integridade circadiana, o índice de capacidade, a inferência de carga cognitiva de novos materiais, a consistência do Google Calendar, o porteiro L2 e o Hit Rate@4.
- **Fórmula:** $\frac{\text{cenários sem nenhuma divergência}}{\text{cenários}}$. **Faixa:** 0–100%. **Meta:** **100%**.

---

## 3. Métricas da Curadoria Bibliotecária por Modelo Local (`--llm`)

### 3.1. JSON Válido no Contrato `SaidaResearchLLM` (`json_valido`)
- **Definição:** a resposta bruta do LLM valida em `SaidaResearchLLM` (`foco_recomendado`, `orientacao_circadiana`, `sintese_evidencias`, com `extra="forbid"`).
- **Fórmula:** $\frac{\text{respostas JSON válidas}}{\text{chamadas}}$. **Meta:** **$\ge 95\%$**.
- **Fonte:** JSONSchemaBench (Geng et al., 2025).

### 3.2. Citação Válida Após Verificador (`citacao_valida`)
- **Definição:** após a passagem pelo verificador determinístico (`api/app/modules/rag/verificador.py`), resta ao menos uma citação `[Fonte: artigo_XX...]` pertencente aos fragmentos efetivamente entregues no prompt.
- **Fórmula:** $\frac{\text{curadorias com citação válida}}{\text{cenários in-scope}}$. **Meta:** **$\ge 95\%$**.
- **Fonte:** ALCE (Gao et al., 2023).

### 3.3. Precisão das Citações (`citacoes_mantidas`)
- **Definição:** fração das citações emitidas pelo modelo que correspondem a artigos presentes no contexto recebido (citações inventadas ou fora do contexto são removidas pelo verificador e penalizam a precisão).
- **Fórmula:** $\frac{|\text{citações mantidas}|}{|\text{citações mantidas}| + |\text{citações fora do contexto}|}$. **Meta:** **$\ge 95\%$**.
- **Fonte:** *Citation Precision* do ALCE (Gao et al., 2023).

### 3.4. Aderência ao Cronotipo e ao Estado do Check-in (`aderencia_cronotipo`)
- **Definição:** a recomendação gerada respeita simultaneamente o cronotipo do estudante (`matutino`, `vespertino`, `noturno` e suas faixas de pico) e o regime de capacidade do check-in (`alta_energia` com blocos de 50 min/foco profundo, `normal` com blocos sustentáveis de 25 min, ou `fadiga` com redução de carga e proteção do sono).
- **Fórmula:** $\frac{\text{curadorias aderentes ao cronotipo e estado}}{\text{cenários in-scope}}$. **Meta:** **$\ge 90\%$**.
- **Fonte:** *Synchrony Effect* (May & Hasher, 1998); Schmidt et al. (2007).

### 3.5. Fidelidade ao Contexto (`fidelidade`)
- **Definição:** proporção das afirmações da curadoria que são diretamente sustentadas pelos dados do perfil/check-in ou pelos trechos científicos recuperados, avaliada pelo LLM-juiz (`pesquisa/metricas/geracao/juiz.py`, sempre de família distinta do modelo avaliado).
- **Fórmula:** $\frac{\text{afirmações sustentadas}}{\text{total de afirmações}}$. **Faixa:** 0–100%. **Meta:** **$\ge 85\%$**.
- **Fonte:** *Faithfulness* do RAGAS (Es et al., 2024); Zheng et al. (2023).

---

## 4. Conjunto de Avaliação (`cenarios.json`)

O arquivo [`pesquisa/metricas/agentes/research/cenarios.json`](../pesquisa/metricas/agentes/research/cenarios.json) contém **22 cenários** distribuídos em 6 grupos:

| Grupo | Cenários | O que avalia |
| :-- | --: | :-- |
| **1. Fixtures Canônicas da `[0.2]`** | 7 | `matutino`, `vespertino`, `noturno`, `alta_energia`, `fadiga`, `agenda_cheia` (CLT), `prazo_apertado` |
| **2. Mapeamento das 4 Escalas da UI** | 3 | Conversão de `humor`, `estresse`, `sono` e `fadiga` + `horas_sono` nos regimes alto (`0.90`), moderado (`0.55`) e fadiga (`0.20`) |
| **3. Limiares Fisiológicos e Privação de Sono** | 3 | Privação de sono (`5h`) com energia média, limiar de alta capacidade (`0.78`) e limiar de fadiga em agenda cheia (`0.35`) |
| **4. Acervo e Inferência de Carga Cognitiva** | 3 | Só materiais de baixa carga, só alta carga e inferência automática de carga em disciplinas novas (Estruturas de Dados vs. Espanhol) |
| **5. Integração Google Calendar** | 2 | Quebra automática de plantão noturno cruzando a meia-noite (`22:00`–`01:00`) e filtragem de eventos com `status="cancelled"` |
| **6. Personas do Projeto e Porteiro L2** | 4 | Consultas diretas das Personas 1 (Lucas CLT), 2 (Lisa Overplanning) e 3 (Bob Autodidata 80/20) + bloqueio de pergunta fora de escopo pelo porteiro L2 |

---

## 5. Referências Bibliográficas

- Borbély, A. A. (1982). A two process model of sleep regulation. *Human Neurobiology*, 1(3), 195–204.
- Es, S. et al. (2024). RAGAS: Automated Evaluation of Retrieval Augmented Generation. *EACL (System Demonstrations)*.
- Gao, T. et al. (2023). Enabling Large Language Models to Generate Text with Citations (ALCE). *EMNLP*.
- Geng, S. et al. (2025). Generating Structured Outputs from Language Models: Benchmark and Studies (JSONSchemaBench). *arXiv:2501.10868*.
- Manning, C. D., Raghavan, P., & Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press.
- May, C. P., & Hasher, L. (1998). Synchrony effects in inhibitory control over thought and action. *Journal of Experimental Psychology: Human Perception and Performance*, 24(2).
- Roenneberg, T. et al. (2007). Epidemiology of the human circadian clock. *Sleep Medicine Reviews*, 11(6), 429–438.
- Schmidt, C. et al. (2007). A time to think: circadian rhythms in human cognition. *Cognitive Neuropsychology*, 24(7).
- Voorhees, E. M. (1999). The TREC-8 Question Answering Track Report. *TREC*.
- Zheng, L. et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena. *NeurIPS*.
