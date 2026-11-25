"""Carrega o conjunto de avaliação (cenarios.json) e monta as entradas do Analysis a partir das fixtures da [0.2].

Cada cenário diz a fixture de contexto, os ajustes (índice, prazos, horas, materiais removidos), a rota do
Maestro e, nos de reajuste, a proposta de partida e as violações (fixture ou detectadas por `regras.py`
sobre blocos plantados). Nada aqui chama outro agente.
"""

import json
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
API_DIR = AQUI.parents[3] / "api"
FIXTURES = API_DIR / "tests" / "fixtures"
ARQUIVO = AQUI / "cenarios.json"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.modules.agentes.analysis import AgenteAnalysis  # noqa: E402
from app.modules.agentes.analysis.janelas import hora, minutos  # noqa: E402
from app.modules.agentes.analysis.pomodoro import ritmo  # noqa: E402
from app.modules.agentes.analysis.tecnicas import TECNICA_PADRAO  # noqa: E402
from app.modules.agentes.contratos import (  # noqa: E402
    BlocoEstudo, ContextoEstudante, DiretivaMaestro, PropostaGrade, ResultadoValidacao, Violacao,
)

from . import regras  # noqa: E402


@dataclass
class Entrada:
    cenario: dict
    ctx: ContextoEstudante
    diretiva: DiretivaMaestro | None
    proposta: PropostaGrade | None = None          # só nos de reajuste: a proposta reprovada
    violacoes: list[Violacao] | None = None        # só nos de reajuste

    @property
    def id(self) -> str:
        return self.cenario["id"]

    @property
    def reajuste(self) -> bool:
        return self.cenario.get("rota") == "reajustar"

    @property
    def esperado(self) -> dict:
        return self.cenario["esperado"]


def carregar(caminho: Path = ARQUIVO) -> list[dict]:
    return json.loads(caminho.read_text(encoding="utf-8"))["cenarios"]


def _fixture(pasta: str, nome: str) -> str:
    return (FIXTURES / pasta / f"{nome}.json").read_text(encoding="utf-8")


def contexto(c: dict) -> ContextoEstudante:
    ctx = ContextoEstudante.model_validate_json(_fixture("contexto", c["contexto"]))
    ajustes = c.get("ajustes", {})
    dados = ctx.model_dump(mode="json")
    if "indice_capacidade" in ajustes:
        dados["indice_capacidade"] = ajustes["indice_capacidade"]
    remover = set(ajustes.get("remover", []))
    mudancas = ajustes.get("materiais", {})
    desconhecidos = (remover | set(mudancas)) - {m["id"] for m in dados["materiais"]}
    if desconhecidos:
        raise ValueError(f"cenário {c['id']}: materiais que a fixture não tem: {sorted(desconhecidos)}")
    dados["materiais"] = [{**m, **mudancas.get(m["id"], {})} for m in dados["materiais"] if m["id"] not in remover]
    return ContextoEstudante.model_validate(dados)


def _plantar(p: PropostaGrade, ctx: ContextoEstudante, plantas: list[dict]) -> PropostaGrade:
    """Acrescenta blocos em horários proibidos, com o ritmo e a técnica que o Analysis usaria."""
    r = ritmo(ctx.indice_capacidade)
    materiais = {m.id: m for m in ctx.materiais}
    novos = []
    for pl in plantas:
        m = materiais[pl["material"]]
        inicio = time.fromisoformat(pl["inicio"])
        novos.append(BlocoEstudo(
            id=pl["id"], dia=date.fromisoformat(pl["dia"]), inicio=inicio, fim=hora(minutos(inicio) + r.foco_min),
            disciplina=m.disciplina, material_id=m.id, carga=m.carga, tecnica=TECNICA_PADRAO[m.carga][0],
            foco_min=r.foco_min, pausa_min=r.pausa_min))
    return p.model_copy(update={"blocos": p.blocos + novos})


def montar(c: dict) -> Entrada:
    ctx = contexto(c)
    rota = c.get("rota", "planejar")
    diretiva = DiretivaMaestro(intencao=c["descricao"], rota=rota)
    if rota != "reajustar":
        return Entrada(c, ctx, diretiva)
    proposta = (PropostaGrade.model_validate_json(_fixture("proposta", c["proposta"])) if c.get("proposta")
                else AgenteAnalysis().propor(ctx))
    proposta = _plantar(proposta, ctx, c.get("plantar", []))
    if c.get("violacoes"):
        violacoes = ResultadoValidacao.model_validate_json(_fixture("resultado", c["violacoes"])).violacoes
    else:
        violacoes = regras.detectar(proposta, ctx)
    return Entrada(c, ctx, diretiva, proposta, violacoes)


def entradas(caminho: Path = ARQUIVO) -> list[Entrada]:
    return [montar(c) for c in carregar(caminho)]
