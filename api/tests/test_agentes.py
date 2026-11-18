"""Testes das decisões dos agentes. Sem LLM, sem Ollama, sem ChromaDB: rodam no CI.

Rodar (a partir de api/): python -m pytest -q
"""

import json

from langchain_core.documents import Document

from app.modules.agentes import orquestrador
from app.modules.agentes import planejador as mp
from app.modules.agentes.triagem import EXPLICACAO, PLANO, Diagnostico, interpretar
from app.modules.rag.fontes import formatar_trechos, nome_fonte
from app.modules.rag.prompts import FRASE_RECUSA


def doc(artigo: str, chunk: int = 0) -> Document:
    return Document(page_content=f"texto do {artigo}", metadata={"source": f"../api/data/{artigo}.txt", "chunk_id": chunk})


TRECHOS = [doc("artigo_05_sleep"), doc("artigo_19_clt", 1)]


# ---------------------------------------------------------------- fontes
def test_nome_fonte_aceita_caminho_unix_e_windows():
    assert nome_fonte("../api/data/artigo_05_x.txt") == "artigo_05_x.txt"
    assert nome_fonte(r"C:\dev\data\artigo_05_x.txt") == "artigo_05_x.txt"


def test_formatar_trechos_igual_ao_notebook():
    assert formatar_trechos(TRECHOS[:1]) == (
        "--- [Fragmento #1 | Fonte: ../api/data/artigo_05_sleep.txt | Chunk ID: 0] ---\ntexto do artigo_05_sleep")


# ---------------------------------------------------------------- Triagem
def diag_json(**kw) -> str:
    base = {"problema_principal": "conciliar_trabalho_e_estudo", "objetivo": "estudar sem perder sono",
            "restricoes": {"tempo_disponivel": "2 horas à noite", "prazo": "", "contexto": "CLT"},
            "tipo_resposta": "plano", "consultas": ["dupla jornada", "sono e memória"]}
    return json.dumps({**base, **kw})


def test_interpreta_diagnostico_valido():
    d = interpretar(diag_json())
    assert d.tipo_resposta == PLANO and d.consultas == ["dupla jornada", "sono e memória"] and not d.falhou
    assert d.restricoes_ditas() == {"tempo_disponivel": "2 horas à noite", "contexto": "CLT"}  # prazo vazio sai


def test_restricao_preenchida_com_nao_dito_conta_como_vazia():
    d = interpretar(diag_json(restricoes={"tempo_disponivel": "não especificado", "prazo": "Não mencionado.",
                                          "contexto": "estágio de 6 horas"}))
    assert d.restricoes_ditas() == {"contexto": "estágio de 6 horas"}


def test_texto_do_diagnostico_so_mostra_o_que_o_estudante_disse():
    texto = interpretar(diag_json()).como_texto()
    assert "Tempo disponível: 2 horas à noite" in texto and "Prazo" not in texto


def test_limita_consultas_e_descarta_vazias():
    d = interpretar(diag_json(consultas=["a", " ", "b", "c", "d"]))
    assert d.consultas == ["a", "b", "c"]


def test_valores_fora_do_esquema_viram_padrao():
    d = interpretar(diag_json(problema_principal="astrologia", tipo_resposta="poema"))
    assert d.problema_principal == "outro" and d.tipo_resposta == EXPLICACAO


def test_json_quebrado_vira_diagnostico_neutro():
    d = interpretar("{não é json")
    assert d.falhou and d.tipo_resposta == EXPLICACAO and d.consultas == []


# ---------------------------------------------------------------- Planejador
def test_juntar_trechos_sem_repetir_e_por_distancia():
    novo_perto, novo_longe = doc("artigo_10", 7), doc("artigo_09", 3)
    extras = [(novo_longe, 0.9), (TRECHOS[0], 0.5), (novo_perto, 0.6)]
    assert mp.juntar_trechos(TRECHOS, extras) == TRECHOS + [novo_perto, novo_longe]


def test_juntar_trechos_respeita_o_teto():
    extras = [(doc(f"artigo_{i:02d}", i), 0.5 + i / 100) for i in range(10, 20)]
    assert len(mp.juntar_trechos(TRECHOS, extras, teto=5)) == 5


def test_consultas_longe_da_base_nao_entram(monkeypatch):
    perto, longe = doc("artigo_10", 7), doc("artigo_25", 9)
    monkeypatch.setattr(mp.repository, "buscar", lambda q, k=None: [(perto, 0.7), (longe, 1.3)])
    monkeypatch.setattr(mp.repository, "barrada", lambda d: d > 1.026)
    trechos = mp.AgentePlanejador().reunir_evidencias(TRECHOS, Diagnostico(consultas=["x"]))
    assert perto in trechos and longe not in trechos


