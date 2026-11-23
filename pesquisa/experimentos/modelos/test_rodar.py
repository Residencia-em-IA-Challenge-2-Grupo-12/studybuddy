"""Harness sem Ollama: agente e chat falsos. Rodar (a partir de pesquisa/): python -m pytest -q experimentos"""

import csv
import json
from types import SimpleNamespace

from pydantic import BaseModel

from experimentos.modelos import rodar
from experimentos.modelos.agentes.analysis import tecnica_adequada
from experimentos.modelos.rodar import Caso, Config


class Saida(BaseModel):
    texto: str


class AgenteFake:
    nome = "fake"
    contrato = Saida
    configs_padrao = []

    def casos(self):
        return [Caso("c1", "prompt 1"), Caso("c2", "prompt 2")]

    def avaliar(self, caso, objeto):
        return {"tem_ok": None if objeto is None else float("ok" in objeto.texto)}

    def resposta(self, objeto):
        return objeto.texto

    def metricas(self):
        return ["tem_ok"]


def fabrica(cfg, esquema):
    """O 'bom' responde JSON válido; o 'ruim' responde texto solto."""
    def invoke(prompt):
        conteudo = json.dumps({"texto": "ok"}) if cfg.modelo == "bom" else "não é json"
        return SimpleNamespace(content=conteudo, response_metadata={"eval_count": 50, "eval_duration": 1e9})
    return SimpleNamespace(invoke=invoke)


def test_dois_modelos_geram_csv_e_resumo(tmp_path, monkeypatch):
    monkeypatch.setattr(rodar, "RESULTADOS", tmp_path / "resultados")
    monkeypatch.setattr(rodar, "AQUI", tmp_path)
    monkeypatch.setattr(rodar, "memoria_gb", lambda modelo: (5.0, 5.0))
    agente = AgenteFake()
    for cfg in (Config("bom"), Config("ruim")):
        rodar.salvar(agente, cfg, rodar.rodar_config(agente, cfg, agente.casos(), fabrica_chat=fabrica))
    csv_path, md_path = rodar.resumir(agente)
    linhas = {r["modelo"]: r for r in csv.DictReader(csv_path.open(encoding="utf-8"))}
    assert float(linhas["bom"]["json_valido"]) == 1.0 and float(linhas["ruim"]["json_valido"]) == 0.0
    assert float(linhas["bom"]["tem_ok"]) == 1.0 and float(linhas["bom"]["tokens_s"]) == 50.0
    assert "| bom |" in md_path.read_text(encoding="utf-8")


def test_rotulo_descreve_a_variacao():
    assert Config("qwen3:8b").rotulo == "qwen3_8b"
    assert Config("qwen3:8b", temperature=0.7, reasoning=True, formato=False).rotulo == "qwen3_8b_t0.7_think_sem_format"


def test_p95():
    assert rodar._p95([1, 2, 3, 4, 100]) == 100 and rodar._p95(list(range(1, 21))) == 19


def test_tecnica_adequada_pela_carga():
    assert tecnica_adequada("Prática intercalada", "alta")
    assert not tecnica_adequada("Flashcards com repetição espaçada", "alta")
    assert tecnica_adequada("Flashcards com repetição espaçada", "baixa")
    assert not tecnica_adequada("Prática intercalada", "baixa")


def test_juiz_nao_julga_a_propria_familia():
    assert rodar.familia("gemma4:e4b") == rodar.familia("gemma3:12b") == "gemma"
    assert rodar.familia("qwen3.5:9b") == "qwen" and rodar.familia("ministral-3:8b") == "ministral"
