"""Contratos JSON entre o Maestro e as skills ([0.1]).

A comunicação interna é só JSON validado: cada agente recebe e devolve um destes modelos, nunca texto livre
no controle. Cada contrato tem um dono, e só o dono muda o contrato, por PR, com o aval de quem consome:

| Modelo                              | Dono (produz)            | Quem consome                         |
| :---------------------------------- | :----------------------- | :----------------------------------- |
| Veredito                            | Validation (guardrails)  | Maestro                              |
| DiretivaMaestro                     | Maestro                  | todos                                |
| ContextoEstudante                   | Research                 | Analysis, Validation, Communication  |
| PropostaGrade, BlocoEstudo          | Analysis                 | Validation, Communication            |
| ResultadoValidacao, Violacao        | Validation               | Maestro, Analysis                    |
| MensagemFinal                       | Communication            | Maestro, web                         |
| ProvedorAgenda (interface)          | Research                 | Maestro                              |

Convenções:
- Datas são `date` (ISO "2026-11-30") e horários são `time` ("08:30"). Uma janela não cruza a meia-noite:
  o sono das 23h às 7h vira duas janelas (23:00-23:59 de um dia e 00:00-07:00 do seguinte).
- `extra="forbid"`: campo a mais é erro. Assim uma saída do LLM com chave inventada não passa calada.
- `esquema(Modelo)` gera o JSON Schema para usar como `format` no Ollama.
"""

from datetime import date, time
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

CargaCognitiva = Literal["alta", "baixa"]
Cronotipo = Literal["matutino", "vespertino", "noturno"]
Regra = Literal["CONFLITO_AGENDA", "INTEGRIDADE_CIRCADIANA", "SOBRECARGA"]


class Contrato(BaseModel):
    model_config = ConfigDict(extra="forbid")


def esquema(modelo: type[BaseModel]) -> dict:
    """JSON Schema do contrato, para a saída estruturada do Ollama (`format=`)."""
    return modelo.model_json_schema()


# ---------------------------------------------------------------- tipos base
class Janela(Contrato):
    """Intervalo de um dia, [inicio, fim). Usado para livres, ocupados, picos, vales, sono e refeições."""

    dia: date
    inicio: time
    fim: time

    @model_validator(mode="after")
    def _ordem(self):
        if self.inicio >= self.fim:
            raise ValueError(f"janela de {self.dia}: inicio ({self.inicio}) precisa ser antes do fim ({self.fim})")
        return self


class CheckIn(Contrato):
    """Como o estudante acordou. 1 = muito baixo, 5 = muito alto."""

    energia: int = Field(ge=1, le=5)
    horas_sono: float = Field(ge=0, le=24)
    estresse: int = Field(ge=1, le=5)


class Material(Contrato):
    id: str
    disciplina: str
    titulo: str
    carga: CargaCognitiva  # alta: exatas, programação, resolução de problemas; baixa: leitura leve, flashcards
    horas_estimadas: float = Field(gt=0)
    dificuldade: int = Field(ge=1, le=5)
    prazo: date | None = None


# ---------------------------------------------------------------- Research -> Analysis, Validation, Communication
class ContextoEstudante(Contrato):
    estudante_id: str
    cronotipo: Cronotipo
    semana_inicio: date
    livres: list[Janela]
    ocupados: list[Janela] = []
    picos: list[Janela] = []      # janelas de pico circadiano (alta carga)
    vales: list[Janela] = []      # janelas de vale, ex.: pós-prandial (baixa carga)
    sono: list[Janela] = []
    refeicoes: list[Janela] = []
    materiais: list[Material]
    checkin: CheckIn
    indice_capacidade: float = Field(ge=0, le=1)  # 0 = exausto, 1 = energia plena (calculado pelo Research)


# ---------------------------------------------------------------- Analysis -> Validation, Communication
class BlocoEstudo(Contrato):
    """Um bloco de foco. [inicio, fim) é o tempo de foco; a pausa vem logo depois."""

    id: str
    dia: date
    inicio: time
    fim: time
    disciplina: str
    material_id: str
    carga: CargaCognitiva
    tecnica: str
    foco_min: int = Field(gt=0)
    pausa_min: int = Field(ge=0)
    justificativa: str = ""
    fontes: list[str] = []  # ex.: ["artigo_10_pomodoro.txt"]

    @model_validator(mode="after")
    def _ordem(self):
        if self.inicio >= self.fim:
            raise ValueError(f"bloco {self.id}: inicio ({self.inicio}) precisa ser antes do fim ({self.fim})")
        return self


class PropostaGrade(Contrato):
    estudante_id: str
    semana_inicio: date
    modo: Literal["normal", "reducao_danos"] = "normal"
    blocos: list[BlocoEstudo]
    fora_da_grade: list[str] = []  # ids dos materiais que não couberam (nada é inventado fora das janelas)
    iteracao: int = Field(default=0, ge=0)  # quantos reajustes já houve


# ---------------------------------------------------------------- Validation -> Maestro, Analysis
class Violacao(Contrato):
    regra: Regra
    dia: date
    bloco_id: str | None = None   # None quando a violação é do dia inteiro (ex.: SOBRECARGA)
    mensagem: str
    excesso_min: int | None = Field(default=None, ge=0)  # quanto cortar ou mover, quando se aplica


class ResultadoValidacao(Contrato):
    status: Literal["APROVADO", "REPROVADO"]
    violacoes: list[Violacao] = []

    @model_validator(mode="after")
    def _coerente(self):
        if (self.status == "REPROVADO") != bool(self.violacoes):
            raise ValueError("REPROVADO exige ao menos uma violação; APROVADO não pode ter violações")
        return self


# ---------------------------------------------------------------- esqueletos (o dono de cada um detalha no PR)
class Veredito(Contrato):
    """Guardrails -> Maestro."""

    permitido: bool
    categoria: Literal["OK", "PROMPT_INJECTION", "HATE_SPEECH", "MEDICAL_ADVICE", "OUT_OF_SCOPE"] = "OK"
    resposta_bloqueio: str | None = None


class DiretivaMaestro(Contrato):
    """Maestro -> todos."""

    intencao: str
    rota: Literal["planejar", "reajustar", "reducao_danos", "explicar", "recusar"]
    iteracao: int = Field(default=0, ge=0)


class MensagemFinal(Contrato):
    """Communication -> Maestro, web."""

    markdown: str
    tom: str
    links: list[str] = []


class ProvedorAgenda(Protocol):
    """Research -> Maestro: Google Calendar de verdade ou AgendaFake nos testes."""

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        """Devolve (livres, ocupados) entre as duas datas."""
        ...

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        """Grava os blocos e devolve os ids dos eventos criados."""
        ...
