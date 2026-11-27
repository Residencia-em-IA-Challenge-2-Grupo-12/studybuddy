# Análise de lacunas — fluxo de estudo (onboarding → check-in → plano)

Status: **análise, nenhuma linha de código escrita para esta issue**.
Data: 2026-11-26
Base: branch `feat/tela-assistente` (a partir de `origin/develop`), onde a tela do assistente já está pronta.
Escopo: frontend em `web/`. Nenhuma fase altera `api/`.

---

## 0. O veredito, medido

A issue pede seis itens. Nesta branch, **um está pronto, um está parcial e quatro não existem**.

| Item da issue | Status | Evidência |
|---|---|---|
| Onboarding (cronotipo, sono, refeição, "Conectar Google Calendar") | **ausente** | `web/src/app/` tem três arquivos e uma rota; `grep` por `cronotipo`/`onboarding` em `web/src` não retorna nada |
| Check-in diário (humor, estresse, sono, fadiga) | **ausente** | idem |
| Materiais (cadastro e lista: disciplina, dificuldade, prazo) | **ausente** | idem |
| Plano semanal (grade por dia, mensagem do mentor, confirmar e sincronizar) | **ausente** | o que existe é a resposta em texto do pipeline `agentes`; não há grade nem ação de sincronizar |
| Bloqueios de guardrail sem parecer erro | **feito** | `.recusa` com tom neutro, título "Pedido bloqueado", causa por origem, sem `role="alert"`; default-deny para categoria futura (`modules/assistente/veredito.ts`) |
| Camada de API com mocks da [0.2], trocável por variável de ambiente | **parcial** | existem `lib/api.ts`, `modules/assistente/service.ts` e `NEXT_PUBLIC_API_URL`; mas os mocks estão em `/tmp/sb-stub`, **fora do repo**, e vêm de `api/demo.py`, **não** das fixtures da [0.2] |

Critérios de aceite:

| Critério | Status |
|---|---|
| Fluxo navegável só com mocks: onboarding → check-in → plano → confirmar | **não** — três das quatro telas não existem e o app tem uma rota só |
| Layout funciona no celular | **sim, mas só da tela do assistente** (390×844 sem overflow, provado nas Fases 3 e 7 do plano anterior) |

O que foi construído é a **tela do assistente** (formulário, resposta, fontes, citações, detalhes, erros). Ela encosta nesta issue apenas no item 5.

### 0.1 O backend já tem os contratos, mas não tem as rotas

`api/app/modules/agentes/contratos.py` já define exatamente os modelos deste fluxo:

| Modelo | Campos | Consumidor |
|---|---|---|
| `ContextoEstudante` | `estudante_id`, `cronotipo` (`matutino`/`vespertino`/`noturno`), `semana_inicio`, `livres[]`, `ocupados[]`, `picos[]`, `vales[]`, `sono[]`, `refeicoes[]`, `materiais[]`, `checkin`, `indice_capacidade` | Analysis, Validation, Communication |
| `CheckIn` | `energia` (1–5), `horas_sono` (0–24), `estresse` (1–5) | Research |
| `Material` | `id`, `disciplina`, `titulo`, `carga` (`alta`/`baixa`), `horas_estimadas`, `dificuldade` (1–5), `prazo` | Research |
| `PropostaGrade` | `estudante_id`, `semana_inicio`, `modo` (`normal`/`reducao_danos`), `blocos[]`, `fora_da_grade[]`, `iteracao` | Validation, Communication |
| `BlocoEstudo` | `id`, `dia`, `inicio`, `fim`, `disciplina`, `material_id`, `carga`, `tecnica`, `foco_min`, `pausa_min`, `justificativa`, `fontes[]` | Validation, Communication |
| `ResultadoValidacao` | `status` (`APROVADO`/`REPROVADO`), `violacoes[]` | Maestro, Analysis |
| `MensagemFinal` | `markdown`, `tom`, `links[]` | Maestro, **web** |

