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
def communication():
    """Modelo que escreve a abertura do Communication, configurável em OLLAMA_COMMUNICATION_MODEL."""
    from langchain_ollama import ChatOllama

    return ChatOllama(model=settings.ollama_communication_model, temperature=0, reasoning=False,
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
def guardrails():
    """Modelo classificador principal dos Guardrails (barreiras 4.4 a 4.7), com saída JSON estruturada."""
    from langchain_ollama import ChatOllama

    from app.modules.agentes.guardrails import ESQUEMA_GUARDRAILS

    return ChatOllama(
        model=settings.ollama_guardrails_model,
        temperature=0.0,
        reasoning=False,
        format=ESQUEMA_GUARDRAILS,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.ollama_timeout_guardrails},
    )


@lru_cache
def guardrails_fallback():
    """Alternativa mais leve para os Guardrails (menor RAM e latência)."""
    from langchain_ollama import ChatOllama

    from app.modules.agentes.guardrails import ESQUEMA_GUARDRAILS

    return ChatOllama(
        model=settings.ollama_guardrails_fallback_model,
        temperature=0.0,
        reasoning=False,
        format=ESQUEMA_GUARDRAILS,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.ollama_timeout_guardrails},
    )
