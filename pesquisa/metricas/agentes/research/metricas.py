"""Fórmulas das métricas do Research Agent ([2.6] Issue #41).

Definições formais, metas e referências em `docs/research_metrics.md` e `METRICAS.md`.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import time
from typing import Callable

from langchain_core.documents import Document

from app.modules.agentes.contratos import BlocoEstudo, ContextoEstudante
from app.modules.agentes.research import (
    EvidenciaRecuperada,
    buscar_evidencias,
    classificar_estado_capacidade,
)


# ---------------------------------------------------------------- 1. Métricas de Contexto, Banco e Agenda
def contrato_valido(ctx: ContextoEstudante) -> float:
    """1.0 se o ContextoEstudante faz round-trip completo pelo JSON Schema sem erro."""
    try:
        return float(ContextoEstudante.model_validate_json(ctx.model_dump_json()) == ctx)
    except ValueError:
        return 0.0


def persistencia_integra(ctx: ContextoEstudante, repo) -> float:
    """1.0 se o snapshot e os materiais salvos no RepositorioEstudante SQLite batem 100% com o contexto."""
    recuperado = repo.obter_contexto(ctx.estudante_id, ctx.semana_inicio)
    materiais_db = repo.listar_materiais(ctx.estudante_id)
    ultimo_ck = repo.obter_ultimo_checkin(ctx.estudante_id)
    ok = (
        recuperado == ctx
        and materiais_db == ctx.materiais
        and ultimo_ck is not None
        and ultimo_ck.checkin == ctx.checkin
    )
    return float(ok)


def integridade_circadiana_janelas(ctx: ContextoEstudante, esperado: dict) -> float:
    """1.0 se nenhuma janela cruza a meia-noite, o número de janelas de sono por dia e os picos/vales batem."""
    for lista in (ctx.livres, ctx.ocupados, ctx.picos, ctx.vales, ctx.sono, ctx.refeicoes):
        for j in lista:
            if j.inicio >= j.fim:
                return 0.0

    sono_por_dia = Counter(j.dia for j in ctx.sono)
    if "sono_janelas_por_dia" in esperado:
        if any(qtd != esperado["sono_janelas_por_dia"] for qtd in sono_por_dia.values()):
            return 0.0

    if "pico_inicio" in esperado and ctx.picos:
        if ctx.picos[0].inicio != time.fromisoformat(esperado["pico_inicio"]):
            return 0.0

    if "vale_inicio" in esperado and ctx.vales:
        if ctx.vales[0].inicio != time.fromisoformat(esperado["vale_inicio"]):
            return 0.0

    return 1.0


def precisao_checkin_capacidade(ctx: ContextoEstudante, esperado: dict) -> float:
    """1.0 se o `indice_capacidade` e o `estado_capacidade` batem exatamente com o gabarito."""
    estado = classificar_estado_capacidade(ctx.indice_capacidade)
    ok_indice = abs(ctx.indice_capacidade - esperado["indice_capacidade"]) < 1e-6
    ok_estado = estado == esperado["estado_capacidade"]
    return float(ok_indice and ok_estado)


def consistencia_agenda(ctx: ContextoEstudante, agente, agenda, esperado: dict) -> float:
    """1.0 se a contagem de eventos ocupados bate e o round-trip de gravação de bloco devolve ID válido."""
    if "ocupados_count" in esperado and len(ctx.ocupados) != esperado["ocupados_count"]:
        return 0.0

    bloco_teste = BlocoEstudo(
        id="b-teste-sync",
        dia=ctx.semana_inicio,
        inicio=time(8, 0),
        fim=time(8, 25),
        disciplina="Teste",
        material_id=ctx.materiais[0].id if ctx.materiais else "mat-01",
        carga="baixa",
        tecnica="Pomodoro",
        foco_min=25,
        pausa_min=5,
    )
    ids = agente.sincronizar_agenda([bloco_teste], provedor_agenda=agenda)
    return float(len(ids) == 1 and bool(ids[0]))


# ---------------------------------------------------------------- 2. Métricas de Recuperação (RAG / Acervo)
def avaliar_recuperacao(
    ctx: ContextoEstudante,
    agente,
    cenario: dict,
    buscador: Callable[[str, int], list[tuple[Document, float]]],
) -> dict:
    """Calcula Hit Rate@K, MRR e Acurácia do Porteiro L2 para o cenário."""
    ajustes = cenario.get("ajustes", {})
    esperado = cenario["esperado"]
    fontes_alvo = set(esperado.get("fontes_esperadas_alguma", []))

    if "forcar_distancia_l2" in ajustes:
        dist_forcada = float(ajustes["forcar_distancia_l2"])

        def buscador_forcado(q: str, k: int):
            res = buscador(q, k)
            return [(doc, dist_forcada) for doc, _ in res]

        fn_busca = buscador_forcado
    else:
        fn_busca = buscador

    if cenario.get("consulta_direta"):
        evidencias: list[EvidenciaRecuperada] = buscar_evidencias(
            cenario["consulta_direta"],
            k=4,
            apenas_conteudo=True,
            aplicar_porteiro=True,
            buscador=fn_busca,
        )
    else:
        _, evidencias = agente.pesquisar_evidencias(ctx, buscador=fn_busca)

    barrada_esperada = bool(esperado.get("barrada_porteiro", False))
    if barrada_esperada:
        acuracia_porteiro = float(len(evidencias) == 0)
        return {
            "hit_rate": None,
            "mrr": None,
            "porteiro_ok": acuracia_porteiro,
            "fontes_recuperadas": [],
        }

    acuracia_porteiro = float(len(evidencias) > 0)
    fontes_rec = [e.source for e in evidencias]

    if not fontes_alvo:
        return {
            "hit_rate": 1.0,
            "mrr": 1.0,
            "porteiro_ok": acuracia_porteiro,
            "fontes_recuperadas": fontes_rec,
        }

    hit = 0.0
    mrr = 0.0
    for rank, src in enumerate(fontes_rec, start=1):
        if src in fontes_alvo:
            hit = 1.0
            mrr = 1.0 / rank
            break

    return {
        "hit_rate": hit,
        "mrr": round(mrr, 4),
        "porteiro_ok": acuracia_porteiro,
        "fontes_recuperadas": fontes_rec,
    }


def rotulo(
    ctx: ContextoEstudante,
    esperado: dict,
    *,
    cIntegridade: float,
    cCapacidade: float,
    cAgenda: float,
    rec: dict,
) -> tuple[float, list[str]]:
    """Confere todas as asserções do rótulo esperado para o cenário."""
    erros: list[str] = []
    if ctx.cronotipo != esperado["cronotipo"]:
        erros.append(f"cronotipo {ctx.cronotipo} != {esperado['cronotipo']}")
    if cIntegridade < 1.0:
        erros.append("falha na integridade das janelas circadianas/sono")
    if cCapacidade < 1.0:
        erros.append(f"indice_capacidade {ctx.indice_capacidade} != {esperado['indice_capacidade']}")
    if cAgenda < 1.0:
        erros.append("falha na consistência da agenda ou contagem de ocupados")

    if "cargas_inferidas" in esperado:
        por_id = {m.id: m.carga for m in ctx.materiais}
        for mid, carga_esp in esperado["cargas_inferidas"].items():
            if por_id.get(mid) != carga_esp:
                erros.append(f"carga de {mid}: {por_id.get(mid)} != {carga_esp}")

    if rec["porteiro_ok"] < 1.0:
        erros.append("decisão incorreta do porteiro de distância L2")
    if rec["hit_rate"] is not None and rec["hit_rate"] < 1.0:
        erros.append(f"nenhuma fonte esperada encontrada em {rec['fontes_recuperadas']}")

    return float(not erros), erros


# ---------------------------------------------------------------- 3. Metas e Agregação
@dataclass(frozen=True)
class Meta:
    chave: str
    nome: str
    alvo: str
    ok: Callable[[float], bool]
    fmt: str = "pct"


METAS = [
    Meta("contrato_valido", "Validade do contrato ContextoEstudante", "100%", lambda v: v == 1.0),
    Meta("persistencia_integra", "Integridade da persistência SQLite", "100%", lambda v: v == 1.0),
    Meta("integridade_circadiana", "Integridade de janelas circadianas e sono", "100%", lambda v: v == 1.0),
    Meta("precisao_capacidade", "Precisão do check-in e índice de capacidade", "100%", lambda v: v == 1.0),
    Meta("consistencia_agenda", "Consistência de leitura/escrita da agenda", "100%", lambda v: v == 1.0),
    Meta("porteiro_ok", "Acurácia do porteiro de distância L2", "≥ 95%", lambda v: v >= 0.95),
    Meta("hit_rate", "Recuperação RAG: Hit Rate@4", "≥ 90%", lambda v: v >= 0.90),
    Meta("mrr", "Recuperação RAG: MRR (Mean Reciprocal Rank)", "≥ 80%", lambda v: v >= 0.80),
    Meta("rotulo", "Acerto integral do cenário esperado", "100%", lambda v: v == 1.0),
    Meta("json_valido", "Curadoria LLM: JSON válido no contrato", "≥ 95%", lambda v: v >= 0.95),
    Meta("citacao_valida", "Curadoria LLM: citação válida após verificador", "≥ 95%", lambda v: v >= 0.95),
    Meta("citacoes_mantidas", "Curadoria LLM: precisão das citações (ALCE)", "≥ 95%", lambda v: v >= 0.95),
    Meta("aderencia_cronotipo", "Curadoria LLM: aderência ao cronotipo e estado", "≥ 90%", lambda v: v >= 0.90),
    Meta("fidelidade", "Curadoria LLM: fidelidade ao contexto (juiz)", "≥ 85%", lambda v: v >= 0.85),
]


def _media(valores: list) -> float | None:
    limpos = [x for x in valores if x is not None]
    return round(statistics.fmean(limpos), 4) if limpos else None


def agregar(linhas: list[dict], llm_regs: list[dict]) -> dict[str, float | None]:
    return {
        "contrato_valido": _media([l["contrato_valido"] for l in linhas]),
        "persistencia_integra": _media([l["persistencia_integra"] for l in linhas]),
        "integridade_circadiana": _media([l["integridade_circadiana"] for l in linhas]),
        "precisao_capacidade": _media([l["precisao_capacidade"] for l in linhas]),
        "consistencia_agenda": _media([l["consistencia_agenda"] for l in linhas]),
        "porteiro_ok": _media([l["porteiro_ok"] for l in linhas]),
        "hit_rate": _media([l["hit_rate"] for l in linhas]),
        "mrr": _media([l["mrr"] for l in linhas]),
        "rotulo": _media([l["rotulo"] for l in linhas]),
        "json_valido": _media([r["json_valido"] for r in llm_regs]),
        "citacao_valida": _media([r["citacao_valida"] for r in llm_regs]),
        "citacoes_mantidas": _media([r["citacoes_mantidas"] for r in llm_regs]),
        "aderencia_cronotipo": _media([r["aderencia_cronotipo"] for r in llm_regs]),
        "fidelidade": _media([r.get("fidelidade") for r in llm_regs]),
    }