E as fixtures da [0.2] existem no repositório — **são elas que o item 6 manda usar**:

- `api/tests/fixtures/contexto/` — `matutino`, `vespertino`, `noturno`, `fadiga`, `agenda_cheia`, `alta_energia`, `prazo_apertado`
- `api/tests/fixtures/proposta/` — `valida`, `violacoes`, `reducao_danos`, `higiene_sono`, `refeicao`, `sobrecarga_fadiga`, `sobrecarga_noturna`
- `api/tests/fixtures/resultado/` — `aprovado`, `reprovado`, `sobrecarga`
- `pesquisa/fixtures/communication/` — `checkins`, `evidencias`, `grade`

O que **não** existe é rota HTTP para nenhum deles: a API expõe `/assistente/info`, `/assistente/perguntar` e `/examples`. Portanto a issue só pode ser cumprida com mock — o que, aliás, é o critério de aceite.

### 0.2 Três divergências entre a issue e o contrato

Estas precisam de decisão antes da Fase 2; não são detalhe de implementação.

1. **Check-in tem 3 campos no contrato, 4 escalas na issue.** `CheckIn` traz `energia`, `horas_sono` e `estresse`. A issue pede "humor, estresse, sono e fadiga". Ou `humor` e `fadiga` são estado só do cliente (não vão ao backend), ou o contrato ganha campos — e aí é épico 0, não `web/`.
   A divergência não é só entre a issue e o contrato: `pesquisa/fixtures/communication/checkins.json` usa exatamente `{humor, estresse, sono, fadiga}` — são **duas famílias de fixture** no próprio repositório, e a do Communication é a que fala a língua da issue.
2. **Material pede mais campos do que a issue lista.** A issue cita disciplina, dificuldade e prazo; o contrato exige também `id`, `titulo`, `carga` (alta/baixa) e `horas_estimadas`. Sem eles o material não entra na grade.
3. **O onboarding não produz o `ContextoEstudante` inteiro.** `picos`, `vales`, `ocupados` e `indice_capacidade` são derivados pelo Research a partir de cronotipo, sono, refeições e agenda. A tela coleta a entrada; o mock precisa fabricar o resto para a grade existir.

---

## 1. Briefing

### 1.1 Stack e o que já existe

Next.js 15, React 19, TypeScript, App Router, sem framework de CSS, **sem biblioteca de estado** e **sem biblioteca de markdown** no `package.json`. Uma rota (`web/src/app/page.tsx`), um módulo (`modules/assistente`), `lib/api.ts` com `ApiError` normalizado nos três formatos do FastAPI.

Reaproveitável sem alteração: tokens e tipografia de `globals.css`, o padrão `service.ts`, o `ApiError`, o bloco `.recusa` (item 5 da issue), o botão/segmentado e o método de prova (fixtures + probe por estado).

### 1.2 O fluxo e o que cada passo produz

```
onboarding ──> check-in ──> materiais ──> plano ──> confirmar e sincronizar
   │              │             │            │              │
   └ contexto     └ CheckIn     └ Material[] └ PropostaGrade └ (escrita)
     (cronotipo,                 (contrato)    + MensagemFinal   não existe
      sono, refeições,                                         no backend
      agenda)
```

Dependência de dados é **linear**: o plano só existe com contexto + check-in + materiais. Por isso as telas não são independentes, mesmo sendo implementáveis em paralelo.

### 1.3 O ambiente real

| Item | Estado | Impacto |
|---|---|---|
| Rotas de onboarding/check-in/plano na API | **não existem** | o fluxo só é navegável com mock; a troca por API real fica preparada, não provada |
| Fixtures da [0.2] | presentes em `api/tests/fixtures` | base do mock, como a issue pede |
| `web/node_modules` | instalado (`npm ci` rodado) | — |
| CI do frontend | `npm ci` → `npx tsc --noEmit` → `npm run build` | cada fase fecha com esse job |
| Playwright | instalado em `/tmp/sb-stub`, fora do repo | as provas de navegador continuam fora do repositório |

