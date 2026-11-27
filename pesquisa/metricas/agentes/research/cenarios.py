"""Carrega o conjunto de avaliação do Research Agent (cenarios.json) e monta as entradas de teste ([2.6] Issue #41)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
API_DIR = AQUI.parents[3] / "api"
FIXTURES = API_DIR / "tests" / "fixtures"
ARQUIVO = AQUI / "cenarios.json"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.modules.agentes.contratos import CheckIn, ContextoEstudante, Material  # noqa: E402
from app.modules.agentes.research import (  # noqa: E402
    AgendaFake,
    AgenteResearch,
    EscalasCheckIn,
    GoogleCalendarProvedor,
    RepositorioEstudante,
    criar_material,
)

# Horários habituais de sono e refeição correspondentes a cada fixture base da [0.2]
PERFIL_DA_FIXTURE: dict[str, dict[str, Any]] = {
    "matutino": {"sono": (time(22, 0), time(6, 0)), "refeicoes": (time(12, 0), time(19, 0))},
    "alta_energia": {"sono": (time(22, 0), time(6, 0)), "refeicoes": (time(12, 0), time(19, 0))},
    "fadiga": {"sono": (time(22, 0), time(6, 0)), "refeicoes": (time(12, 0), time(19, 0))},
    "prazo_apertado": {"sono": (time(22, 0), time(6, 0)), "refeicoes": (time(12, 0), time(19, 0))},
    "vespertino": {"sono": (time(23, 30), time(7, 30)), "refeicoes": (time(12, 30), time(20, 0))},
    "noturno": {"sono": (time(2, 0), time(10, 0)), "refeicoes": (time(13, 0), time(18, 0))},
    "agenda_cheia": {"sono": (time(22, 30), time(5, 30)), "refeicoes": (time(18, 0), time(18, 0))},
}


@dataclass
class EntradaResearch:
    cenario: dict
    fixture_base: ContextoEstudante
    ctx_montado: ContextoEstudante
    agente: AgenteResearch
    agenda: Any

    @property
    def id(self) -> str:
        return self.cenario["id"]

    @property
    def esperado(self) -> dict:
        return self.cenario["esperado"]


def carregar(caminho: Path = ARQUIVO) -> list[dict]:
    return json.loads(caminho.read_text(encoding="utf-8"))["cenarios"]


def _fixture_contexto(nome: str) -> ContextoEstudante:
    return ContextoEstudante.model_validate_json(
        (FIXTURES / "contexto" / f"{nome}.json").read_text(encoding="utf-8")
    )


def montar(c: dict) -> EntradaResearch:
    nome_fx = c["contexto"]
    base = _fixture_contexto(nome_fx)
    ajustes = c.get("ajustes", {})
    cfg_perfil = PERFIL_DA_FIXTURE[nome_fx]

    # 1. Check-in (direto, escalas da UI ou o da fixture)
    if "escalas" in ajustes:
        checkin_in: CheckIn | EscalasCheckIn = EscalasCheckIn.model_validate(ajustes["escalas"])
    elif "checkin" in ajustes:
        checkin_in = CheckIn.model_validate(ajustes["checkin"])
    else:
        checkin_in = base.checkin

    # 2. Materiais (remoção, adição com inferência de carga ou os da fixture)
    remover = set(ajustes.get("remover_materiais", []))
    materiais: list[Material] = [m for m in base.materiais if m.id not in remover]
    for nm in ajustes.get("novos_materiais", []):
        materiais.append(
            criar_material(
                id=nm["id"],
                disciplina=nm["disciplina"],
                titulo=nm["titulo"],
                horas_estimadas=nm["horas_estimadas"],
                dificuldade=nm.get("dificuldade", 3),
                carga=nm.get("carga"),
                prazo=nm.get("prazo"),
            )
        )

    # 3. Provedor de Agenda (GoogleCalendarProvedor com eventos mockados ou AgendaFake da fixture)
    if "eventos_calendar" in ajustes:
        eventos_mock = ajustes["eventos_calendar"]

        def _http_fake(metodo: str, url: str, corpo: dict | None, headers: dict) -> dict:
            if metodo == "GET":
                return {"items": eventos_mock}
            return {"id": "gcal-created-mock"}

        agenda: Any = GoogleCalendarProvedor(
            calendar_id="primary",
            access_token="mock-token",
            sono=base.sono,
            refeicoes=base.refeicoes,
            http_client=_http_fake,
        )
    else:
        agenda = AgendaFake(livres=base.livres, ocupados=base.ocupados)

    repo = RepositorioEstudante(":memory:")
    agente = AgenteResearch(repositorio=repo, provedor_agenda=agenda)

    ctx_montado = agente.montar_contexto(
        estudante_id=base.estudante_id,
        semana_inicio=base.semana_inicio,
        cronotipo=base.cronotipo,
        sono_horario=cfg_perfil["sono"],
        refeicoes_horario=cfg_perfil["refeicoes"],
        checkin=checkin_in,
        materiais=materiais,
        provedor_agenda=agenda,
    )
    # No caso especial da fixture agenda_cheia (que tem apenas 1 refeição às 18:00), preserva as refeições da fixture
    if nome_fx == "agenda_cheia" and "eventos_calendar" not in ajustes:
        ctx_montado = ctx_montado.model_copy(update={"refeicoes": base.refeicoes})
        repo.salvar_contexto(ctx_montado)

    return EntradaResearch(
        cenario=c,
        fixture_base=base,
        ctx_montado=ctx_montado,
        agente=agente,
        agenda=agenda,
    )


def entradas(caminho: Path = ARQUIVO) -> list[EntradaResearch]:
    return [montar(c) for c in carregar(caminho)]
