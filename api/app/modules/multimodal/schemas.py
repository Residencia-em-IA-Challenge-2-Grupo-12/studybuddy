from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaginaPDF(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero: int = Field(ge=1)
    texto: str


class EvidenciaPDF(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pagina: int = Field(ge=1)
    trecho: str = Field(min_length=1)


class RespostaPDF(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["RESPONDIDA", "SEM_EVIDENCIA"]
    resposta: str = Field(min_length=1)
    evidencias: list[EvidenciaPDF]