### 1.4 Escopo de arquivos

- `web/src/app/**` (rotas novas e `layout.tsx`)
- `web/src/lib/**` (transporte e modo mock)
- `web/src/modules/{onboarding,checkin,materiais,plano}/**` (novos)
- `web/src/app/globals.css` (estilos do fluxo)
- `web/src/mocks/**` (novo — ver decisão 1)
- `web/scripts/**` (sincronização das fixtures)

`modules/assistente/**` só é tocado para extrair o que for compartilhado (o bloco de recusa), nunca para mudar comportamento.

### 1.5 Decisões que precisam do seu aval

1. **Onde os mocks vivem.** O Next não importa JSON de fora da raiz do projeto. Proposta: copiar `api/tests/fixtures` para `web/src/mocks/` por um script, com verificação de divergência (`node scripts/sincronizar-mocks.mjs --check`), de modo que mock e contrato não se separem calados. Alternativa: mover as fixtures para um pacote compartilhado — mudança maior, fora do escopo desta issue.
2. **Como o mock é escolhido.** `NEXT_PUBLIC_API_MODE=mock|real` (padrão `mock`). No modo `mock`, `api()` resolve contra `web/src/mocks` em vez de `fetch`. A API real continua selecionável por `NEXT_PUBLIC_API_URL`.
3. **Materiais é passo do fluxo?** O critério de aceite diz "onboarding → check-in → plano → confirmar" e **não
   cita materiais**, mas a grade não existe sem eles. **Decidido em 2026-11-26: materiais é passo obrigatório.**
   O caminho fica com cinco telas; sem material o plano não teria o que colocar na grade.
4. **Humor e fadiga no check-in** (ver §0.2, item 1): **decidido em 2026-11-26** — a tela coleta as quatro
   escalas da issue e mapeia para os três campos do contrato em `modules/checkin/mapeamento.ts`
   (`energia = 6 − fadiga`, `estresse` direto, `horas_sono` perguntado à parte); humor e qualidade do sono
   ficam no cliente. A inclusão dos campos em `CheckIn` continua sendo a correção definitiva, no épico 0.
5. **"Conectar Google Calendar"**: OAuth real não existe no backend (`ProvedorAgenda` é um `Protocol`). Proposta: botão com estado de conexão simulado no mock, e o texto deixando claro que a agenda é a do mock.
6. **`MensagemFinal.markdown`**: renderizar markdown exige dependência nova ou um renderizador mínimo. Proposta: renderizador mínimo (parágrafos, listas, negrito, links) sem dependência, já que o restante do projeto não tem nenhuma.

### 1.6 Tarefa

Uma rota por passo, com o fluxo navegável de ponta a ponta **sem backend**, contra as fixtures da [0.2], e responsivo até 390×844.

---

## 2. Direção visual

O sistema já existe e não muda: fundo `#F6F7F4`, tinta `#14181A`, acento `#0F5A50`, uma família, três tamanhos de corpo, coluna de 46rem. O que esta issue acrescenta:

- **Grade semanal**: no desktop, sete colunas com o dia no topo e os blocos como células com hora, disciplina e técnica. No celular, os dias empilhados (a grade de sete colunas não cabe em 390px e rolagem horizontal num calendário é pior que a leitura vertical).
- **Escalas de 1 a 5**: botões de seleção (radiogroup), não `input[type=range]` — o alvo de 44px e o teclado vêm de graça, e a leitura "1 = muito baixo" fica explícita nas pontas.
- **Blocos da grade** são células de dado, não cápsulas decorativas: fio, superfície e tipografia. A regra da skill que proíbe chip não interativo não se aplica a uma célula de calendário, mas o bloco não ganha ícone nem sombra.
- Movimento só na troca de passo (150–200ms, opacidade), desligado em `prefers-reduced-motion`.

