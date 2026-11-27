# Plano — tela do assistente (StudyBuddy)

Status: **executado** em 2026-11-26, fases 0 a 7, na branch `feat/tela-assistente` (criada a partir de `origin/develop`).
Data: 2026-11-26 (revisão 2 — a revisão 1 está no histórico do git deste arquivo)
Escopo: frontend em `web/`. O backend `api/` não é alterado em nenhuma fase.

---

## 0. O que mudou nesta revisão

A revisão 1 partia de uma premissa que o código não sustenta: "com API e Ollama no ar". Este ambiente
não tem API nem Ollama no ar, e a revisão 1 também trazia três afirmações sobre o contrato que a leitura
do código e dois probes de runtime refutam. As correções, com a evidência de cada uma:

| # | Mudança | Evidência |
|---|---|---|
| 1 | `d1` não-finito chega ao cliente como **`null`**, não como `Infinity`. O caso "busca vazia" é uma resposta **200** com `d1: null`, `barrada_pelo_porteiro: true` e `resposta` = frase padrão — não uma falha de parse. A "falha de parse por `Infinity`" da Fase 6 sai; o parse tolerante fica, mas por outro motivo (ver #2). | Probe: FastAPI serializa `float("inf")` em modo JSON como `null` (pydantic v2). `{"d1":null,"resposta":"recusa"}`, status 200. |
| 2 | O corpo de erro tem **três formatos**: `503`/`504` → `{"detail": string}`; `422` → `{"detail": [ {...} ]}` (array de objetos); `500` → **`text/plain` "Internal Server Error"**. O `ApiError` precisa tolerar os três. | Probe com `TestClient`: 422 devolve `detail` como array; exceção não tratada devolve `content-type: text/plain`. |
| 3 | `verificacao.citadas` e `verificacao.fora_do_contexto` contêm **IDs** (`artigo_05`), **não nomes de arquivo**. Só `fontes` traz os nomes completos (`artigo_05_sleep_consolidation_walker.txt`). A UI não pode tratar `citadas` como arquivo. | `api/app/modules/rag/verificador.py:84` — `destino.append(f"artigo_{n}")`. |
| 4 | Existe uma **segunda recusa**, além do porteiro: `verificacao.recusa = true` significa que o próprio modelo recusou pela regra 2 do prompt, depois de chamar o LLM. É diferente de `barrada_pelo_porteiro` (que barra antes de qualquer LLM). A tela precisa distinguir as duas. | `api/app/modules/rag/verificador.py:32-33,63-64`; frase em `api/app/modules/rag/prompts.py:3`, regra 2 em `prompts.py:11`. |
| 5 | `diagnostico.restricoes` chega **cru** no JSON. O filtro "só o que o estudante disse" (`_NAO_DITO`) existe só em Python (`restricoes_ditas()`), não vai no payload — a UI precisa do filtro equivalente em TS, senão mostra "não especificado" como restrição. | `api/app/modules/agentes/triagem.py:69,85-87,99-100`. |
| 6 | **O backend não sobe neste ambiente.** `.venv` não tem `ollama` nem `langchain_ollama` → `from app.main import app` quebra em `router.py:3`; `api/chroma_db/` não existe; o Ollama está fora do ar em :11434. | `api/app/modules/assistente/router.py:3`; import testado; `curl :11434` sem resposta; `api/chroma_db/` ausente (gitignored). |
| 7 | "Selo do pipeline" **virou metadado tipográfico** (texto secundário, sem borda nem cápsula). A skill proíbe chip/badge não interativo acima de título ou dentro de card. | `gemini-frontend-design/SKILL.md` §4. |
| 8 | O contador de caracteres saiu de `0.8125rem` para `0.875rem`: texto abaixo de 13px não pode ficar acima da dobra, e o contador fica ao lado do campo. | `gemini-frontend-design/SKILL.md` §1 e checklist §5. |
| 9 | "Evidence before claims" **não existe** no pstack-skill; "Show me your work" é **skill**, não princípio. As citações da tabela §3 foram corrigidas para os nomes reais (24 princípios em `references/principles.md`, 38 skills em `references/skills/`). | `grep` em `.claude/skills/pstack-skill/`. |
| 10 | As capturas agora incluem **desktop rolado**, não só a abertura. | `gemini-frontend-design/SKILL.md` §5. |
| 11 | A **Fase 0** (ambiente de prova com stub) é nova, e cada fase ganhou as três caixas que o playbook exige: **unidade**, **live** e **perf**. A revisão 1 tinha um único "critério de verificação". | `pstack-skill/playbooks/multi-phase-plan.md` §4. |

Decisão do operador sobre o item 6: **provar tudo contra um servidor stub local; a prova com a API real
fica declarada como pendente**, com os comandos de desbloqueio em §7.3.

---

## 1. Briefing ajustado

### 1.1 Contexto e stack

Repositório StudyBuddy (RAG sobre 20 artigos científicos de orientação de estudos). Backend FastAPI em
`api/` — **não alterar**. Frontend em `web/`: Next.js 15, React 19, TypeScript, App Router, sem framework
de CSS. Organização por módulo em `web/src/modules/<modulo>/{components/, service.ts, types.ts}`; rotas em
`web/src/app/`; cliente HTTP em `web/src/lib/api.ts` (`NEXT_PUBLIC_API_URL`, padrão `http://localhost:8000`).
O módulo `example` é a referência de padrão.

`web/src/app/page.tsx` é hoje um Server Component; o módulo do assistente precisa de `"use client"` no
componente que guarda estado (formulário e resultado). `layout.tsx` continua sendo Server Component e
importa o CSS global.

### 1.2 Contrato da API (conferido no código)

- `POST /assistente/perguntar` — body `{ pergunta: string (3..1000), pipeline?: "classico" | "agentes" }`.
  O `pipeline` do corpo **sobrescreve** o do ambiente, o que permite forçar o outro pipeline no mesmo
  servidor (útil contra os dois containers do `docker-compose`).
  — `api/app/modules/assistente/schemas.py:12-15`
- Resposta: `{ pipeline, pergunta, resposta, fontes, d1, barrada_pelo_porteiro, chamadas_llm,
  diagnostico, verificacao, veredito, latencia_s, rastro[] }` — `api/app/modules/assistente/schemas.py:25-40`
  (`veredito` veio da `develop`, com a barreira de prompt injection; num servidor anterior ao guardrail o
  campo não vem, e o tipo o trata como opcional).
- `veredito`: resultado da barreira de guardrails. **Dois formatos convivem na develop**: o de
  `guardrails/injection.py` (`categoria: "INJECTION"`, `motivos[]`), que o serviço devolve hoje, e o
  canônico do Maestro em `agentes/contratos.py` (`permitido`, `resposta_bloqueio` e as categorias
  `PROMPT_INJECTION`, `HATE_SPEECH`, `MEDICAL_ADVICE`, `OUT_OF_SCOPE`), que a `guardrails/clinico.py` já usa.
  O bloqueio acontece **antes de qualquer busca**: a resposta vem com `barrada_pelo_porteiro: false`,
  `verificacao: null`, `chamadas_llm: 0`, `fontes: []`, `d1: null` e a frase de bloqueio.
  A tela decide por `permitido === false` quando o campo existe e, na falta dele, por **default-deny**:
  qualquer `categoria` diferente de `"OK"` bloqueia. Assim uma categoria futura bloqueia por padrão em vez
  de aparecer como resposta. É uma **terceira recusa**, diferente do porteiro e do modelo.
- `fontes` são os **arquivos dos trechos consultados** (`artigo_NN_*.txt`), deduplicados e em ordem de
  aparição — `api/app/modules/rag/resultado.py:34-41`.
- `d1` é a distância L2 do primeiro trecho. **Não finito vira `null` no JSON**, e a UI exibe "—".
- `barrada_pelo_porteiro: true` significa recusa **antes de qualquer LLM**: `resposta` é a frase padrão,
  `chamadas_llm` é 0, `verificacao` é `null`, e `fontes` ainda lista o que foi consultado.
- `diagnostico` (só multiagente): `problema_principal`, `objetivo`,
  `restricoes{tempo_disponivel, prazo, contexto}`, `tipo_resposta` (`plano`/`explicacao`), `consultas[]`,
  `falhou`. As restrições vêm **cruas** — o filtro do que foi dito é do lado Python (§0 item 5).
- `verificacao`: `recusa`, `citadas[]`, `fora_do_contexto[]`, `sem_citacao`, `alterou`. As listas contêm
  **IDs** `artigo_NN`, não nomes de arquivo (§0 item 3).
- `rastro[]`: `{ agente, acao, detalhe, segundos }`; `detalhe` **pode conter quebras de linha**
  (`api/app/modules/agentes/orquestrador.py:54-56`).
- `GET /assistente/info` — `{ pipeline, llm, triagem, embedding, top_k, porteiro_tau }`.
- Erros: `503` = índice ausente / Ollama fora do ar / modelo não baixado (`{"detail": string}`);
  `504` = modelo local não respondeu a tempo (`{"detail": string}`); `422` = validação
  (`{"detail": [ {...} ]}`); `500` = exceção não tratada (**corpo `text/plain`**).
  **API fora do ar não é 503**: é `TypeError` do `fetch`, e precisa de estado próprio.
- CORS libera `http://localhost:3000` (`api/app/core/config.py:12`).

### 1.3 O ambiente real (conferido em 2026-11-26)

Isto não é premissa herdada: é o estado medido. O plano da revisão 1 assumia "backend no ar".

| Item | Estado | Impacto no plano |
|---|---|---|
| `web/node_modules` | ausente | `npm ci` é obrigatório antes de `tsc`/`build` (registry.npmjs.org respondeu 200) |
| CI do frontend | `npm ci` → `npx tsc --noEmit` → `npm run build` (Node 22) — `.github/workflows/ci.yml` | A Fase 7 **é** esse job, mais a conferência visual |
| `.venv` do backend | sem `ollama` e sem `langchain_ollama`; `fastapi 0.163.2` contra `0.163.1` pinado em `requirements.txt` (drift) | `from app.main import app` **falha** em `router.py:3` — a API não sobe |
| `api/chroma_db/` | ausente (gitignored) | Se a API subisse, `/perguntar` daria 503 "Índice não encontrado" (`repository.py:23-24`) |
| Ollama em `:11434` | sem resposta | Sem modelo local, sem embedding, sem resposta real |
| Containers | `docker compose up` sobe clássico em `:8001` e multiagente em `:8002`; o Ollama roda **fora** do Docker (Metal); o volume `./api/chroma_db` precisa existir | O seletor de pipeline cobre os dois; o caminho real depende do índice e do Ollama |
| `api/.env` (gitignored) | sem `PIPELINE` → default `classico`; `porteiro_tau` vazio → corte calibrado do bge-m3 = **1.026** | O corte do porteiro no ambiente é 1.026 (`repository.py:14`) |
| Playwright | sem browser em cache | `npx playwright install chromium` (rede) |

**Consequência:** a Fase 0 cria o substituto do backend — um servidor stub local com os payloads reais —
e a prova de ponta a ponta fica como pendência declarada (§7.3), não como item falho.

### 1.4 Escopo de arquivos permitido

- `web/src/app/page.tsx`
- `web/src/app/layout.tsx`
- `web/src/app/globals.css` (novo)
- `web/src/lib/api.ts`
- `web/src/modules/assistente/**` (novo)

Em `web/src/modules/example/` só é permitido remover o import em `page.tsx`; o módulo não é editado nem
apagado. O servidor stub e as capturas ficam **fora do repositório**, em `/tmp` — nada de stub no `web/`.

### 1.5 Decisões fixadas

1. `lib/api.ts` entra no escopo, com extensão mínima compatível com o uso atual: ler o corpo como texto,
   fazer `JSON.parse` tolerante e lançar `ApiError` com `status` e `detail` **normalizado em string**
   (422 traga `detail` como array; 500 traga `text/plain` e nem tem JSON). A assinatura `api<T>(path, init)`
   não muda, e o módulo `example` continua funcionando (ele engole o erro com `.catch`).
2. Sem dependência nova em `package.json` e sem fonte externa (`system-ui`): o build não depende de rede.
3. Tema claro; tokens prontos para um tema escuro futuro, que não será implementado agora.
4. O seletor começa no pipeline de `/assistente/info`, com fallback `classico` se a chamada falhar. A UI
   **sempre envia `pipeline` explicitamente** no body, o que funciona contra um servidor só e contra os
   dois containers.
5. Envio: Enter envia, Shift+Enter quebra linha, Cmd/Ctrl+Enter também envia. Botão de cancelar durante a
   espera, já que a latência local pode chegar a minutos. `isComposing` é respeitado (IME em português).
6. `d1` aparece nos detalhes; `null` vira "—". O valor nunca é não-finito no wire (§0 item 1).
7. Verificação visual com Playwright via `npx` (sem tocar no `package.json`); capturas gravadas fora do
   repositório, em `/tmp`.
8. O plano vive neste arquivo; o chat registra as decisões.
9. Sem chip, badge ou cápsula não interativa em lugar nenhum. O pipeline aparece como metadado
   tipográfico ("Resposta · pipeline clássico · 12,4 s"), com hierarquia por peso e cor.
10. `transition` nomeia propriedade explícita; nunca `transition: all`.

### 1.6 Tarefa

Construir a tela principal do assistente, substituindo o conteúdo de `web/src/app/page.tsx` (hoje renderiza
`ExampleList`):

1. Campo de pergunta com contador e limite de 1000 caracteres, envio por Enter/Cmd+Enter.
2. Seletor segmentado entre `classico` e `agentes` (um controle, não dois botões soltos).
3. Resposta em PT-BR, com as fontes consultadas, as citações verificadas e o metadado do pipeline usado.
4. Estados explícitos: carregando (com tempo decorrido e cancelar), erro 503, erro 504, API indisponível,
   e o caso `barrada_pelo_porteiro` (recusa, não erro).
5. Detalhes colapsáveis: latência, chamadas ao LLM, `d1`, diagnóstico (só multiagente), verificação de
   citações e rastro por agente.
6. Layout responsivo até 390×844, sem overflow horizontal.

### 1.7 Skills e precedência

`pstack-skill` e `gemini-frontend-design` existem em `.claude/skills/`, mas não estão invocáveis nesta
sessão; ler `pstack-skill/playbooks/multi-phase-plan.md` e `gemini-frontend-design/SKILL.md` diretamente.

Precedência em conflito: contrato da API e coerência com o restante do `web/` > `gemini-frontend-design` >
preferência estética. Ferramenta de produtividade: abertura direta no conteúdo, sem hero.

## 2. Direção visual

"Tinta sobre papel frio": fundo `#F6F7F4`, superfície `#FFFFFF`, tinta `#14181A`, texto secundário
`#5A6462`, linha `#DCE1DC`, acento verde-petróleo `#0F5A50` (ações e metadado). Semânticos: sucesso `#1F6B3A`,
atenção `#8A5A00`, erro `#A32B23`, recusa `#4B4E6D`.

Uma família (`system-ui`) com pesos diferentes, três tamanhos de corpo (1rem, 0.875rem, 0.8125rem) e um `h1`
acima da escala com `-0.02em`. Coluna única de 46rem, alinhada à esquerda, cabeçalho compacto e conteúdo
imediatamente abaixo. O texto da resposta tem coluna própria de **34rem** (≈65ch, o teto da skill); o
formulário usa os 46rem.

Movimento só na entrada do resultado (150–200ms, opacidade e 4px), desligado sob `prefers-reduced-motion`.
Rótulos em sentence case. A recusa é um bloco com fio lateral e fundo tingido — **sem cápsula, sem borda
fechada, sem ícone decorativo**.

O contador de caracteres fica em `0.875rem` (§0 item 8), e o texto de `0.8125rem` só aparece abaixo da dobra.

## 3. Skills aplicadas por fase

As duas skills são governantes, não anexos: cada fase nomeia a disciplina da `pstack-skill` e a decisão da
`gemini-frontend-design` que estão em jogo. Todas foram lidas do disco em
`.claude/skills/pstack-skill/playbooks/multi-phase-plan.md`, `.claude/skills/pstack-skill/references/principles.md`,
`.claude/skills/pstack-skill/references/skills/` e `.claude/skills/gemini-frontend-design/SKILL.md`.

| Fase | pstack-skill | gemini-frontend-design |
|---|---|---|
| 0. Ambiente de prova | Prove It Works: verificar a coisa real, não um proxy | Nenhuma decisão visual |
| 1. Fundação | Foundational Thinking: tokens e erro de API antes de qualquer tela. Laziness Protocol: nenhuma abstração nova | Tokens em `:root`, uma família (`system-ui`), três tamanhos de corpo, contraste AA, foco visível |
| 2. Tipos e serviço | Model the Domain: o tipo espelha o contrato, sem camada de tradução. Type System Discipline | Nenhuma decisão visual |
| 3. Pergunta | Sequence-verifiable-units: o formulário fecha e se verifica sozinho | Abertura direta no conteúdo, sem hero; `h1` fora da escala de corpo |
| 4. Resultado | Prove It Works + Test Behavior Not Implementation: só exibe citação que o verificador confirmou | Prosa ≤ 65ch (34rem), metadado em texto, **sem chip/badge** |
| 5. Detalhes | Minimize Reader Load: detalhe sob demanda, uma seção por dado | Hierarquia por peso e cor, sem inventar tamanho intermediário |
| 6. Erros e a11y | Attack the Premise: erro não é um só, cada causa tem estado próprio. Boundary Discipline: o que é do backend é do backend | Cores semânticas, `prefers-reduced-motion`, alvos ≥ 44px, WCAG AA |
| 7. Verificação | Explain the Number: a métrica tem nome, sonda, base e limite. Skill `show-me-your-work` | Conferência visual real em 1440 (abertura e rolado) e 390×844, não só build |

Estrutura que o playbook `multi-phase-plan` pede e como este plano a cumpre:

- **Grafo de dependências:** linear, `0 → 1 → 2 → 3 → 4 → 5 → 6 → 7`. Nenhuma fase é paralelizável: todas
  tocam o mesmo módulo e a mesma página.
- **PRs:** nenhum. A entrega é uma mudança única no working tree, porque o briefing proíbe commit. O
  playbook de execução é **manual, fase a fase**, com o "ok" antes da Fase 0; `autopilot-full.md` e
  `autopilot-stack.md` não se aplicam porque pressupõem fila de PRs com push e merge.
- **Uma mudança por fase**, com os arquivos que toca e o critério que a fecha, no lugar dos checkboxes do
  playbook — mas **com as caixas do playbook**, agora em §4: dependência, arquivos, mudança, resultado
  observável e as três caixas de verificação (unidade, live, perf). Onde uma dimensão não se aplica, ela
  fica marcada `n/a:` com o motivo, como pede `playbooks/feature.md`.

## 4. Fases

Convenção das três caixas (de `multi-phase-plan.md` §4): **unidade** = verificação determinística e
repetível sem rede; **live** = a superfície real (a página no navegador) com cenário concreto e
predicado observável; **perf** = métrica, sonda, base e número que falha. Sem runner de teste no `web/`
(o `package.json` está fora do escopo), a caixa de unidade é `npx tsc --noEmit` mais, quando aplicável,
um script `node` sem dependência contra o fixture do stub.

### Fase 0 — Ambiente de prova (stub + fixtures)

**Arquivos:** nenhum no repositório. Tudo em `/tmp/sb-stub/` (fora do repo, como a decisão 7 já previa
para as capturas).

**Mudança:** `server.mjs` (Node, sem dependência) que serve `GET /assistente/info` e
`POST /assistente/perguntar`, reconhecendo as **5 perguntas do `api/demo.py`** (`CENARIOS`) e devolvendo um
fixture por cenário, mais fixtures sintéticos para: recusa do porteiro, recusa do modelo, `d1: null`,
`sem_citacao`, citação fora do contexto, e os quatro erros (503, 504, 422, 500 `text/plain`). Os
identificadores de cenário entram pelo **texto da pergunta** (mesma mecânica dos cenários do `demo.py`),
porque o body do POST é fixo pelo contrato. `NEXT_PUBLIC_API_URL` aponta para a porta do stub.

**Depende de:** nada. É a primeira fase.

**Checkboxes:**

- [x] Depende de: nada
- [x] Arquivos: `/tmp/sb-stub/server.mjs`, `/tmp/sb-stub/fixtures/*.json` (fora do repo)
- [x] Mudança: os 5 payloads de `demo.py` viram fixtures; os estados de erro viram respostas por
      sentinela no texto da pergunta
- [x] Resultado que se vê: `curl` no stub devolve o JSON esperado para cada cenário
- [x] Verificação:
  - unidade: `node --test` do próprio stub (runner nativo do Node 22, zero dependência) — 1 teste por
    fixture, comparando o JSON servido com o arquivo
  - live: n/a (ainda não há UI)
  - perf: n/a — sem superfície

### Fase 1 — Fundação: tokens, layout e cliente HTTP

**Arquivos:** `web/src/app/globals.css` (novo), `web/src/app/layout.tsx`, `web/src/lib/api.ts`.

**Mudança:** tokens em `:root`, reset mínimo, tipografia base, foco visível, container e utilitários de
texto; `layout.tsx` importa o CSS e ganha `title`/`description` reais; `api()` passa a ler o corpo como
texto, fazer `JSON.parse` tolerante e lançar `ApiError` (`status`, `detail` normalizado em string:
array do 422 vira `"pergunta: String should have at least 3 characters"`; corpo não-JSON vira o texto cru
truncado), mantendo a assinatura `api<T>(path, init)`. `ApiError` também carrega o `status`, para que a
tela mapeie 503/504/422/500 para estados diferentes.

**Depende de:** Fase 0 (para ter contra o que testar o cliente HTTP).

**Checkboxes:**

- [x] Depende de: Fase 0
- [x] Arquivos: `globals.css`, `layout.tsx`, `lib/api.ts`
- [x] Mudança: tokens, reset, `ApiError` com os três formatos de corpo de erro
- [x] Resultado que se vê: a página antiga (`ExampleList`) continua renderizando, agora com o CSS novo
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo; script `node` que chama `api()` contra o stub e afirma que 503
    vira `ApiError{status:503}`, 422 vira `detail` string, e corpo `text/plain` não estoura
  - live: `npm run dev` renderiza `ExampleList` sem erro de console
  - perf: a primeira pintura não dispara requisição de fonte externa — sonda: contagem de requisições
    no Playwright; base: `ExampleList` atual; limite: 0 requisições de fonte

### Fase 2 — Tipos e serviço do módulo

**Arquivos:** `web/src/modules/assistente/types.ts`, `web/src/modules/assistente/service.ts`.

**Mudança:** tipos espelhando o contrato (`Pipeline`, `Resposta`, `Evento`, `Diagnostico`, `Verificacao`,
`Info`), com `diagnostico`/`verificacao` tipados pelas chaves reais e tolerantes a campo ausente;
`d1: number | null` (nunca `Infinity`); `citadas`/`fora_do_contexto` como `string[]` de IDs. Serviço com
`perguntar(pergunta, pipeline, signal)` e `obterInfo(signal)`, ambos repassando o `AbortSignal` para o
`fetch` — é o que torna o botão de cancelar possível.

**Depende de:** Fase 1.

**Checkboxes:**

- [x] Depende de: Fase 1
- [x] Arquivos: `types.ts`, `service.ts`
- [x] Mudança: tipos espelham o contrato, sem camada de tradução
- [x] Resultado que se vê: `obterInfo()` e `perguntar()` devolvem os objetos do fixture
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo; script `node` que confere **cada fixture** do stub contra o tipo
    (campo a campo, incluindo `d1: null` e `verificacao: null`)
  - live: n/a
  - perf: n/a — sem superfície

### Fase 3 — Pergunta: campo, contador e seletor

**Arquivos:** `modules/assistente/components/PerguntaForm.tsx`, `PipelineToggle.tsx`, `web/src/app/page.tsx`.

**Mudança:** componente cliente com `textarea` (Enter envia, Shift+Enter quebra, Cmd/Ctrl+Enter envia,
`isComposing` ignorado), contador `n/1000` com `maxLength`, bloqueio abaixo de 3 caracteres (o mesmo
mínimo da API), `AbortController`, botão de cancelar e cronômetro decorrido durante a espera; segmentado
com `role="radiogroup"`, teclado por setas, default vindo de `obterInfo` e fallback `classico`. O `/info`
**não bloqueia** o formulário: o campo fica utilizável antes de a chamada responder.

**Depende de:** Fase 2.

**Checkboxes:**

- [x] Depende de: Fase 2
- [x] Arquivos: `PerguntaForm.tsx`, `PipelineToggle.tsx`, `page.tsx`
- [x] Mudança: campo, contador, seletor, cancelar, cronômetro
- [x] Resultado que se vê: digitar e enviar contra o stub devolve o resultado na tela
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo
  - live: Playwright contra o stub — (a) digitar 1001 caracteres para no 1000, contador em `1000/1000`;
    (b) Enter envia e Shift+Enter cria linha nova; Cmd/Ctrl+Enter envia; (c) botão desabilitado com 2
    caracteres; (d) setas trocam o pipeline com foco visível; (e) recarregar mantém o default do `/info`;
    (f) em 390×844, `scrollWidth <= innerWidth`
  - perf: tempo do `performance.now()` até o `textarea` ficar utilizável, com o `/info` do stub atrasado
    em 2s — sonda: marca de tempo no Playwright; base: o mesmo campo sem a chamada de `/info`; limite:
    **< 300 ms** (o `/info` nunca segura o formulário)

### Fase 4 — Resultado: resposta, fontes e recusa

**Arquivos:** `modules/assistente/components/RespostaCard.tsx`, `FontesList.tsx`, `SeloPipeline.tsx`
(renomeado: `MetadadoResposta.tsx`), `EstadoRecusa.tsx`.

**Mudança:** resposta em texto puro com `white-space: pre-wrap` (as citações `[Fonte: ...]` ficam no
lugar); seção "Fontes consultadas" com os nomes dos arquivos, quebrando nomes longos, e uma linha "nenhuma
fonte consultada" quando a lista vier vazia; lista de citações verificadas a partir de
`verificacao.citadas` (**IDs `artigo_NN`**, com o nome do arquivo resolvido por prefixo contra `fontes`
quando houver), aviso discreto quando `alterou`; metadado do pipeline em texto secundário, **sem cápsula**;
card de recusa (tom neutro, não de erro) para `barrada_pelo_porteiro`, **distinguindo** a recusa do
modelo (`verificacao.recusa`); as duas recusas mantêm as fontes consultadas e o metadado.

**Depende de:** Fase 3.

**Checkboxes:**

- [x] Depende de: Fase 3
- [x] Arquivos: `RespostaCard.tsx`, `FontesList.tsx`, `MetadadoResposta.tsx`, `EstadoRecusa.tsx`
- [x] Mudança: resposta, fontes, citações verificadas, recusas
- [x] Resultado que se vê: a resposta do fixture renderiza com parágrafos e citações no meio do texto
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo
  - live: Playwright contra o stub — (a) resposta renderiza inteira, com a citação no lugar do texto;
    (b) recusa do porteiro **não** usa cor nem rótulo de erro e **não** mostra seção de verificação;
    (c) recusa do modelo aparece como recusa, não como resposta vazia; (d) nome de arquivo de 60+
    caracteres quebra linha sem overflow em 390px; (e) foco vai para o título do resultado após sucesso;
    (f) nenhum chip, badge ou cápsula no resultado
  - perf: desvio de layout acumulado (CLS) na entrada do resultado — sonda:
    `performance.getEntriesByType("layout-shift")`; base: 0 (sem a animação); limite: **CLS < 0,1**

### Fase 5 — Detalhes colapsáveis

**Arquivos:** `modules/assistente/components/DetalhesTecnicos.tsx`.

**Mudança:** `<details>`/`<summary>` (teclado de graça) fechado por padrão, com seções condicionais:
métricas (latência, chamadas ao LLM, `d1` — `null` vira "—"), diagnóstico (só quando não nulo, com as
restrições **filtradas** como o Python filtra, aviso se `falhou`), verificação (citadas, removidas, sem
citação), rastro (agente, ação, detalhe com `pre-line`, segundos).

**Depende de:** Fase 4.

**Checkboxes:**

- [x] Depende de: Fase 4
- [x] Arquivos: `DetalhesTecnicos.tsx`
- [x] Mudança: seções condicionais sob `<details>`
- [x] Resultado que se vê: abrir "Detalhes técnicos" mostra as seções do resultado atual
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo
  - live: Playwright contra o stub — (a) seções sem dado não aparecem (clássico não mostra diagnóstico;
    recusa não mostra verificação); (b) abrir e fechar por teclado funciona; (c) estado fechado não
    desloca o layout; (d) detalhe multilinha do rastro preserva as quebras; (e) restrição "não
    especificado" **não** aparece
  - perf: o `innerHTML` do bloco da resposta é **idêntico** antes e depois de abrir os detalhes —
    sonda: comparação de snapshot no Playwright; base: o mesmo bloco fechado; limite: **0 diferenças**

### Fase 6 — Erros, acessibilidade e responsivo

**Arquivos:** `RespostaCard.tsx`/`page.tsx` (estado de erro), `globals.css`.

**Mudança:** mapeamento explícito (§5): 503 → "O servidor está sem índice ou o Ollama não está
respondendo", com o `detail` cru nos detalhes; 504 → "O modelo local demorou demais", com ação de tentar
de novo; `TypeError` → "Não foi possível falar com a API em `{NEXT_PUBLIC_API_URL}`", com o comando de
subir o backend; corpo não-JSON (500) → erro genérico, **sem tela branca**; 422 → erro de validação (não
deve ocorrer, porque o cliente bloqueia < 3 caracteres, mas o estado existe). `aria-live="polite"` para
carregando e resultado, `role="alert"` para erro, alvo de toque ≥ 44px, `prefers-reduced-motion`
respeitado, foco e ordem de tabulação conferidos.

**Depende de:** Fase 5.

**Checkboxes:**

- [x] Depende de: Fase 5
- [x] Arquivos: `RespostaCard.tsx`, `page.tsx`, `globals.css`
- [x] Mudança: um estado por causa, sem tela branca
- [x] Resultado que se vê: cada falha mostra a mensagem certa e a ação sugerida
- [x] Verificação:
  - unidade: `npx tsc --noEmit` limpo; script `node` que confirma o mapeamento status → mensagem
  - live: Playwright contra o stub, um cenário por estado — 503, 504, 422, 500 `text/plain`, API
    desligada (stub parado) — cada um mostra a mensagem certa e a ação sugerida, e **nenhum** quebra a
    página; leitor de tela anuncia carregando e erro; nada anima com
    `prefers-reduced-motion: reduce`
  - perf: tempo entre a resposta do stub e a mensagem na tela — sonda: marca de tempo no Playwright;
    base: render do mesmo texto sem tratamento de erro; limite: **< 100 ms**

### Fase 7 — Verificação final

**Mudança:** nenhuma; só prova.

**Critério de verificação (todos obrigatórios):**

- `npm ci`, `npx tsc --noEmit`, `npm run build` limpos — **é o job de CI do frontend**, palavra por palavra
  (`.github/workflows/ci.yml`, Node 22).
- Playwright instalado via `npx` (`npx playwright install chromium`), capturas em `/tmp/`: **1440 de
  abertura**, **1440 rolada** e **390×844**, com `scrollWidth <= innerWidth` nas duas larguras.
- Teclado do início ao fim, sem armadilha de foco.
- `git status` sem mudanças em `api/`; nada commitado.
- A prova contra a API real (§7.3) fica **pendente declarada**, não verde por omissão.

---

## 5. Matriz de estados: gatilho no servidor → estado na tela

Uma linha por estado, com o corpo exato que o servidor devolve. É a tabela que a Fase 6 implementa e que
o stub reproduz.

| Condição | HTTP | Corpo | Estado na tela |
|---|---|---|---|
| Resposta normal, pipeline `classico` | 200 | `d1` numérico, `verificacao.citadas` com IDs | Resposta + fontes + citações verificadas + metadado |
| Resposta normal, pipeline `agentes` | 200 | + `diagnostico` com `falhou: false` | idem + seção de diagnóstico nos detalhes |
| Resposta sem citação do modelo | 200 | `verificacao.sem_citacao: true` | Resposta + aviso discreto "o modelo não citou a fonte" |
| Citação fora do contexto | 200 | `verificacao.fora_do_contexto: ["artigo_99"]` | Aviso com o que foi removido; a citação removida **não** aparece |
| Recusa do porteiro | 200 | `barrada_pelo_porteiro: true`, `verificacao: null`, `chamadas_llm: 0` | Bloco de recusa (tom neutro, sem cor de erro), sem seção de verificação, fontes preservadas |
| Recusa do modelo | 200 | `barrada_pelo_porteiro: false`, `verificacao.recusa: true` | Bloco de recusa com a causa ("o modelo não achou base") |
| Bloqueio por guardrail (injeção, clínico ou categoria futura) | 200 | `veredito` com `permitido: false` ou `categoria ≠ "OK"`, `verificacao: null`, `fontes: []` | Bloco "Pedido bloqueado", com a categoria e os motivos nos detalhes |
| Busca vazia | 200 | `d1: null`, `barrada_pelo_porteiro: true` | Recusa + `d1` como "—" nos detalhes |
| Índice ausente / Ollama fora / modelo não baixado | 503 | `{"detail": "..."}` | Erro 503: o servidor está sem índice ou o Ollama não responde; `detail` cru nos detalhes |
| Modelo local demorou | 504 | `{"detail": "..."}` | Erro 504: o modelo local demorou demais; ação "tentar de novo" |
| Validação (só se o cliente deixar passar) | 422 | `{"detail": [ {...} ]}` | Erro de validação, com o campo e a mensagem |
| Exceção não tratada | 500 | `text/plain` | Erro genérico, sem tela branca |
| API fora do ar | — | `TypeError` do `fetch` | Erro "não foi possível falar com a API", com a URL e o comando para subir |

## 6. Definição de pronto

| Requisito | Onde fecha |
|---|---|
| 1. Campo, contador, Enter/Cmd+Enter | Fase 3 |
| 2. Seletor segmentado | Fase 3 |
| 3. Resposta, fontes e metadado do pipeline | Fase 4 |
| 4. Carregando, 503/504/API fora, recusas | Fases 4 e 6 |
| 5. Detalhes colapsáveis | Fase 5 |
| 6. Responsivo até 390×844 | Fases 3 e 7 |

## 7. O que não fica provado

### 7.1 Latência e qualidade das respostas

Latência real dos dois pipelines e qualidade das respostas dependem de Ollama e índice vetorial no ar.
Sem eles, valem o build, os estados provados contra o stub e as capturas.

### 7.2 O caso `d1` não-finito

Coberto por **fixture** (`d1: null` servido pelo stub), não por um índice vazio real: o caminho real exigiria
o Chroma com coleção vazia, o que só se atinge com o volume do `docker-compose` montado sem o índice.
O que a fixture prova é o que a UI faz com `null` — que é "—".

### 7.3 A prova de ponta a ponta (pendente, com o caminho para desbloquear)

Bloqueada por três fatos, todos externos ao frontend:

1. `.venv` sem `ollama` e `langchain_ollama` → `from app.main import app` falha em `router.py:3`.
   Desbloqueio: `cd api && pip install -r requirements.txt` (o `ollama` vem transitivo do
   `langchain-ollama`; é por isso que o CI do backend passa).
2. `api/chroma_db/` não existe → `/perguntar` daria 503 "Índice não encontrado".
   Desbloqueio: rodar `pesquisa/rag_pipeline_semana2.ipynb` de dentro de `pesquisa/`, com o Ollama no ar.
3. Ollama fora do ar em `:11434` → sem `bge-m3` e `qwen3:8b` não há embedding nem resposta.
   Desbloqueio: `ollama pull bge-m3` e `ollama pull qwen3:8b`.

Feito isso, a prova pendente é: uma pergunta por pipeline contra `http://localhost:8000`, mais uma pergunta
fora do escopo para a recusa do porteiro, e o mesmo checklist visual. Até lá, o resultado é **pendente
declarado** — não verde por omissão.

## 8. Ordem de execução

Fase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7, com `npx tsc --noEmit` ao fim de cada fase. Execução começa somente com
o "ok" explícito do operador.
