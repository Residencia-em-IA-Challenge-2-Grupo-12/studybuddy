"""Funções puras sobre trechos (sem LLM, sem banco)."""

from pathlib import PureWindowsPath

from langchain_core.documents import Document


def nome_fonte(source: str) -> str:
    """'../api/data/artigo_05_x.txt' (ou caminho do Windows) -> 'artigo_05_x.txt'."""
    return PureWindowsPath(source).name


def formatar_trechos(docs: list[Document]) -> str:
    """Igual ao format_retrieved_docs do notebook."""
    partes = []
    for idx, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "desconhecida")
        chunk_id = doc.metadata.get("chunk_id", "N/A")
        partes.append(f"--- [Fragmento #{idx} | Fonte: {source} | Chunk ID: {chunk_id}] ---\n{doc.page_content}")
    return "\n\n".join(partes)
