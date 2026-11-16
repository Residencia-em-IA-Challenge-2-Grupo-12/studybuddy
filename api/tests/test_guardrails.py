"""Guardrails sem LLM: verificador de citações e limite de tamanho da pergunta. Rodam no CI.

Rodar (a partir de api/): python -m pytest -q
"""

from fastapi.testclient import TestClient
from langchain_core.documents import Document

from app.main import app
from app.modules.assistente import service
from app.modules.assistente.schemas import MAX_PERGUNTA
from app.modules.rag import classico, repository
from app.modules.rag.prompts import FRASE_RECUSA
from app.modules.rag.verificador import NOTA_SEM_CITACAO, verificar


def doc(artigo: str) -> Document:
    return Document(page_content=f"texto do {artigo}", metadata={"source": f"../api/data/{artigo}.txt", "chunk_id": 0})


TRECHOS = [doc("artigo_05_sleep"), doc("artigo_19_clt")]


# ---------------------------------------------------------------- verificador de citações
def test_citacoes_dos_trechos_ficam_intactas():
    resposta = "- Durma 8 h [Fonte: artigo_05_sleep.txt]\n- Estude cedo [Fonte: artigo_19_clt.txt]"
    texto, v = verificar(resposta, TRECHOS)
    assert texto == resposta
    assert v.citadas == ["artigo_05", "artigo_19"] and not v.alterou


def test_citacao_de_artigo_que_o_llm_nao_recebeu_sai_do_texto():
    resposta = "- Durma 8 h [Fonte: artigo_05_sleep.txt]\n- Use Pomodoro [Fonte: artigo_10_pomodoro.txt]"
    texto, v = verificar(resposta, TRECHOS)
    assert texto == "- Durma 8 h [Fonte: artigo_05_sleep.txt]\n- Use Pomodoro"
    assert v.fora_do_contexto == ["artigo_10"] and v.citadas == ["artigo_05"] and v.alterou


def test_citacao_com_um_artigo_recebido_e_outro_nao_fica():
    resposta = "Ponto [Fonte: artigo_05_sleep.txt, artigo_10_pomodoro.txt]"
    texto, v = verificar(resposta, TRECHOS)
    assert texto == resposta and v.citadas == ["artigo_05"] and v.fora_do_contexto == []


def test_resposta_sem_citacao_ganha_a_lista_dos_trechos_consultados():
    texto, v = verificar("Durma bem antes da prova.", TRECHOS)
    assert v.sem_citacao and v.alterou
    assert texto.endswith(NOTA_SEM_CITACAO.format(fontes="artigo_05_sleep.txt, artigo_19_clt.txt"))


def test_so_citacoes_inventadas_vira_sem_citacao():
    texto, v = verificar("Use Pomodoro [Fonte: artigo_10_pomodoro.txt]", TRECHOS)
    assert "[Fonte:" not in texto and v.fora_do_contexto == ["artigo_10"] and v.sem_citacao


def test_citacao_sem_numero_de_artigo_nao_e_removida():
    texto, v = verificar("Ponto [Fonte: Fragmento #2]", TRECHOS)
    assert texto.startswith("Ponto [Fonte: Fragmento #2]") and v.fora_do_contexto == [] and v.sem_citacao


def test_recusa_passa_sem_alteracao():
    texto, v = verificar(FRASE_RECUSA, TRECHOS)
    assert texto == FRASE_RECUSA and v.recusa and not v.alterou


def test_pipeline_classico_passa_pelo_verificador(monkeypatch):
    monkeypatch.setattr(repository, "buscar", lambda q, k=None: [(d, 0.6) for d in TRECHOS])
    monkeypatch.setattr(classico, "gerar", lambda ctx, q, *a, **kw: "Use Pomodoro [Fonte: artigo_10_pomodoro.txt]")
    r = classico.responder("Como estudar melhor?")
    assert "[Fonte: artigo_10" not in r.resposta and r.verificacao["fora_do_contexto"] == ["artigo_10"]
    assert r.rastro[-1].agente == "Verificador" and r.rastro[-1].acao == "corrigiu as citações"


def test_porteiro_barra_sem_passar_pelo_verificador(monkeypatch):
    monkeypatch.setattr(repository, "buscar", lambda q, k=None: [(d, 1.4) for d in TRECHOS])
    r = classico.responder("Como investir em ações?")
    assert r.resposta == FRASE_RECUSA and r.verificacao is None


# ---------------------------------------------------------------- tamanho da pergunta
def test_pergunta_acima_do_limite_e_rejeitada_antes_do_pipeline(monkeypatch):
    chamado = []
    monkeypatch.setattr(service, "responder", lambda *a, **k: chamado.append(1))
    resp = TestClient(app).post("/assistente/perguntar", json={"pergunta": "a" * (MAX_PERGUNTA + 1)})
    assert resp.status_code == 422 and not chamado


def test_pergunta_no_limite_e_aceita(monkeypatch):
    monkeypatch.setattr(service, "responder", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("sem Ollama")))
    resp = TestClient(app).post("/assistente/perguntar", json={"pergunta": "a" * MAX_PERGUNTA})
    assert resp.status_code == 503  # passou da validação e chegou ao pipeline
