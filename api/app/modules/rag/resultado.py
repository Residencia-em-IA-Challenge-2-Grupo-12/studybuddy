"""Formato de saída comum aos dois pipelines, para a API e a avaliação compararem lado a lado."""

import time
from dataclasses import dataclass, field

from langchain_core.documents import Document

from .fontes import nome_fonte


@dataclass
class Evento:
    """Uma linha do rastro: qual agente (ou etapa) agiu, o que decidiu e quanto tempo levou."""
    agente: str
    acao: str
    detalhe: str = ""
    segundos: float = 0.0


@dataclass
class Resultado:
    pipeline: str
    pergunta: str
    resposta: str = ""
    trechos: list[Document] = field(default_factory=list)
    d1: float | None = None
    barrada_pelo_porteiro: bool = False
    chamadas_llm: int = 0
    diagnostico: dict | None = None
    verificacao: dict | None = None
    latencia_s: float = 0.0
    rastro: list[Evento] = field(default_factory=list)

    @property
    def fontes(self) -> list[str]:
        vistas: list[str] = []
        for d in self.trechos:
            nome = nome_fonte(d.metadata.get("source", ""))
            if nome not in vistas:
                vistas.append(nome)
        return vistas


class Cronometro:
    """with Cronometro() as c: ...; c.segundos"""

    def __enter__(self):
        self._t = time.perf_counter()
        self.segundos = 0.0
        return self

    def __exit__(self, *exc):
        self.segundos = round(time.perf_counter() - self._t, 2)
