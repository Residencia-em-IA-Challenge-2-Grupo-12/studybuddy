# Camada de apresentação: rotas HTTP do assistente.
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from . import service
from .schemas import InfoOut, PerguntaIn, RespostaOut

router = APIRouter(prefix="/assistente", tags=["assistente"])


@router.get("/info", response_model=InfoOut)
def info():
    """Qual pipeline este servidor roda e com quais modelos."""
    return service.info()


@router.post("/perguntar", response_model=RespostaOut)
async def perguntar(dados: PerguntaIn):
    """Responde com o pipeline do ambiente (PIPELINE) ou o pedido no corpo. Devolve o rastro de cada etapa."""
    try:
        return await run_in_threadpool(service.responder, dados.pergunta, dados.pipeline)
    except RuntimeError as exc:  # índice ausente, Ollama fora do ar
        raise HTTPException(status_code=503, detail=str(exc)) from exc
