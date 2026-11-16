from typing import Literal

from pydantic import BaseModel, Field

Pipeline = Literal["classico", "agentes"]


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=3, examples=["Trabalho 8 horas por dia. Como encaixo o estudo sem prejudicar o sono?"])
    # Opcional: sobrescreve o pipeline do ambiente (útil para comparar os dois no mesmo servidor)
    pipeline: Pipeline | None = None


class EventoOut(BaseModel):
    agente: str
    acao: str
    detalhe: str
    segundos: float


class RespostaOut(BaseModel):
    pipeline: Pipeline
    pergunta: str
    resposta: str
    fontes: list[str]
    d1: float | None
    barrada_pelo_porteiro: bool
    chamadas_llm: int
    # Só no pipeline multiagente: o diagnóstico da Triagem (problema, restrições, tipo de resposta, consultas)
    diagnostico: dict | None
    latencia_s: float
    rastro: list[EventoOut]


class InfoOut(BaseModel):
    pipeline: Pipeline
    llm: str
    triagem: str | None
    embedding: str
    top_k: int
    porteiro_tau: float | None
