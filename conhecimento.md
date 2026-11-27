---
type: Project Knowledge
title: StudyBuddy
description: Assistente de estudos em RAG sobre 20 artigos científicos, com backend FastAPI, frontend Next.js e fluxo de planejamento semanal.
tags: [studybuddy, rag, fastapi, nextjs, agente, okf]
status: draft
generated: { by: process:claude-code, at: 2026-11-26T00:00:00Z }
sources:
  - id: contratos
    resource: api/app/modules/agentes/contratos.py
    title: Contratos JSON entre o Maestro e as skills
  - id: schemas
    resource: api/app/modules/assistente/schemas.py
    title: Contrato da API do assistente
  - id: plano-assistente
    resource: docs/plano-frontend-assistente.md
    title: Plano da tela do assistente
  - id: plano-fluxo
    resource: docs/plano-web-fluxo-estudo.md
    title: Plano do fluxo de estudo
---

# O que é

O StudyBuddy responde perguntas de organização de estudos fundamentadas em 20 artigos científicos,
citando a fonte no próprio texto, e monta um plano semanal a partir do contexto do estudante
(cronotipo, sono, refeições, check-in diário e materiais).[^contratos]

# Arquitetura

| Parte | Onde | Papel |
|---|---|---|
| API | `api/` (FastAPI) | Pipelines de resposta, guardrails, contratos JSON |
| Pesquisa | `pesquisa/` | Notebook de indexação e métricas |
| Frontend | `web/` (Next.js 15, App Router) | Tela do assistente e fluxo de planejamento |
| Índice vetorial | `api/chroma_db/` (gitignored) | Chroma com os trechos dos artigos |
| Fixtures | `api/tests/fixtures/`, `pesquisa/fixtures/` | Casos de referência da [0.2] |

Os pipelines de resposta são dois: `classico` (busca, porteiro, geração e verificador de citações) e
`agentes` (Triagem, Planejador e verificador). O porteiro recusa antes de qualquer LLM quando a
distância do primeiro trecho (`d1`) passa do corte calibrado; o verificador remove citação a artigo
que o modelo não recebeu.[^schemas]

# Contratos

Definidos em pydantic, com `extra="forbid"`.[^contratos]

- `ContextoEstudante` — cronotipo, semana, janelas livres/ocupadas/picos/vales/sono/refeições,
  materiais, check-in e índice de capacidade.
- `CheckIn` — `energia` (1–5), `horas_sono` (0–24) e `estresse` (1–5).
- `Material` — disciplina, título, carga cognitiva (`alta`/`baixa`), horas estimadas, dificuldade e prazo.
- `PropostaGrade` — blocos da semana, o que ficou fora da grade e o modo (`normal`/`reducao_danos`).
- `ResultadoValidacao` — `APROVADO` ou `REPROVADO` com a lista de violações.
- `MensagemFinal` — `markdown`, `tom` e `links`; é o contrato que o `web` consome.
- `Veredito` — guardrails: `permitido`, `categoria` (`OK`, `PROMPT_INJECTION`, `HATE_SPEECH`,
  `MEDICAL_ADVICE`, `OUT_OF_SCOPE`) e `resposta_bloqueio`.

# Fluxo do estudo

```
onboarding → check-in → materiais → plano → confirmar e sincronizar
```

Cinco telas em `web/src/app/`, cada uma com o seu módulo em `web/src/modules/<passo>/`. O estado do
fluxo (`modules/fluxo/FluxoProvider.tsx`) guarda contexto, check-in, escalas e materiais em contexto
React + `localStorage`; cada passo só abre com o anterior preenchido, e o que falta aparece nomeado, não
como tela quebrada.[^plano-fluxo]

| Tela | Rota | O que faz | Contrato envolvido |
|---|---|---|---|
| Onboarding | `/onboarding` | cronotipo, janela de sono, refeições e conexão de agenda (simulada) | entrada do `ContextoEstudante` |
| Check-in | `/check-in` | quatro escalas de 1 a 5 (humor, estresse, sono, fadiga) e horas dormidas | `CheckIn` |
| Materiais | `/materiais` | cadastro, edição e remoção; lista com disciplina, carga, horas, dificuldade e prazo | `Material[]` |
| Plano | `/plano` | grade de sete dias, mensagem do mentor, o que ficou fora da grade e o botão "confirmar e sincronizar" | `PropostaGrade`, `ResultadoValidacao`, `MensagemFinal` |

O que vale saber antes de mexer:

- **A tela envia horários, não datas.** O contrato não deixa uma `Janela` cruzar a meia-noite; quem
  distribui pelos dias e quebra a janela é o Research. Por isso `EntradaOnboarding.sono` é `{inicio, fim}`.
- **Quatro escalas, três campos.** A issue pede humor, estresse, sono e fadiga; `CheckIn` tem energia,
  horas de sono e estresse. O mapeamento é explícito em `modules/checkin/mapeamento.ts`
  (`energia = 6 − fadiga`) e humor e qualidade do sono ficam no cliente.
- **A grade empilha em uma coluna a 390px.** O plano usa uma variante larga da página (72rem); as demais
  telas continuam na coluna de leitura de 46rem.
- **Bloqueio de guardrail não é erro de sistema.** `EstadoBloqueio` é a marcação única — tom de recusa, sem
  `role="alert"` — e a decisão é default-deny: qualquer categoria diferente de `OK` bloqueia, inclusive
  uma que a tela ainda não conheça.
- **O mock responde os cinco passos.** Com `NEXT_PUBLIC_API_MODE=mock` (o padrão), `web/src/mocks` serve as
  fixtures da [0.2]; `localStorage["studybuddy.cenario"]` escolhe o plano (`valida`, `reprovado`,
  `reducao_danos`, `sobrecarga`) e os bloqueios (`bloqueio`, `bloqueio_clinico`).

# Como rodar

- Frontend: `cd web && npm ci && npm run dev`.
- Modo mock (padrão): `NEXT_PUBLIC_API_MODE` ausente ou `mock`. O fluxo responde com as fixtures da
  [0.2], copiadas por `web/scripts/sincronizar-mocks.mjs` e validadas por `web/scripts/validar-mocks.py`.
- Modo real: `NEXT_PUBLIC_API_MODE=real` e `NEXT_PUBLIC_API_URL` apontando para a API.
- Backend: `cd api && uvicorn app.main:app --reload`, com Ollama (`bge-m3`, `qwen3:8b`) e o índice gerado.

# Lacunas conhecidas

- As rotas HTTP do fluxo (`/fluxo/*`) **não existem** no backend; hoje só o mock responde.
- `MensagemFinal` não tem fixture na [0.2]; o mock sintetiza o texto do mentor, marcado como sintético.
- `CheckIn` tem três campos, mas a issue do check-in pede quatro escalas (humor, estresse, sono,
  fadiga); a tela mapeia e guarda as duas que sobram no cliente.
- A prova de ponta a ponta depende de índice vetorial e modelo local no ar.

# Relacionados

- [Plano da tela do assistente](./docs/plano-frontend-assistente.md)
- [Plano do fluxo de estudo](./docs/plano-web-fluxo-estudo.md)

[^contratos]: Contratos JSON entre o Maestro e as skills — `api/app/modules/agentes/contratos.py`
[^schemas]: Contrato da API do assistente — `api/app/modules/assistente/schemas.py`
[^plano-assistente]: Plano da tela do assistente — `docs/plano-frontend-assistente.md`
[^plano-fluxo]: Plano do fluxo de estudo — `docs/plano-web-fluxo-estudo.md`
