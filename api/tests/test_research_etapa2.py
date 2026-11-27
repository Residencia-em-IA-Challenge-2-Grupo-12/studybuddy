"""Testes unitários da Etapa 2 do Research Agent: Google Calendar (#15) e AgenteResearch (#16)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

import pytest
from langchain_core.documents import Document

from app.modules.agentes.analysis import AgenteAnalysis
from app.modules.agentes.contratos import BlocoEstudo, CheckIn, ContextoEstudante, Janela, Material
from app.modules.agentes.research import (
    AgendaFake,
    AgenteResearch,
    EscalasCheckIn,
    GoogleCalendarProvedor,
    RepositorioEstudante,
    SaidaResearchLLM,
    montar_payload_bloco,
    parse_evento_google,
    quebrar_evento_em_janelas,
)
from app.modules.agentes.validation import AgenteValidation

FIXTURES_CONTEXTO = Path(__file__).resolve().parent / "fixtures" / "contexto"
FIXTURES_PROPOSTA = Path(__file__).resolve().parent / "fixtures" / "proposta"


@dataclass
class _MsgFake:
    content: str


class _ChatFake:
    def __init__(self, resposta: str | Exception) -> None:
        self.resposta = resposta
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> _MsgFake:
        self.prompts.append(prompt)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return _MsgFake(content=self.resposta)


# ==============================================================================
# [2.4] Testes do Google Calendar: Leitura e Escrita (Issue #15)
# ==============================================================================
def test_quebrar_evento_em_janelas_cruzando_meia_noite():
    tz = timezone.utc
    dt_ini = datetime(2026, 11, 30, 22, 30, tzinfo=tz)
    dt_fim = datetime(2026, 12, 1, 1, 15, tzinfo=tz)

    janelas = quebrar_evento_em_janelas(dt_ini, dt_fim)
    assert janelas == [
        Janela(dia=date(2026, 11, 30), inicio=time(22, 30), fim=time(23, 59)),
        Janela(dia=date(2026, 12, 1), inicio=time(0, 0), fim=time(1, 15)),
    ]


def test_google_calendar_provedor_leitura_e_escrita_mock_http():
    chamadas: list[tuple[str, str, dict[str, Any] | None]] = []

    def http_fake(
        metodo: str,
        url: str,
        corpo: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        chamadas.append((metodo, url, corpo))
        assert headers.get("Authorization") == "Bearer token-teste-123"
        if metodo == "GET":
            return {
                "items": [
                    {
                        "id": "evt-aula-1",
                        "summary": "Aula de Cálculo",
                        "status": "confirmed",
                        "start": {"dateTime": "2026-11-30T09:00:00-03:00"},
                        "end": {"dateTime": "2026-11-30T10:00:00-03:00"},
                    },
                    {
                        "id": "evt-cancelado",
                        "summary": "Reunião cancelada",
                        "status": "cancelled",
                        "start": {"dateTime": "2026-11-30T14:00:00-03:00"},
                        "end": {"dateTime": "2026-11-30T15:00:00-03:00"},
                    },
                ]
            }
        return {"id": f"created-{len(chamadas)}"}

    provedor = GoogleCalendarProvedor(
        calendar_id="estudante@usp.br",
        access_token="token-teste-123",
        expediente_estudo=(time(7, 0), time(18, 0)),
        refeicoes=[Janela(dia=date(2026, 11, 30), inicio=time(12, 0), fim=time(13, 0))],
        http_client=http_fake,
    )

    livres, ocupados = provedor.ler_janelas(date(2026, 11, 30), date(2026, 11, 30))
    assert ocupados == [Janela(dia=date(2026, 11, 30), inicio=time(9, 0), fim=time(10, 0))]
    assert livres == [
        Janela(dia=date(2026, 11, 30), inicio=time(7, 0), fim=time(9, 0)),
        Janela(dia=date(2026, 11, 30), inicio=time(10, 0), fim=time(12, 0)),
        Janela(dia=date(2026, 11, 30), inicio=time(13, 0), fim=time(18, 0)),
    ]

    proposta_valida = (FIXTURES_PROPOSTA / "valida.json").read_text(encoding="utf-8")
    from app.modules.agentes.contratos import PropostaGrade

    grade = PropostaGrade.model_validate_json(proposta_valida)
    ids = provedor.gravar_blocos(grade.blocos[:2])
    assert len(ids) == 2
    assert ids[0].startswith("created-")
    assert chamadas[-1][0] == "POST"
    assert "[StudyBuddy]" in chamadas[-1][2]["summary"]


# ==============================================================================
# [2.5] Testes do AgenteResearch (Issue #16)
# ==============================================================================
def test_agente_research_montar_contexto_reproduz_fixture_matutino():
    fixture_mat = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "matutino.json").read_text(encoding="utf-8")
    )
    agenda = AgendaFake(livres=fixture_mat.livres, ocupados=fixture_mat.ocupados)
    agente = AgenteResearch(repositorio=RepositorioEstudante(":memory:"), provedor_agenda=agenda)

    ctx = agente.montar_contexto(
        estudante_id="est-matutino",
        semana_inicio=date(2026, 11, 30),
        cronotipo="matutino",
        sono_horario=(time(22, 0), time(6, 0)),
        refeicoes_horario=(time(12, 0), time(19, 0)),
        checkin=EscalasCheckIn(humor=3, estresse=2, sono=4, fadiga=3, horas_sono=7.0),
        materiais=fixture_mat.materiais,
    )
    assert ctx == fixture_mat


def test_agente_research_fluxo_completo_com_analysis_e_validation():
    fixture_mat = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "matutino.json").read_text(encoding="utf-8")
    )
    agenda = AgendaFake(livres=fixture_mat.livres, ocupados=fixture_mat.ocupados)
    research = AgenteResearch(provedor_agenda=agenda)

    ctx = research.montar_contexto(
        estudante_id=fixture_mat.estudante_id,
        semana_inicio=fixture_mat.semana_inicio,
        cronotipo=fixture_mat.cronotipo,
        sono_horario=(time(22, 0), time(6, 0)),
        refeicoes_horario=(time(12, 0), time(19, 0)),
        checkin=fixture_mat.checkin,
        materiais=fixture_mat.materiais,
    )

    # Consumido diretamente pelo Analysis e pelo Validation sem violação
    proposta = AgenteAnalysis().propor(ctx)
    resultado_val = AgenteValidation(provedor_agenda=agenda).validar(proposta, ctx)
    assert resultado_val.status == "APROVADO"

    ids_gravados = research.sincronizar_agenda(proposta.blocos)
    assert len(ids_gravados) == len(proposta.blocos)
    assert len(agenda.blocos_gravados) == len(proposta.blocos)


def test_agente_research_curar_recomendacao_com_llm_e_verificador_citacoes():
    ctx = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "fadiga.json").read_text(encoding="utf-8")
    )
    agente = AgenteResearch()

    docs_fakes = [
        (
            Document(
                page_content=(
                    "Durante o sono profundo, ocorre o replay neural das informações adquiridas no dia. "
                    "Reduzir o tempo de sono para menos de 7 horas diárias deteriora a capacidade de foco."
                ),
                metadata={"source": "../api/data/artigo_05_sleep_consolidation_walker.txt", "chunk_id": 14},
            ),
            0.38,
        ),
        (
            Document(
                page_content=(
                    "O autocontrole e a capacidade de tomada de decisão consciente operam como um recurso "
                    "cognitivo finito que se desgasta ao longo do dia."
                ),
                metadata={"source": "../api/data/artigo_14_willpower_depletion_baumeister.txt", "chunk_id": 34},
            ),
            0.42,
        ),
    ]

    saida_llm = SaidaResearchLLM(
        foco_recomendado="Reduzir blocos para 25 min com pausas de 10 min devido à privação de sono (4h).",
        orientacao_circadiana="Concentrar esforço leve pela manhã (08:00–11:00) e preservar o início do sono às 22:00.",
        sintese_evidencias=(
            "Dormir menos de 7 horas deteriora a capacidade de foco e a consolidação da memória "
            "[Fonte: artigo_05_sleep_consolidation_walker.txt]. Além disso, o autocontrole é um recurso "
            "finito que se desgasta ao longo do dia [Fonte: artigo_14_willpower_depletion_baumeister.txt] "
            "[Fonte: artigo_99_alucinado.txt]."
        ),
    )

    chat_fake = _ChatFake(saida_llm.model_dump_json())
    relato = agente.curar_recomendacao(
        ctx,
        chat=chat_fake,
        buscador=lambda q, k: docs_fakes,
    )

    assert relato.usou_llm is True
    assert relato.estado_capacidade == "fadiga"
    assert "artigo_05_sleep_consolidation_walker.txt" in relato.fontes_citadas
    assert "artigo_14_willpower_depletion_baumeister.txt" in relato.fontes_citadas
    assert "artigo_99" in relato.citacoes_removidas
    assert "artigo_99" not in relato.sintese_evidencias


def test_agente_research_curar_recomendacao_fallback_quando_json_invalido():
    ctx = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "alta_energia.json").read_text(encoding="utf-8")
    )
    agente = AgenteResearch()
    docs_fakes = [
        (
            Document(
                page_content="O trabalho profundo consiste em atividades realizadas em estado de foco ininterrupto.",
                metadata={"source": "../api/data/artigo_06_deep_work_newport.txt", "chunk_id": 15},
            ),
            0.31,
        )
    ]

    relato = agente.curar_recomendacao(
        ctx,
        chat=_ChatFake("{json quebrado"),
        buscador=lambda q, k: docs_fakes,
    )
    assert relato.usou_llm is False
    assert "JSON fora do esquema" in relato.motivo_fallback
    assert "artigo_06_deep_work_newport.txt" in relato.fontes_citadas
    assert "[Fonte: artigo_06_deep_work_newport.txt]" in relato.sintese_evidencias
