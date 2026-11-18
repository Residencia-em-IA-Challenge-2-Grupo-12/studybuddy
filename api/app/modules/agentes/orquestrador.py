"""Orquestrador do pipeline multiagente (código simples, sem LLM).

Pergunta
  -> Planejador verifica o escopo (busca k=5 + porteiro). Barrada: recusa, 0 chamadas ao LLM.
  -> Triagem diagnostica o estudante (problema, restrições, plano ou explicação, consultas).
  -> Planejador reúne evidências (pergunta + consultas da Triagem) e escreve a resposta no formato decidido.
  -> Verificador confere as citações (só regras, sem LLM), como no pipeline clássico.
Cada passo vira um Evento no rastro, que a API devolve e a demonstração imprime.
"""

import logging
import time

from app.modules.rag.classico import conferir_citacoes
from app.modules.rag.prompts import FRASE_RECUSA
from app.modules.rag.resultado import Cronometro, Evento, Resultado

from .planejador import AgentePlanejador
from .triagem import AgenteTriagem

logger = logging.getLogger("studybuddy.agentes")


def _registrar(r: Resultado, evento: Evento) -> None:
    r.rastro.append(evento)
    logger.info("[%s] %s: %s (%.2fs)", evento.agente, evento.acao, evento.detalhe, evento.segundos)


def responder(pergunta: str) -> Resultado:
    triagem, planejador = AgenteTriagem(), AgentePlanejador()
    inicio = time.perf_counter()
    r = Resultado(pipeline="agentes", pergunta=pergunta)

    # 1. Escopo (porteiro): antes de gastar qualquer chamada ao LLM
    with Cronometro() as c:
        escopo = planejador.verificar_escopo(pergunta)
    r.trechos, r.d1, r.barrada_pelo_porteiro = escopo.trechos, escopo.d1, escopo.barrada
    if escopo.barrada:
        _registrar(r, Evento(planejador.nome, "recusou pelo porteiro",
                             f"d1={escopo.d1:.3f} acima do corte; nenhum agente chamou o LLM", c.segundos))
        r.resposta = FRASE_RECUSA
        r.latencia_s = round(time.perf_counter() - inicio, 2)
        return r
    _registrar(r, Evento(planejador.nome, "verificou o escopo",
                         f"pergunta dentro da base (d1={escopo.d1:.3f}); {len(escopo.trechos)} trechos", c.segundos))

    # 2. Triagem: diagnóstico do estudante
    with Cronometro() as c:
        diag = triagem.diagnosticar(pergunta)
    r.chamadas_llm += 1
    r.diagnostico = diag.para_dict()
    restricoes = "; ".join(f"{k}: {v}" for k, v in diag.restricoes_ditas().items()) or "nenhuma dita"
    _registrar(r, Evento(triagem.nome, f"diagnosticou → resposta tipo {diag.tipo_resposta.upper()}",
                         f"problema: {diag.problema_principal}\nobjetivo: {diag.objetivo}\nrestrições: {restricoes}\n"
                         f"consultas para o Planejador: {diag.consultas or '(nenhuma)'}"
                         + ("\nJSON inválido: diagnóstico neutro" if diag.falhou else ""), c.segundos))

    # 3. Planejador: evidências extras a partir das consultas da Triagem
    with Cronometro() as c:
        antes = len(r.trechos)
        r.trechos = planejador.reunir_evidencias(r.trechos, diag)
    _registrar(r, Evento(planejador.nome, "reuniu evidências",
                         f"+{len(r.trechos) - antes} trecho(s) pelas consultas da Triagem; {len(r.trechos)} no total: "
                         f"{', '.join(r.fontes)}", c.segundos))

    # 4. Planejador: resposta no formato decidido pela Triagem
    with Cronometro() as c:
        r.resposta = planejador.responder(pergunta, r.trechos, diag)
    r.chamadas_llm += 1
    _registrar(r, Evento(planejador.nome, f"escreveu {'o plano' if diag.tipo_resposta == 'plano' else 'a explicação'}",
                         f"{len(r.resposta)} caracteres", c.segundos))

    # 5. Verificador: citações de artigos que o Planejador não recebeu saem do texto
    conferir_citacoes(r)

    r.latencia_s = round(time.perf_counter() - inicio, 2)
    return r