## 3. Skills aplicadas por fase

| Fase | pstack-skill | gemini-frontend-design |
|---|---|---|
| 0. Mock e fixtures | Prove It Works: o mock é o dado real da [0.2], não uma invenção | nenhuma decisão visual |
| 1. Fundação | Foundational Thinking: transporte e estado antes de qualquer tela | tokens existentes; nenhuma família nova |
| 2. Onboarding | Model the Domain: a tela coleta o que o contrato pede, nem mais nem menos | abertura direta, sem hero; alvos ≥ 44px |
| 3. Check-in | Attack the Premise: três campos de contrato, quatro escalas na issue — decidir antes de desenhar | escala como radiogroup, não slider |
| 4. Materiais | Laziness Protocol: um formulário e uma lista, sem abstração de tabela genérica | lista com hierarquia por peso, sem chips |
| 5. Plano | Minimize Reader Load: grade primeiro, mensagem depois, detalhe sob demanda | grade por dia no celular; nenhuma cápsula decorativa |
| 6. Bloqueios | Boundary Discipline: o bloqueio é do backend, a tela só o apresenta | tom neutro, nunca cor de erro |
| 7. Verificação | Explain the Number: cada métrica com sonda, base e limite | capturas em 1440 e 390, fluxo inteiro |

## 4. Fases

Convenção: **unidade** = determinístico e sem rede; **live** = a tela no navegador com predicado observável; **perf** = métrica, sonda, base e limite.

### Fase 0 — Mocks a partir das fixtures da [0.2]

**Arquivos:** `web/src/mocks/**`, `web/scripts/sincronizar-mocks.mjs`.
**Depende de:** nada.

**Mudança:** script que copia `api/tests/fixtures/{contexto,proposta,resultado}` e `pesquisa/fixtures/communication` para `web/src/mocks/`, e um índice que mapeia cada cenário ao arquivo. `--check` falha se os dois lados divergirem.

- [x] Depende de: nada
- [x] Arquivos: `web/src/mocks/**`, `web/scripts/sincronizar-mocks.mjs`
- [x] Mudança: fixtures da [0.2] viram módulos importáveis, com verificação de divergência
- [x] Resultado que se vê: `node scripts/sincronizar-mocks.mjs --check` sai com 0, e um `import` de `mocks/contexto/matutino.json` tipa
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo; **script Python** validando cada fixture contra o modelo pydantic correspondente (`ContextoEstudante`, `PropostaGrade`, `ResultadoValidacao`) — é o que prova que o mock respeita o contrato, e não só o JSON
  - live: n/a
  - perf: n/a

> **Executado em 2026-11-26.** Arquivos a mais do que o previsto: `web/scripts/validar-mocks.py` (o script
> Python da caixa de unidade) e `web/src/mocks/index.ts` (índice gerado). Resultado: 20 mocks (17 da [0.2] +
> 3 de `communication`), as duas checagens provadas **reprovando** uma cópia adulterada em `/tmp` — validador
> com erro de validação do pydantic, `--check` apontando o arquivo divergente. As fixtures de
> `communication/` ficaram numa pasta própria e **não** são validadas pelos contratos do Maestro: são outra
> família, e o validador imprime a divergência de campos em vez de aprová-las ou reprová-las pelo modelo errado.

### Fase 1 — Fundação: rotas, estado do fluxo e transporte mock

**Arquivos:** `web/src/app/{onboarding,check-in,materiais,plano}/page.tsx`, `web/src/lib/modo.ts`, `web/src/lib/api.ts`, um provider do fluxo.
**Depende de:** Fase 0.

**Mudança:** quatro rotas com um shell comum; `NEXT_PUBLIC_API_MODE` escolhe o transporte dentro de `api()` (sem tocar nas assinaturas); estado do fluxo em contexto + `localStorage`, para recarregar sem perder o que já foi preenchido; navegação entre passos bloqueada quando falta o dado anterior.

