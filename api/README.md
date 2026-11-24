# dev (backend - FastAPI)

Arquitetura em camadas, organizada por módulos em `app/modules/<modulo>/`:

- `router.py`     → apresentação (HTTP)
- `service.py`    → regras de negócio
- `repository.py` → acesso a dados
- `schemas.py`    → contratos (Pydantic)

## Rodar
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Docs: http://localhost:8000/docs

## Dados e índice vetorial
- `data/` → base de conhecimento (documentos-fonte `.txt`/`.pdf`), versionada.
- `chroma_db/` → índice ChromaDB, **não versionado**. Gere/atualize rodando `pesquisa/rag_pipeline_semana2.ipynb`.
- Variáveis de ambiente (`OPENAI_API_KEY` ou `GOOGLE_API_KEY`) ficam em `api/.env` (veja `.env.example`).

## Módulos do assistente
- `app/modules/rag/` → núcleo compartilhado: busca no ChromaDB, porteiro, prompts e o pipeline clássico (T3 + porteiro).
- `app/modules/agentes/` → pipeline multiagente (`triagem.py`, `planejador.py`, `orquestrador.py`), contratos (`contratos.py`), guardrails (`guardrails.py`) e validação determinística da grade (`validation.py`).
- `app/modules/assistente/` → rotas `GET /assistente/info` e `POST /assistente/perguntar`.

O pipeline padrão vem de `PIPELINE` (`classico` ou `agentes`); o corpo do `POST` pode sobrescrever.
Precisa do Ollama com `bge-m3` e `qwen3:8b`. Detalhes em `pesquisa/Entrega4.md`.

## Contratos entre os agentes
`app/modules/agentes/contratos.py` (Pydantic). A comunicação interna é só JSON validado. Cada contrato tem um dono, e mudanças entram só por PR, com o aval do dono e de quem consome.

| Modelo | Dono (produz) | Quem consome |
| :-- | :-- | :-- |
| `Veredito` | Validation (guardrails) | Maestro |
| `DiretivaMaestro` | Maestro | todos |
| `ContextoEstudante` | Research | Analysis, Validation, Communication |
| `PropostaGrade`, `BlocoEstudo` | Analysis | Validation, Communication |
| `ResultadoValidacao`, `Violacao` | Validation | Maestro, Analysis |
| `MensagemFinal` | Communication | Maestro, web |
| `ProvedorAgenda` (interface) | Research | Maestro |

Fixtures de exemplo ficam em `tests/fixtures/<contrato>/`, e `tests/test_contratos.py` valida todas. `esquema(Modelo)` gera o JSON Schema para o `format` do Ollama.

## Guardrails e Validation
Camadas determinísticas por regra, sem LLM:

| Guardrail / Regra | Onde | O que faz |
| :-- | :-- | :-- |
| Tamanho da pergunta | `assistente/schemas.py` | De 3 a 1000 caracteres (`MAX_PERGUNTA`); fora disso, 422 antes de qualquer busca |
| Porteiro de distância | `rag/repository.py` | Pergunta longe da base (`d1 > 1,026`) é recusada sem chamar o LLM |
| Verificador de citações | `rag/verificador.py` | Remove `[Fonte: ...]` de artigo que o LLM não recebeu; sem nenhuma citação válida, acrescenta a lista dos trechos consultados. O resultado vai em `verificacao` e no rastro |
| `CONFLITO_AGENDA` | `agentes/validation.py` | Garante que nenhum bloco da `PropostaGrade` se sobreponha a compromissos ocupados (`ContextoEstudante.ocupados` e, opcionalmente, `ProvedorAgenda` do Google Agenda) |
| `INTEGRIDADE_CIRCADIANA` | `agentes/validation.py` | Garante que nenhum bloco viole janelas de sono ou refeição e nenhum bloco de alta carga caia na higiene do sono (1h antes de dormir) ou em vales circadianos |
| Erros do Ollama | `assistente/router.py` | Fora do ar ou modelo ausente: 503; lento demais (`OLLAMA_TIMEOUT_*`): 504 |

As regras do prompt (não inventar, recusar com a frase fixa, citar a fonte) continuam valendo, mas são só instrução: os guardrails acima não dependem de o modelo obedecer.

## Testes e demonstração
```
python -m pytest -q           # agentes, contratos, validation e guardrails, sem LLM (rodam no CI)
python demo_validation.py     # demonstração determinística do Validation (5 cenários, sem LLM)
python demo_validation.py -i  # modo interativo do Validation para testar horários
python demo.py                # os agentes colaborando, nos dois pipelines
python demo.py -i             # interativo: digite perguntas até "sair" (:ambos compara os pipelines)
```
