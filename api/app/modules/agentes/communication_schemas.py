"""Contrato provisório do agente Communication até a issue 0.1 (#11) definir o oficial.

Os nomes seguem a tabela da #11. Só os campos que o Communication consome estão
modelados. Os tipos ficam reunidos neste arquivo para que a troca pela versão de
`app.modules.agentes.contratos` seja uma única mudança de importação.
"""

from typing import Literal

from pydantic import BaseModel, Field

Tom = Literal["acolhedor", "equilibrado", "desafiador"]


class BlocoEstudo(BaseModel):
    dia: str
    inicio: str
    fim: str
    disciplina: str
    material: str | None = None


class PropostaGrade(BaseModel):
    blocos: list[BlocoEstudo]


class CheckIn(BaseModel):
    humor: int = Field(ge=1, le=5)
    estresse: int = Field(ge=1, le=5)
    sono: int = Field(ge=1, le=5)
    fadiga: int = Field(ge=1, le=5)


class Evidencia(BaseModel):
    fonte: str
    trecho: str


class MensagemFinal(BaseModel):
    tom: Tom
    markdown: str
    links: list[str] = Field(default_factory=list)
