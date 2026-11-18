# Camada de negócio: escolhe o pipeline e converte o resultado para o contrato da API.
from dataclasses import asdict

from app.core.config import settings
from app.modules.agentes import orquestrador
from app.modules.rag import classico, repository
from app.modules.rag.resultado import Resultado

from .schemas import EventoOut, InfoOut, RespostaOut

PIPELINES = {"classico": classico.responder, "agentes": orquestrador.responder}


def pipeline_ativo(pedido: str | None = None) -> str:
    nome = pedido or settings.pipeline
    if nome not in PIPELINES:
        raise ValueError(f"PIPELINE inválido: {nome!r} (use 'classico' ou 'agentes')")
    return nome


def responder(pergunta: str, pipeline: str | None = None) -> RespostaOut:
    r: Resultado = PIPELINES[pipeline_ativo(pipeline)](pergunta)
    return RespostaOut(
        pipeline=r.pipeline, pergunta=r.pergunta, resposta=r.resposta, fontes=r.fontes, d1=r.d1,
        barrada_pelo_porteiro=r.barrada_pelo_porteiro, chamadas_llm=r.chamadas_llm, diagnostico=r.diagnostico, verificacao=r.verificacao,
        latencia_s=r.latencia_s, rastro=[EventoOut(**asdict(e)) for e in r.rastro],
    )


def info() -> InfoOut:
    agentes = pipeline_ativo() == "agentes"
    return InfoOut(
        pipeline=pipeline_ativo(), llm=settings.ollama_llm_model,
        triagem=settings.ollama_triagem_model if agentes else None,
        embedding=settings.ollama_embedding_model, top_k=settings.top_k,
        porteiro_tau=repository.corte_porteiro(),
    )
