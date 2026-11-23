"""Modelos de linguagem locais (Ollama), criados uma vez e reaproveitados."""

from functools import lru_cache

from app.core.config import settings


@lru_cache
def gerador():
    """O mesmo gerador do notebook: qwen3:8b, temperatura 0, sem o modo <think>."""
    from langchain_ollama import ChatOllama

    return ChatOllama(model=settings.ollama_llm_model, temperature=0, reasoning=False,
                      base_url=settings.ollama_base_url, client_kwargs={"timeout": settings.ollama_timeout_llm})


@lru_cache
def triagem():
    """Modelo da Triagem, com saída JSON de esquema fixo (structured output do Ollama)."""
    from langchain_ollama import ChatOllama

    from app.modules.agentes.triagem import ESQUEMA_DIAGNOSTICO

    return ChatOllama(model=settings.ollama_triagem_model, temperature=0, reasoning=False,
                      format=ESQUEMA_DIAGNOSTICO, base_url=settings.ollama_base_url,
                      client_kwargs={"timeout": settings.ollama_timeout_llm})


@lru_cache
def analysis(modelo: str | None = None):
    """Modelo do Analysis: técnica + justificativa em JSON de esquema fixo. `modelo` troca o do config.py
    (usado na comparação de modelos da [3.0])."""
    from langchain_ollama import ChatOllama

    from app.modules.agentes.analysis.justificativa import ESQUEMA_JUSTIFICATIVA

    return ChatOllama(model=modelo or settings.ollama_analysis_model, temperature=0, reasoning=False,
                      format=ESQUEMA_JUSTIFICATIVA, base_url=settings.ollama_base_url,
                      client_kwargs={"timeout": settings.ollama_timeout_llm})
