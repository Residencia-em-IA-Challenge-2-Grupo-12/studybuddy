# Camada de negócio: escolhe o pipeline e converte o resultado para o contrato da API.
import time
from dataclasses import asdict

from app.core.config import settings
from app.modules.agentes import orquestrador
from app.modules.guardrails import Categoria, FRASE_BLOQUEIO, avaliar
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
    nome = pipeline_ativo(pipeline)

    inicio = time.perf_counter()
    veredito = avaliar(pergunta)
    segundos_guardrail = round(time.perf_counter() - inicio, 4)

    if veredito.categoria is Categoria.INJECTION:
        return RespostaOut(
            pipeline=nome, pergunta=pergunta, resposta=FRASE_BLOQUEIO, fontes=[], d1=None,
            barrada_pelo_porteiro=False, chamadas_llm=0, diagnostico=None, verificacao=None,
            veredito=veredito.para_dict(), latencia_s=segundos_guardrail,
            rastro=[EventoOut(agente="Guardrail", acao="bloqueou a pergunta",
                              detalhe="; ".join(veredito.motivos), segundos=segundos_guardrail)],
        )

    r: Resultado = PIPELINES[nome](pergunta)
    r.veredito = veredito.para_dict()
    return RespostaOut(
        pipeline=r.pipeline, pergunta=r.pergunta, resposta=r.resposta, fontes=r.fontes, d1=r.d1,
        barrada_pelo_porteiro=r.barrada_pelo_porteiro, chamadas_llm=r.chamadas_llm, diagnostico=r.diagnostico, verificacao=r.verificacao,
        veredito=r.veredito, latencia_s=r.latencia_s, rastro=[EventoOut(**asdict(e)) for e in r.rastro],
    )


def info() -> InfoOut:
    agentes = pipeline_ativo() == "agentes"
    return InfoOut(
        pipeline=pipeline_ativo(), llm=settings.ollama_llm_model,
        triagem=settings.ollama_triagem_model if agentes else None,
        embedding=settings.ollama_embedding_model, top_k=settings.top_k,
        porteiro_tau=repository.corte_porteiro(),
    )