def test_formato_da_resposta_segue_a_decisao_da_triagem(monkeypatch):
    usados = []
    monkeypatch.setattr(mp, "gerar", lambda ctx, q, modelo, **kw: usados.append(modelo) or "ok")
    mp.AgentePlanejador().responder("p", TRECHOS, Diagnostico(tipo_resposta=PLANO))
    mp.AgentePlanejador().responder("p", TRECHOS, Diagnostico(tipo_resposta=EXPLICACAO))
    assert usados == [mp.PLANO_USER_PROMPT, mp.EXPLICACAO_USER_PROMPT]


# ---------------------------------------------------------------- orquestração (agentes falsos)
class TriagemFalsa:
    nome = "Triagem"

    def __init__(self):
        self.chamadas = 0

    def diagnosticar(self, pergunta):
        self.chamadas += 1
        return interpretar(diag_json())


class PlanejadorFalso:
    nome = "Planejador"

    def __init__(self, barrada=False):
        self.escopo = mp.Escopo(TRECHOS, 1.4 if barrada else 0.7, barrada)

    def verificar_escopo(self, pergunta):
        return self.escopo

    def reunir_evidencias(self, trechos, diag):
        return trechos + [doc("artigo_09", 3)]

    def responder(self, pergunta, trechos, diag):
        return f"plano com {len(trechos)} trechos [Fonte: artigo_09.txt]"


def rodar(monkeypatch, triagem, planejador):
    monkeypatch.setattr(orquestrador, "AgenteTriagem", lambda: triagem)
    monkeypatch.setattr(orquestrador, "AgentePlanejador", lambda: planejador)
    return orquestrador.responder("pergunta")


def test_porteiro_barra_antes_da_triagem(monkeypatch):
    triagem = TriagemFalsa()
    r = rodar(monkeypatch, triagem, PlanejadorFalso(barrada=True))
    assert r.resposta == FRASE_RECUSA and r.chamadas_llm == 0 and triagem.chamadas == 0 and len(r.rastro) == 1


def test_fluxo_completo_passa_o_diagnostico_e_as_evidencias(monkeypatch):
    r = rodar(monkeypatch, TriagemFalsa(), PlanejadorFalso())
    assert r.resposta == "plano com 3 trechos [Fonte: artigo_09.txt]" and r.chamadas_llm == 2
    assert r.diagnostico["tipo_resposta"] == PLANO
    assert [e.agente for e in r.rastro] == ["Planejador", "Triagem", "Planejador", "Planejador", "Verificador"]
    assert r.verificacao["citadas"] == ["artigo_09"] and not r.verificacao["alterou"]


# ---------------------------------------------------------------- Triagem: JSON fora do esquema
def test_interpretar_consultas_string_nao_vira_letras():
    d = interpretar(diag_json(consultas="sono"))
    assert d.consultas == []


def test_interpretar_null_nao_vira_texto_none():
    d = interpretar(diag_json(objetivo=None, restricoes={"prazo": None, "contexto": "CLT"}))
    assert d.objetivo == ""
    assert d.restricoes_ditas() == {"contexto": "CLT"}


def test_interpretar_restricoes_que_nao_sao_dict():
    assert interpretar(diag_json(restricoes=["2 horas"])).restricoes == {}


# ---------------------------------------------------------------- API: erros do Ollama viram 503/504
def _cliente_com_erro(monkeypatch, exc):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.modules.assistente import service

    def falha(*_a, **_k):
        raise exc

    monkeypatch.setattr(service, "responder", falha)
    return TestClient(app)


def test_ollama_fora_do_ar_responde_503(monkeypatch):
    c = _cliente_com_erro(monkeypatch, ConnectionError("Failed to connect to Ollama"))
    assert c.post("/assistente/perguntar", json={"pergunta": "Como estudar melhor?"}).status_code == 503


def test_modelo_nao_baixado_responde_503(monkeypatch):
    import ollama

    c = _cliente_com_erro(monkeypatch, ollama.ResponseError("model 'qwen3:8b' not found", 404))
    assert c.post("/assistente/perguntar", json={"pergunta": "Como estudar melhor?"}).status_code == 503


def test_ollama_lento_responde_504(monkeypatch):
    import httpx

    c = _cliente_com_erro(monkeypatch, httpx.ReadTimeout("timed out"))
    assert c.post("/assistente/perguntar", json={"pergunta": "Como estudar melhor?"}).status_code == 504


def test_env_lido_de_api_independente_do_diretorio():
    from app.core.config import API_DIR, Settings

    assert Settings.model_config["env_file"] == API_DIR / ".env"
