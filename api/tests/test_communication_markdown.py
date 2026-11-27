"""Testes do plano Markdown montado pelo agente Communication. Sem LLM real e sem Ollama.

Rodar (a partir de api/): python -m pytest -q
"""

import json
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from app.modules.agentes import communication
from app.modules.agentes.communication_schemas import CheckIn, Evidencia, PropostaGrade
from app.modules.rag.verificador import verificar

FIXTURES = Path(__file__).resolve().parents[2] / "pesquisa" / "fixtures" / "communication"


def carregar(nome: str):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


GRADE = PropostaGrade.model_validate(carregar("grade.json"))
EVIDENCIAS = [Evidencia.model_validate(item) for item in carregar("evidencias.json")]
CHECKINS = carregar("checkins.json")


def checkin(nome: str) -> CheckIn:
    return CheckIn(**CHECKINS[nome])


class ModeloFalso:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.chamadas = []

    def invoke(self, mensagens):
        self.chamadas.append(mensagens)
        return SimpleNamespace(content=f"  {self.resposta}  ")


def usar_modelo(monkeypatch, resposta: str = "mensagem do mentor") -> ModeloFalso:
    modelo = ModeloFalso(resposta)
    monkeypatch.setattr(communication.llm, "communication", lambda: modelo)
    return modelo


def linha_do_bloco(bloco) -> str:
    linha = f"- {bloco.dia}, {bloco.inicio}-{bloco.fim}: {bloco.disciplina}"
    if bloco.material is not None:
        linha += f". Material: [Material]({bloco.material})"
    else:
        linha += "."
    return linha


def gerar(monkeypatch, resposta: str = "mensagem do mentor") -> str:
    usar_modelo(monkeypatch, resposta)
    return communication.montar_mensagem(GRADE, checkin("equilibrado"), EVIDENCIAS).markdown


def test_plano_tem_todo_bloco_com_horario_exato(monkeypatch):
    markdown = gerar(monkeypatch)
    for bloco in GRADE.blocos:
        assert linha_do_bloco(bloco) in markdown


def test_plano_preserva_a_ordem(monkeypatch):
    markdown = gerar(monkeypatch)
    indices = [markdown.index(linha_do_bloco(bloco)) for bloco in GRADE.blocos]
    assert indices == sorted(indices)


def test_material_vira_link_e_bloco_sem_material_nao_tem_link(monkeypatch):
    markdown = gerar(monkeypatch)
    assert "[Material](https://example.org/materiais/matematica)" in markdown
    assert "[Material](None)" not in markdown


def test_plano_nao_depende_do_llm(monkeypatch):
    markdown = gerar(monkeypatch, "oi")
    for bloco in GRADE.blocos:
        assert linha_do_bloco(bloco) in markdown


def test_citacao_inventada_sai(monkeypatch):
    markdown = gerar(monkeypatch, "Abertura [Fonte: artigo_99_inventado.txt]")
    assert "artigo_99" not in markdown


def test_citacao_valida_fica(monkeypatch):
    markdown = gerar(monkeypatch, "Abertura [Fonte: artigo_05_sleep.txt]")
    assert "[Fonte: artigo_05_sleep.txt]" in markdown


def test_verificador_nao_remove_nada_na_saida_final(monkeypatch):
    markdown = gerar(monkeypatch)
    documentos = [Document(page_content=e.trecho, metadata={"source": e.fonte}) for e in EVIDENCIAS]
    _, verificacao = verificar(markdown, documentos)
    assert verificacao.fora_do_contexto == []