- [x] Depende de: Fase 0
- [x] Arquivos: as quatro rotas, `lib/modo.ts`, `lib/api.ts`, provider
- [x] Mudança: rotas + transporte mock + estado persistido
- [x] Resultado que se vê: `/plano` aberto sem contexto mostra "falta o onboarding", não uma tela quebrada
- [x] Verificação:
  - unidade: `tsc` limpo; script `node` que chama cada função de serviço no modo mock e confere o objeto devolvido contra o fixture
  - live: Playwright — visitar as quatro URLs direto não quebra; recarregar preserva o estado
  - perf: primeira pintura do passo 1 em modo mock **< 300 ms** (sonda: `performance.now()` até o primeiro campo focável; base: a tela do assistente, 48–54 ms; limite 300 ms)

> **Executado em 2026-11-26.** Arquivos a mais: `lib/mock.ts` (registro de rotas), `modules/fluxo/{types,service,FluxoProvider}.tsx`,
> `modules/fluxo/components/PassoShell.tsx`, as quatro páginas, `layout.tsx` (provider) e `globals.css`.
> Provas: 5 serviços em mock devolvendo as fixtures; quatro rotas abertas direto; recarregar preserva o estado;
> pré-requisito avançando (`plano → materiais → plano aberto`); passo 1 focável em **56 ms**; **zero** requisição
> fora do app e zero erro de console.
> Decisões registradas: a superfície `/fluxo/*` é **provisória** (não há rota no backend); o `as Tipo` do índice
> gerado é ponte para o alargamento de literais do `resolveJsonModule` — quem confere o mock é o validador
> pydantic; `PlanoResposta.mensagem` é opcional porque a [0.2] não tem fixture de `MensagemFinal`.
> Efeito colateral medido: `/` foi de 4,64 kB para 6,01 kB, porque `api()` passou a importar o registro de mocks.

### Fase 2 — Onboarding

**Arquivos:** `modules/onboarding/**`, rota `/onboarding`.
**Depende de:** Fase 1.

**Mudança:** cronotipo (radiogroup de três), janela de sono, lista de refeições, botão "Conectar Google Calendar" com estado simulado. Produz o subconjunto do `ContextoEstudante` que a tela pode coletar; o resto vem do mock.

- [x] Depende de: Fase 1
- [x] Arquivos: `modules/onboarding/**`
- [x] Mudança: formulário do contexto inicial + conexão de agenda simulada
- [x] Resultado que se vê: preencher e avançar leva ao check-in com o contexto guardado
- [x] Verificação:
  - unidade: `tsc` limpo; validação do objeto produzido contra `ContextoEstudante` (pydantic)
  - live: Playwright — fluxo completo por teclado; "conectar" alterna o estado; 390×844 sem overflow
  - perf: passo focável em **< 300 ms**; nenhuma requisição de rede no modo mock

> **Executado em 2026-11-26.** `EscolhaUnica.tsx` (radiogroup reutilizável), `OnboardingForm.tsx`, a página e o CSS.
> **Decisão registrada:** a tela manda **horários, não datas** — `EntradaOnboarding.sono` virou `{inicio, fim}` em vez
> de `Janela[]`, porque o contrato não deixa uma janela cruzar a meia-noite e quem distribui pelos dias é o Research.
> O mock passou a responder pelo cronotipo escolhido, usando as três fixtures (`matutino`/`vespertino`/`noturno`).
> Provas: pydantic aceita o contexto devolvido e **reprova** um sem `livres`; teclado no radiogroup; conexão de agenda
> alternando com o texto deixando claro que é simulada; contexto salvo igual ao fixture; 390×844 sem overflow;
> passo focável em **158 ms**; zero requisição de rede. (sonda: contagem de requisições)

### Fase 3 — Check-in diário

**Arquivos:** `modules/checkin/**`, rota `/check-in`.
**Depende de:** Fase 2. **Bloqueada pela decisão 4** (humor e fadiga).

