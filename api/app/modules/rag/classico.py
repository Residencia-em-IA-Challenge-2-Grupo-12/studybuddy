"""Pipeline clássico: T3 + porteiro, a configuração escolhida na Semana 3.

Busca k=5 -> porteiro (d1 > tau recusa sem LLM) -> LLM escreve a resposta -> sai. Ninguém confere.
"""

import time

from . import llm, repository
from .fontes import formatar_trechos
from .prompts import FRASE_RECUSA, RAG_SYSTEM_PROMPT, RAG_USER_PROMPT
from .resultado import Cronometro, Evento, Resultado


def gerar(contexto: str, pergunta: str, user_prompt: str = RAG_USER_PROMPT, **extra: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    pedido = user_prompt.format(context=contexto, question=pergunta, **extra)
    return llm.gerador().invoke([SystemMessage(RAG_SYSTEM_PROMPT), HumanMessage(pedido)]).content.strip()


def responder(pergunta: str) -> Resultado:
    inicio = time.perf_counter()
    r = Resultado(pipeline="classico", pergunta=pergunta)

    with Cronometro() as c:
        pares = repository.buscar(pergunta)
    r.trechos = [d for d, _ in pares]
    r.d1 = pares[0][1] if pares else float("inf")
    r.barrada_pelo_porteiro = repository.barrada(r.d1)
    r.rastro.append(Evento("busca", "barrou" if r.barrada_pelo_porteiro else "buscou",
                           f"{len(pares)} trechos, d1={r.d1:.3f}, corte={repository.corte_porteiro()}", c.segundos))

    if r.barrada_pelo_porteiro:
        r.resposta = FRASE_RECUSA
    else:
        with Cronometro() as c:
            r.resposta = gerar(formatar_trechos(r.trechos), pergunta)
        r.chamadas_llm = 1
        r.rastro.append(Evento("geração", "respondeu", f"{len(r.resposta)} caracteres", c.segundos))

    r.latencia_s = round(time.perf_counter() - inicio, 2)
    return r
