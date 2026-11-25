"""Contratos da [0.1] e fixtures da [0.2]. Sem LLM: rodam no CI.

Cada subpasta de tests/fixtures/ guarda exemplos de um contrato; todos precisam validar.
"""

import json
from datetime import date, time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.agentes.contratos import (
    BlocoEstudo, ContextoEstudante, Janela, PropostaGrade, ResultadoValidacao, Veredito, Violacao, esquema,
)

FIXTURES = Path(__file__).parent / "fixtures"
CONTRATO_DA_PASTA = {
    "contexto": ContextoEstudante,
    "proposta": PropostaGrade,
    "resultado": ResultadoValidacao,
    "veredito": Veredito,
}


def carregar(pasta: str, nome: str):
    return CONTRATO_DA_PASTA[pasta].model_validate_json((FIXTURES / pasta / f"{nome}.json").read_text(encoding="utf-8"))


TODAS = sorted((p.parent.name, p) for p in FIXTURES.glob("*/*.json"))


@pytest.mark.parametrize("pasta,caminho", TODAS, ids=[f"{p}/{c.stem}" for p, c in TODAS])
def test_fixture_valida_no_contrato(pasta, caminho):
    modelo = CONTRATO_DA_PASTA[pasta]
    obj = modelo.model_validate_json(caminho.read_text(encoding="utf-8"))
    assert modelo.model_validate(json.loads(obj.model_dump_json())) == obj  # ida e volta pelo JSON


@pytest.mark.parametrize("pasta", sorted(CONTRATO_DA_PASTA))
def test_cada_contrato_tem_ao_menos_3_fixtures(pasta):
    assert len(list((FIXTURES / pasta).glob("*.json"))) >= 3


def test_janela_com_fim_antes_do_inicio_e_invalida():
    with pytest.raises(ValidationError):
        Janela(dia=date(2026, 11, 30), inicio=time(10), fim=time(9))


def test_campo_a_mais_e_rejeitado():
    dado = json.loads((FIXTURES / "proposta" / "valida.json").read_text(encoding="utf-8"))
    dado["comentario_do_llm"] = "texto livre"
    with pytest.raises(ValidationError):
        PropostaGrade.model_validate(dado)


def test_bloco_com_carga_fora_do_enum_e_invalido():
    dado = carregar("proposta", "valida").blocos[0].model_dump()
    dado["carga"] = "media"
    with pytest.raises(ValidationError):
        BlocoEstudo.model_validate(dado)


def test_resultado_precisa_ser_coerente():
    v = Violacao(regra="SOBRECARGA", dia=date(2026, 12, 2), mensagem="excesso", excesso_min=60)
    with pytest.raises(ValidationError):
        ResultadoValidacao(status="REPROVADO", violacoes=[])
    with pytest.raises(ValidationError):
        ResultadoValidacao(status="APROVADO", violacoes=[v])


def test_esquema_serve_de_format_no_ollama():
    s = esquema(PropostaGrade)
    assert s["type"] == "object" and "blocos" in s["properties"]
    assert set(s["$defs"]["BlocoEstudo"]["properties"]["carga"]["enum"]) == {"alta", "baixa"}
