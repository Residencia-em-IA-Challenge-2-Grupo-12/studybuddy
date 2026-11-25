from typing import Literal

from pydantic import BaseModel, Field

Pipeline = Literal["classico", "agentes"]

# Teto da pergunta: as maiores do gabarito têm ~150 caracteres. Uma pergunta enorme iria inteira para a
# busca e para os dois LLMs (Triagem e Planejador), e pode carregar instruções para o modelo.
MAX_PERGUNTA = 1000


class PerguntaIn(BaseModel):
    pergunta: str = Field(min_length=3, max_length=MAX_PERGUNTA, examples=["Trabalho 8 horas por dia. Como encaixo o estudo sem prejudicar o sono?"])
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
    # O que o verificador de citações encontrou (None quando o porteiro recusou e não houve geração)
    verificacao: dict | None
    # Resultado da barreira de prompt injection (None quando a barreira não rodou)
    veredito: dict | None = None
    latencia_s: float
    rastro: list[EventoOut]


class InfoOut(BaseModel):
    pipeline: Pipeline
    llm: str
    triagem: str | None
    embedding: str
    top_k: int
    porteiro_tau: float | None