**Mudança:** escalas de 1 a 5 para energia e estresse, horas de sono, e as duas escalas da issue conforme a decisão. Produz `CheckIn`.

- [x] Depende de: Fase 2 e da decisão sobre humor/fadiga
- [x] Arquivos: `modules/checkin/**`
- [x] Mudança: uma tela só com as escalas, como a issue pede
- [x] Resultado que se vê: responder quatro escalas e avançar
- [x] Verificação:
  - unidade: `tsc` limpo; objeto validado contra `CheckIn`
  - live: Playwright — teclado nas escalas (setas), sem armadilha; 390×844
  - perf: passo focável em **< 300 ms**

> **Executado em 2026-11-26, com a decisão 2 (mapear, não mudar o contrato).** A regra ficou explícita em
> `modules/checkin/mapeamento.ts`: `energia = 6 − fadiga`, `estresse` e `horas_sono` diretos; **humor** e
> **qualidade do sono** ficam no cliente, guardados em `EstadoFluxo.escalas` para não descartar a resposta.
> `horas_sono` é perguntado à parte porque uma escala de 1 a 5 não vira horas e inventar a conversão seria
> fabricar dado. O mock passou a **ecoar** o check-in e os materiais enviados, em vez de devolver o fixture.
> Provas: pydantic aceita o `CheckIn` e reprova `energia: 0`; quatro escalas operáveis por setas (incluindo
> a volta do 5 para o 1); salvo `{energia: 5, horas_sono: 7, estresse: 2}` com as quatro escalas preservadas;
> 390×844 sem overflow; passo focável em **38 ms**; zero requisição de rede.

### Fase 4 — Materiais

**Arquivos:** `modules/materiais/**`, rota `/materiais`.
**Depende de:** Fase 3.

**Mudança:** cadastro com os campos do contrato (disciplina, título, carga, horas estimadas, dificuldade, prazo) e lista editável/removível. É mais do que a issue lista; sem `carga` e `horas_estimadas` o material não entra na grade.

- [x] Depende de: Fase 3
- [x] Arquivos: `modules/materiais/**`
- [x] Mudança: cadastro e lista
- [x] Resultado que se vê: adicionar dois materiais e seguir para o plano
- [x] Verificação:
  - unidade: `tsc` limpo; cada material validado contra `Material`
  - live: Playwright — adicionar, editar, remover; lista vazia leva a "adicione ao menos um material"; 390×844
  - perf: 50 itens na lista renderizam em **< 100 ms** (sonda: `performance.now()` em volta do `setState`)

> **Executado em 2026-11-26.** `montagem.ts` (monta o `Material`, testável), `MateriaisForm.tsx` (formulário + lista
> com editar/remover) e a página. O formulário pede mais do que a issue lista — `carga`, `horas_estimadas` e `titulo`
> vêm do contrato; sem eles o material não entra na grade. `prazo` vazio vira `null`.
> Provas: pydantic aceita os dois materiais e **reprova** `horas_estimadas = 0`; lista vazia bloqueia o avanço;
> editar não duplica; remover tira; avançar guarda e abre o plano; 390×844 com 50 itens sem overflow;
> remover e repintar 50 itens em **1,2 ms** (limite 100).

### Fase 5 — Plano semanal

**Arquivos:** `modules/plano/**`, rota `/plano`.
**Depende de:** Fase 4.

**Mudança:** grade por dia a partir de `PropostaGrade.blocos`; `fora_da_grade` listado como o que não coube; `MensagemFinal` (markdown mínimo, `tom`, `links`); violações quando `ResultadoValidacao.status === "REPROVADO"`; botão **"confirmar e sincronizar"** com estado de confirmação (escrita é só mock).

