"""Juiz LLM para o que a regra não mede: adequação do tom e fidelidade às evidências.

O juiz é um modelo diferente do gerador (padrão: gemma3:12b julgando o qwen3:8b) e devolve JSON de
esquema fixo. A nota é calculada em Python a partir do veredito, nunca pedida ao modelo em texto livre.
"""

import json
import os
from typing import Dict, List, Sequence

from metricas.geracao.juiz import ESQUEMA_FIDELIDADE, PROMPT_FIDELIDADE

MODELO_JUIZ = os.getenv("OLLAMA_JUIZ_MODEL", "gemma3:12b")

PROMPT_TOM = """Você avalia o TOM de uma mensagem de um mentor de estudos.

CHECK-IN: humor {humor}/5, estresse {estresse}/5, sono {sono}/5, fadiga {fadiga}/5
TOM ESPERADO: {tom_esperado}
MENSAGEM: {abertura}

Dê uma nota de 0 a 2:
- 2: o tom combina claramente com o estado do check-in (acolhedor quando há fadiga, estresse ou humor baixo; desafiador quando há alta energia; equilibrado nos demais).
- 1: o tom é neutro ou só parcialmente adequado.
- 0: o tom é oposto ao estado (por exemplo, cobrança dura num check-in de exaustão).
Julgue só o tom. Não avalie o conteúdo do plano, a naturalidade nem a gramática."""

ESQUEMA_TOM = {
    "type": "object",
    "properties": {
        # nota antes da justificativa: o juiz se compromete com o veredito antes de explicar
        "nota": {"type": "integer", "enum": [0, 1, 2]},
        "justificativa": {"type": "string"},
    },
    "required": ["nota", "justificativa"],
}


class JuizCommunication:
    def __init__(self, modelo: str = MODELO_JUIZ) -> None:
        from langchain_ollama import ChatOllama

        self.modelo = modelo
        self._tom = ChatOllama(model=modelo, temperature=0, format=ESQUEMA_TOM)
        self._fidelidade = ChatOllama(model=modelo, temperature=0, format=ESQUEMA_FIDELIDADE)

    def adequacao_tom(self, checkin: Dict, tom_esperado: str, abertura: str) -> Dict:
        pedido = PROMPT_TOM.format(tom_esperado=tom_esperado, abertura=abertura, **checkin)
        saida = json.loads(self._tom.invoke(pedido).content)
        nota = int(saida["nota"])
        return {"nota": nota, "score": round(nota / 2, 4), "justificativa": saida.get("justificativa", "")}

    def fidelidade(self, evidencias: Sequence[Dict], abertura: str) -> Dict:
        """Fração das afirmações da abertura sustentadas pelos trechos entregues ao agente (RAGAS)."""
        contexto = "\n".join(f"[Fonte: {e['fonte']}] {e['trecho']}" for e in evidencias)
        saida = json.loads(self._fidelidade.invoke(
            PROMPT_FIDELIDADE.format(contexto=contexto, resposta=abertura)).content)
        afirmacoes: List[Dict] = saida["afirmacoes"]
        sustentadas = sum(bool(a["sustentada"]) for a in afirmacoes)
        return {
            "afirmacoes": afirmacoes,
            "total": len(afirmacoes),
            "sustentadas": sustentadas,
            "score": round(sustentadas / len(afirmacoes), 4) if afirmacoes else None,
        }
