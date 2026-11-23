"""Testes do agente Communication. Sem LLM real e sem Ollama: rodam no CI.

Rodar (a partir de api/): python -m pytest -q
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.agentes import communication
from app.modules.agentes.communication import ACOLHEDOR, DESAFIADOR, EQUILIBRADO
from app.modules.agentes.communication_schemas import CheckIn, Evidencia, PropostaGrade
from app.modules.agentes.prompts_communication import INSTRUCOES_TOM

FIXTURES = Path(__file__).resolve().parents[2] / "pesquisa" / "fixtures" / "communication"


def carregar(nome: str):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


GRADE = PropostaGrade.model_validate(carregar("grade.json"))
EVIDENCIAS = [Evidencia.model_validate(item) for item in carregar("evidencias.json")]
CHECKINS = carregar("checkins.json")


def checkin(nome: str) -> CheckIn:
    return CheckIn(**CHECKINS[nome])


class ModeloFalso:
    def __init__(self, resposta: str = "mensagem do mentor"):
        self.resposta = resposta
        self.chamadas = []

    def invoke(self, mensagens):
        self.chamadas.append(mensagens)
        return SimpleNamespace(content=f"  {self.resposta}  ")


def usar_modelo(monkeypatch, resposta: str = "mensagem do mentor") -> ModeloFalso:
    modelo = ModeloFalso(resposta)
    monkeypatch.setattr(communication.llm, "gerador", lambda: modelo)
    return modelo


def test_checkins_opostos_geram_tons_diferentes(monkeypatch):
    usar_modelo(monkeypatch)
    fadiga = communication.montar_mensagem(GRADE, checkin("fadiga"), EVIDENCIAS)
    energia = communication.montar_mensagem(GRADE, checkin("energia"), EVIDENCIAS)
    assert fadiga.tom == ACOLHEDOR
    assert energia.tom == DESAFIADOR
    assert fadiga.tom != energia.tom


@pytest.mark.parametrize(("nome", "tom"), [
    ("fadiga", ACOLHEDOR),
    ("energia", DESAFIADOR),
    ("equilibrado", EQUILIBRADO),
])
def test_tabela_de_tons(nome, tom):
    assert communication.escolher_tom(checkin(nome)) == tom


def test_grade_aprovada_igual_e_na_mesma_ordem_nas_duas_chamadas(monkeypatch):
    usar_modelo(monkeypatch)
    primeira = communication.montar_mensagem(GRADE, checkin("fadiga"), EVIDENCIAS)
    segunda = communication.montar_mensagem(GRADE, checkin("energia"), EVIDENCIAS)
    for mensagem in (primeira, segunda):
        cursor = 0
        for bloco in GRADE.blocos:
            cabecalho = f"{bloco.dia}, {bloco.inicio}-{bloco.fim}"
            indice = mensagem.markdown.index(cabecalho, cursor)
            cursor = indice + len(cabecalho)
            assert bloco.disciplina in mensagem.markdown


def test_saida_registra_o_tom_escolhido(monkeypatch):
    usar_modelo(monkeypatch)
    mensagem = communication.montar_mensagem(GRADE, checkin("fadiga"), EVIDENCIAS)
    assert mensagem.tom == ACOLHEDOR
    assert mensagem.links == [
        "https://example.org/materiais/matematica",
        "https://example.org/materiais/historia",
    ]
    assert mensagem.markdown.startswith("mensagem do mentor")
    assert "## Seu plano da semana" in mensagem.markdown


def test_prompt_so_tem_as_evidencias_passadas(monkeypatch):
    modelo = usar_modelo(monkeypatch)
    communication.montar_mensagem(GRADE, checkin("equilibrado"), EVIDENCIAS[:1])
    prompt = modelo.chamadas[0][1].content
    assert EVIDENCIAS[0].fonte in prompt
    assert EVIDENCIAS[1].fonte not in prompt


def test_modelo_recebe_a_instrucao_do_tom(monkeypatch):
    modelo = usar_modelo(monkeypatch)
    communication.montar_mensagem(GRADE, checkin("energia"), EVIDENCIAS)
    prompt = modelo.chamadas[0][1].content
    assert DESAFIADOR in prompt
    assert INSTRUCOES_TOM[DESAFIADOR] in prompt
