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


@lru_cache
def guardrails_veredito():
    """Gatekeeper unificado das barreiras 4.4 a 4.7 no contrato `Veredito` (esquema JSON compacto)."""
    from langchain_ollama import ChatOllama

    from app.modules.agentes.guardrails import ESQUEMA_VEREDITO_GATEKEEPER

    return ChatOllama(
        model=settings.ollama_guardrails_model,
        temperature=0.0,
        reasoning=False,
        format=ESQUEMA_VEREDITO_GATEKEEPER,
        num_predict=160,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.ollama_timeout_guardrails},
    )


@lru_cache
def moderacao():
    """Classificador da barreira 4.5 (HATE_SPEECH): qwen3:4b-q8_0 com esquema JSON compacto.

    Suporta também modelos nativos de moderação (ex.: `llama-guard3:1b`) caso o operador
    troque `OLLAMA_MODERACAO_MODEL` no `.env`.
    """
    from langchain_ollama import ChatOllama

    from app.modules.agentes.guardrails import ESQUEMA_HATE_SPEECH, eh_modelo_llama_guard

    modelo = settings.ollama_moderacao_model
    if eh_modelo_llama_guard(modelo):
        return ChatOllama(
            model=modelo,
            temperature=0.0,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.ollama_timeout_guardrails},
        )
    return ChatOllama(
        model=modelo,
        temperature=0.0,
        reasoning=False,
        format=ESQUEMA_HATE_SPEECH,
        num_predict=160,
        base_url=settings.ollama_base_url,
        client_kwargs={"timeout": settings.ollama_timeout_guardrails},
    )
