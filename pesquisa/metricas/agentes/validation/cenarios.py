"""Carrega os conjuntos de avaliação versionados do Validation e dos Guardrails.

Monta todas as entradas do Validation a partir das fixtures da [0.2] (`api/tests/fixtures/`)
e de um stub local de `ProvedorAgenda`, sem depender de nenhum outro agente (Analysis,
Research, Communication ou Maestro).
"""

import json
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
API_DIR = AQUI.parents[3] / "api"
FIXTURES = API_DIR / "tests" / "fixtures"
ARQUIVO_VALIDATION = AQUI / "cenarios_validation.json"
ARQUIVO_GUARDRAILS = AQUI / "cenarios_guardrails.json"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.modules.agentes.contratos import (  # noqa: E402
    BlocoEstudo,
    CheckIn,
    ContextoEstudante,
    Janela,
    PropostaGrade,
)


class AgendaStub:
    """Stub local de `ProvedorAgenda` para cenários com compromissos extras do Google Agenda."""

    def __init__(self, ocupados: list[Janela]) -> None:
        self.ocupados = ocupados

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        return [], [j for j in self.ocupados if inicio <= j.dia <= fim]

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        return [f"stub-{b.id}" for b in blocos]


@dataclass(frozen=True)
class ViolacaoEsperada:
    regra: str
    dia: date
    bloco_id: str | None = None
    excesso_min: int | None = None

    def chave(self) -> tuple[str, date, str | None]:
        return (self.regra, self.dia, self.bloco_id)


@dataclass
class EntradaValidation:
    id: str
    grupo: str
    descricao: str
    contexto: ContextoEstudante
    proposta: PropostaGrade
    provedor_agenda: AgendaStub | None
    status_esperado: str
    violacoes_esperadas: list[ViolacaoEsperada]


@dataclass(frozen=True)
class EntradaGuardrail:
    id: str
    categoria: str
    tipo: str  # direto | disfarcado | ofuscado | valido | limitrofe
    subcategoria: str
    esperado_bloqueado: bool
    mensagem: str


def _parse_hora(texto: str) -> time:
    partes = [int(p) for p in texto.strip().split(":")]
    return time(*partes)


def _montar_bloco(spec: dict) -> BlocoEstudo:
    ini = _parse_hora(spec["inicio"])
    fim = _parse_hora(spec["fim"])
    foco_min = spec.get("foco_min")
    if foco_min is None:
        foco_min = max(1, (fim.hour * 60 + fim.minute) - (ini.hour * 60 + ini.minute))
    return BlocoEstudo(
        id=spec["id"],
        dia=date.fromisoformat(spec["dia"]),
        inicio=ini,
        fim=fim,
        disciplina=spec.get("disciplina", "Cálculo I"),
        material_id=spec.get("material_id", "calc-01"),
        carga=spec.get("carga", "alta"),
        tecnica=spec.get("tecnica", "Pomodoro"),
        foco_min=foco_min,
        pausa_min=spec.get("pausa_min", 5),
        justificativa=spec.get("justificativa", ""),
        fontes=spec.get("fontes", []),
    )


def _carregar_contexto(nome: str, overrides: dict | None = None) -> ContextoEstudante:
    caminho = FIXTURES / "contexto" / f"{nome}.json"
    ctx = ContextoEstudante.model_validate_json(caminho.read_text(encoding="utf-8"))
    if not overrides:
        return ctx

    atualizacoes = {}
    if "checkin" in overrides:
        atualizacoes["checkin"] = CheckIn.model_validate(overrides["checkin"])
    for campo_janela in ("livres", "ocupados", "picos", "vales", "sono", "refeicoes"):
        if campo_janela in overrides:
            atualizacoes[campo_janela] = [Janela.model_validate(j) for j in overrides[campo_janela]]
    return ctx.model_copy(update=atualizacoes)


def _carregar_proposta(cenario: dict, ctx: ContextoEstudante) -> PropostaGrade:
    if "proposta_fixture" in cenario:
        caminho = FIXTURES / "proposta" / f"{cenario['proposta_fixture']}.json"
        proposta = PropostaGrade.model_validate_json(caminho.read_text(encoding="utf-8"))
        return proposta.model_copy(update={"estudante_id": ctx.estudante_id})
    blocos = [_montar_bloco(b) for b in cenario.get("blocos", [])]
    return PropostaGrade(
        estudante_id=ctx.estudante_id,
        semana_inicio=ctx.semana_inicio,
        blocos=blocos,
    )


def carregar_cenarios_validation(caminho: Path = ARQUIVO_VALIDATION) -> list[EntradaValidation]:
    brutos = json.loads(caminho.read_text(encoding="utf-8"))
    entradas: list[EntradaValidation] = []
    for item in brutos:
        ctx = _carregar_contexto(item["contexto_fixture"], item.get("contexto_overrides"))
        proposta = _carregar_proposta(item, ctx)
        ocupados_extra = [Janela.model_validate(j) for j in item.get("ocupados_provedor", [])]
        provedor = AgendaStub(ocupados_extra) if ocupados_extra else None

        esperado = item["esperado"]
        violacoes = [
            ViolacaoEsperada(
                regra=v["regra"],
                dia=date.fromisoformat(v["dia"]),
                bloco_id=v.get("bloco_id"),
                excesso_min=v.get("excesso_min"),
            )
            for v in esperado.get("violacoes", [])
        ]
        entradas.append(
            EntradaValidation(
                id=item["id"],
                grupo=item["grupo"],
                descricao=item["descricao"],
                contexto=ctx,
                proposta=proposta,
                provedor_agenda=provedor,
                status_esperado=esperado["status"],
                violacoes_esperadas=violacoes,
            )
        )
    return entradas


def carregar_cenarios_guardrails(caminho: Path = ARQUIVO_GUARDRAILS) -> list[EntradaGuardrail]:
    brutos = json.loads(caminho.read_text(encoding="utf-8"))
    return [
        EntradaGuardrail(
            id=item["id"],
            categoria=item["categoria"],
            tipo=item["tipo"],
            subcategoria=item["subcategoria"],
            esperado_bloqueado=bool(item["esperado_bloqueado"]),
            mensagem=item["mensagem"],
        )
        for item in brutos
    ]
