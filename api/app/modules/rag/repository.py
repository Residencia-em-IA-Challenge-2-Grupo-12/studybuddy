"""Acesso ao ChromaDB e ao porteiro de distância. Único ponto do código que toca o índice vetorial."""

import logging
from functools import lru_cache

from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger("studybuddy.rag")

# Corte calibrado por embedding (pesquisa/metricas/relatorios/comparacao_porteiro.json).
# Cada embedding tem a sua escala de distância: o corte do bge-m3 não vale para outro modelo.
PORTEIRO_TAU_CALIBRADO = {"bge-m3": 1.026}


@lru_cache
def vectorstore():
    """Abre o índice que o notebook gerou. Não reindexa: só lê."""
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings

    if not settings.chroma_dir.exists():
        raise RuntimeError(f"Índice não encontrado em {settings.chroma_dir}. Rode o notebook pesquisa/rag_pipeline_semana2.ipynb.")
    emb = OllamaEmbeddings(model=settings.ollama_embedding_model, base_url=settings.ollama_base_url)
    vs = Chroma(collection_name=settings.chroma_collection, embedding_function=emb,
                persist_directory=str(settings.chroma_dir))
    logger.info("ChromaDB aberto: %s (%s trechos)", settings.chroma_dir, vs._collection.count())
    return vs


def buscar(consulta: str, k: int | None = None) -> list[tuple[Document, float]]:
    """(trecho, distância L2) dos k mais próximos, do mais perto para o mais longe."""
    return [(d, float(s)) for d, s in vectorstore().similarity_search_with_score(consulta, k=k or settings.top_k)]


def corte_porteiro() -> float | None:
    """Corte do porteiro para o embedding ativo, ou None se o porteiro está desligado."""
    valor = settings.porteiro_tau.strip().lower()
    if valor in ("desligado", "off"):
        return None
    if valor:
        return float(valor.replace(",", "."))
    return PORTEIRO_TAU_CALIBRADO.get(settings.ollama_embedding_model.split(":")[0])


def barrada(d1: float) -> bool:
    tau = corte_porteiro()
    return tau is not None and d1 > tau