- [x] Depende de: Fase 4
- [x] Arquivos: `modules/plano/**`
- [x] Mudança: grade, mensagem, violações e confirmação
- [x] Resultado que se vê: a grade da fixture `proposta/valida.json` renderizada por dia, com a mensagem e o botão
- [x] Verificação:
  - unidade: `tsc` limpo; `PropostaGrade` e `MensagemFinal` validados contra os modelos
  - live: Playwright — (a) sete dias no desktop, dias empilhados em 390; (b) `reprovado.json` mostra as violações e não deixa confirmar; (c) `sobrecarga.json` mostra o modo `reducao_danos`; (d) confirmar leva ao estado "sincronizado"; (e) 390×844 sem overflow horizontal
  - perf: CLS na renderização da grade **< 0,1**; nenhuma requisição de rede no modo mock

> **Executado em 2026-11-26.** `Markdown.tsx` (renderizador mínimo, sem dependência e sem HTML cru),
> `PlanoSemana.tsx` e a página. Duas decisões registradas:
> **(1)** a `MensagemFinal` é **sintética** (opção escolhida), escrita em `lib/mock.ts` e marcada como tal;
> quando a [0.2] tiver fixture, o mock devolve a dela. **(2)** As fixtures da [0.2] **não emparelham por nome**:
> `resultado/sobrecarga.json` aponta para 2026-12-02, que só existe em `proposta/sobrecarga_noturna.json`, e
> `reducao_danos` cobre 30/11 e 01/12. O pareamento é por **coerência de datas** (`sobrecarga_noturna` +
> `sobrecarga`; `reducao_danos` + `aprovado`), o que ajusta a letra da caixa (c). Os cenários são escolhidos
> por `localStorage["studybuddy.cenario"]`, sem seletor na tela.
> Provas: pydantic aceita `PropostaGrade` e a mensagem sintética e **reprova** mensagem sem `markdown`;
> sete colunas no desktop e uma em 390; três violações travando o confirmar; redução de danos com o que ficou
> fora, resolvido por título; sobrecarga com "Cortar 120 min"; confirmação virando "sincronizado"; CLS **0,0000**.

### Fase 6 — Bloqueios nas telas do fluxo

**Arquivos:** `modules/*/components/EstadoBloqueio.tsx` (extraído do assistente).
**Depende de:** Fase 5.

**Mudança:** o mesmo bloco neutro já provado na tela do assistente, usado quando o guardrail barra uma ação de qualquer passo (ex.: check-in ou plano), reaproveitando `veredito.ts` com default-deny.

- [x] Depende de: Fase 5
- [x] Arquivos: componente de bloqueio compartilhado
- [x] Mudança: um único bloco de bloqueio para o fluxo todo
- [x] Resultado que se vê: bloqueio aparece com a mensagem fixa, sem cor de erro e sem `role="alert"`
- [x] Verificação:
  - unidade: `tsc` limpo
  - live: Playwright — um bloqueio em cada passo; nenhum usa o tom de erro; categoria desconhecida bloqueia por padrão
  - perf: n/a

> **Executado em 2026-11-26.** `Veredito` e `bloqueou()` saíram de `modules/assistente/` para `lib/veredito.ts`, junto com
> `BloqueioError` e `exigirPermitido`; `modules/fluxo/components/EstadoBloqueio.tsx` é a marcação única, e a
> `EstadoRecusa` do assistente passou a usá-la. Os serviços do fluxo chamam `exigirPermitido` no retorno: se o
> guardrail barrou, o dado não circula e a tela recebe `BloqueioError`. O mock ganhou dois cenários
> (`bloqueio` com `PROMPT_INJECTION`, `bloqueio_clinico` com `MEDICAL_ADVICE`) que respondem por **todos** os
> `/fluxo/*`. Provas: bloqueio nos quatro passos, sempre em tom de recusa (rgb(75,78,109)), sem bloco `.falha`,
> sem `role="alert"` e sem avançar de passo; categoria desconhecida bloqueia por padrão, com texto de
> "barreira de segurança" e sem o enum na copy.

### Fase 7 — Verificação final

