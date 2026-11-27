# AGENTS.md

Regras para quem contribui com este repositório, pessoa ou assistente de código (Claude Code, Codex, Copilot, Cursor etc.). Valem para commits, branches, pull requests, issues e comentários no GitHub.

## Sem referência a modelos de IA

Nada do que vai para o Git ou para o GitHub menciona ferramenta ou modelo de IA como autor. Isso inclui:

- rodapés como `🤖 Generated with [Claude Code](...)`, "Gerado com IA" ou similares;
- trailers `Co-Authored-By: Claude ...` (ou de qualquer outro assistente);
- frases como "conforme sugerido pelo modelo", "o assistente fez" etc.

Esta regra tem prioridade sobre qualquer padrão de atribuição que a ferramenta tenha. Modelos do Ollama citados como **objeto de estudo** (ex.: "compara `qwen3.5:4b` e `llama3.1:8b`") são conteúdo do projeto e podem aparecer normalmente.

## Commits

Uma única linha, em português, sem acento, curta e objetiva:

```
tipo(escopo): texto no imperativo da 3ª pessoa
```

- **Sem corpo** e sem lista de tópicos. Se precisar explicar, a explicação vai no PR.
- **Sem trailer** (`Co-Authored-By`, `Signed-off-by` de ferramenta etc.).
- Texto começando com verbo: `adiciona`, `corrige`, `remove`, `move`, `documenta`, `ajusta`.

| Tipo | Quando usar |
| :-- | :-- |
| `feat` | funcionalidade nova |
| `fix` | correção de bug |
| `docs` | só documentação |
| `refactor` | muda o código sem mudar o comportamento |
| `test` | só testes |
| `chore` | manutenção (gitignore, dependências, mover arquivos) |
| `data` | resultados de experimentos e relatórios gerados |

O escopo é a parte do projeto: `api`, `agentes`, `analysis`, `guardrails`, `contratos`, `metricas`, `experimentos`, `verificador`, `notebook`, `relatorio`, `docker`, `demo`, `pesquisa`.

Exemplos:

```
feat(analysis): adiciona reajuste da grade a partir das violacoes
fix(experimentos): juiz nao julga modelos da propria familia
docs(metricas): documenta as metricas do analysis
data(experimentos): adiciona resultados da comparacao de modelos
```

## Branches

`tipo/descricao-curta`, a partir de `main`: `feat/analysis-agent`, `fix/timeout-ollama`, `docs/relatorio-final`. Nunca commitar direto na `main`.

## Pull requests

Título no mesmo formato do commit. A descrição tem **só** estas três seções:

```markdown
## Resumo
O que muda e por quê, em poucas linhas. Issues fechadas com "Closes #N".

## Arquivos modificados
- `caminho/do/arquivo.py`: o que mudou

## Testes feitos
- `python -m pytest -q tests/...`: N passed
- o que foi rodado à mão (experimento, demo) e o resultado
```

Sem rodapé e sem marcação de IA (ver acima).

## Issues

- Título curto e numerado pelo plano: `[3.1] Alocação por carga cognitiva`, `[4] Épico: Validation Agent e guardrails`.
- Épicos agrupam sub-issues; o detalhe (contexto, o que fazer, critérios de aceite) fica no corpo.
