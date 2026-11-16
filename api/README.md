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
- `app/modules/agentes/` → pipeline multiagente: `triagem.py`, `planejador.py` e `orquestrador.py`.
- `app/modules/assistente/` → rotas `GET /assistente/info` e `POST /assistente/perguntar`.

O pipeline padrão vem de `PIPELINE` (`classico` ou `agentes`); o corpo do `POST` pode sobrescrever.
Precisa do Ollama com `bge-m3` e `qwen3:8b`. Detalhes em `pesquisa/Entrega4.md`.

## Testes e demonstração
```
python -m pytest -q   # decisões dos agentes, sem LLM (rodam no CI)
python demo.py        # os agentes colaborando, nos dois pipelines
python demo.py -i     # interativo: digite perguntas até "sair" (:ambos compara os pipelines)
```