- [x] `npm ci`, `npx tsc --noEmit`, `npm run build` limpos (o job do CI)
- [x] Fluxo completo por teclado, só com mocks: onboarding → check-in → materiais → plano → confirmar
- [x] Capturas em 1440 (abertura e rolado) e 390×844, sem overflow
- [x] `git status` sem mudança em `api/`; nada commitado
- [x] A prova contra a API real fica **pendente declarada** — as rotas não existem

> **Executado em 2026-11-26.** CI limpo sem variáveis (`npm ci` → `tsc` → `build`); as quatro rotas novas ficaram entre
> 2,6 e 3,3 kB. O fluxo inteiro foi feito **por teclado** — Tab, setas, Enter — do onboarding ao "confirmar e sincronizar",
> e o foco não fica preso no fim. Uma ressalva de método: `input[type=time]` do Chromium não aceita `keyboard.type`,
> então os horários foram preenchidos por `fill` (sem mouse); todo controle (rádios, botões, links) foi operado por teclado.
> As capturas (`fluxo-1440-onboarding`, `fluxo-1440-plano`, `fluxo-390-plano`) revelaram **dois defeitos de layout** que
> nenhuma asserção pegaria: o radiogroup e o botão de conectar esticavam na largura toda, por `justify-items` herdado do
> grid — corrigido com `justify-items: start`. `api/` intocado; o único commit local é o da tela do assistente.

---

## 5. Matriz de estados (mock → tela)

| Cenário | Fixture | Estado na tela |
|---|---|---|
| Contexto completo, semana normal | `contexto/matutino.json` + `proposta/valida.json` + `resultado/aprovado.json` | Grade dos sete dias + mensagem + confirmar habilitado |
| Estudante em fadiga | `contexto/fadiga.json` + `proposta/reducao_danos.json` | Grade reduzida, com o modo indicado como metadado |
| Agenda cheia | `contexto/agenda_cheia.json` + `proposta/violacoes.json` | Grade parcial + lista do que ficou fora da grade |
| Plano reprovado pela validação | `resultado/reprovado.json` | Violações listadas; confirmar **desabilitado** |
| Sobrecarga | `resultado/sobrecarga.json` | Violação de dia inteiro, com o excesso a cortar |
| Guardrail barra uma ação | `veredito` com `permitido: false` | Bloco neutro "Pedido bloqueado", sem parecer erro do sistema |
| Sem contexto | — | Cada passo diz qual dado falta, em vez de quebrar |

## 6. Definição de pronto

| Item da issue | Onde fecha |
|---|---|
| Onboarding | Fase 2 |
| Check-in | Fase 3 |
| Materiais | Fase 4 |
| Plano semanal | Fase 5 |
| Bloqueios | Fase 6 (base já pronta na tela do assistente) |
| Camada de API com mocks da [0.2], trocável por env | Fases 0 e 1 |
| Fluxo navegável só com mocks | Fase 7 |
| Layout no celular | Fases 2 a 5, provado na 7 |

## 7. O que não fica provado

- **A API real deste fluxo**: as rotas não existem em `api/`. A troca por `NEXT_PUBLIC_API_MODE=real` fica implementada e sem prova.
- **Google Calendar de verdade**: `ProvedorAgenda` é um `Protocol` sem rota; o botão só simula o estado.
- **Qualidade do plano gerado**: a grade vem de fixtures da [0.2], não do Analysis rodando.
- **Markdown do mentor**: o renderizador mínimo será provado com os `MensagemFinal` das fixtures, não com saída real de LLM.

## 8. Ordem de execução

Fase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7, com `npx tsc --noEmit` ao fim de cada uma. As Fases 2, 3 e 4 são paralelizáveis tecnicamente, mas compartilham o provider de estado: sequenciá-las custa menos do que reconciliar três implementações.

**Antes de começar, três decisões:** materiais como passo do fluxo (1.5.3), humor/fadiga no check-in (1.5.4) e onde os mocks vivem (1.5.1).
