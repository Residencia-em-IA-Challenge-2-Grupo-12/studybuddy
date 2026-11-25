"""Fórmulas das métricas do Analysis ([3.4]). Definições, metas e fontes em METRICAS.md.

Cada função recebe uma proposta e o contexto e devolve um número (ou None quando a métrica não se aplica ao
cenário). `agregar` junta os cenários e compara com a meta.
"""

import statistics
from collections import Counter
from dataclasses import dataclass

from app.modules.agentes.analysis import invariantes as inv
from app.modules.agentes.analysis.janelas import contido, disponivel, minutos, por_dia, sobrepoe
from app.modules.agentes.contratos import ContextoEstudante, PropostaGrade, Violacao

from . import regras


# ---------------------------------------------------------------- planejamento
def contrato_valido(p: PropostaGrade) -> float:
    try:
        return float(PropostaGrade.model_validate_json(p.model_dump_json()) == p)
    except ValueError:
        return 0.0


def integridade(p: PropostaGrade, ctx: ContextoEstudante) -> float:
    """1 se a proposta não viola nenhuma regra dura (invariantes + regras das fixtures)."""
    return float(not inv.todas(p, ctx) and not regras.detectar(p, ctx))


def aderencia_circadiana(p: PropostaGrade, ctx: ContextoEstudante) -> float | None:
    """Fração dos blocos de alta carga com o foco inteiro dentro de uma janela de pico."""
    picos = por_dia(ctx.picos)
    altas = [b for b in p.blocos if b.carga == "alta"]
    if not altas:
        return None
    return sum(contido((minutos(b.inicio), minutos(b.fim)), picos.get(b.dia, [])) for b in altas) / len(altas)


def alta_no_vale(p: PropostaGrade, ctx: ContextoEstudante) -> int:
    vales = por_dia(ctx.vales)
    return sum(b.carga == "alta" and sobrepoe((minutos(b.inicio), minutos(b.fim)), vales.get(b.dia, []))
               for b in p.blocos)


def cobertura_prazos(p: PropostaGrade, ctx: ContextoEstudante, ids: list[str]) -> float | None:
    """Dos materiais que o rótulo diz que cabem, a fração com as horas estimadas inteiras antes do prazo."""
    if not ids:
        return None
    materiais = {m.id: m for m in ctx.materiais}
    a_tempo = 0
    for mid in ids:
        m = materiais[mid]
        foco = sum(b.foco_min for b in p.blocos if b.material_id == mid and (m.prazo is None or b.dia < m.prazo))
        a_tempo += foco >= m.horas_estimadas * 60
    return a_tempo / len(ids)


def ocupacao(p: PropostaGrade, ctx: ContextoEstudante) -> float:
    """Tempo agendado (foco + pausa) / tempo disponível (livres - ocupados - sono - refeições)."""
    total = sum(b - a for iv in disponivel(ctx).values() for a, b in iv)
    usado = sum(b.foco_min + b.pausa_min for b in p.blocos)
    return usado / total if total else 0.0


def pico_diario(p: PropostaGrade) -> int:
    """Maior foco num único dia, em minutos (para ler junto com a ocupação)."""
    dias = Counter()
    for b in p.blocos:
        dias[b.dia] += b.foco_min
    return max(dias.values(), default=0)


def pausas_adequadas(p: PropostaGrade, esperado: list[int]) -> float | None:
    if not p.blocos:
        return None
    return sum([b.foco_min, b.pausa_min] == esperado for b in p.blocos) / len(p.blocos)


def rotulo(p: PropostaGrade, ctx: ContextoEstudante, esp: dict) -> tuple[float, list[str]]:
    """Confere a resposta esperada do cenário. Devolve (1 ou 0, o que não bateu)."""
    erros = []
    if "modo" in esp and p.modo != esp["modo"]:
        erros.append(f"modo {p.modo} != {esp['modo']}")
    if "ritmo" in esp and pausas_adequadas(p, esp["ritmo"]) not in (1.0, None):
        erros.append(f"ritmo diferente de {esp['ritmo']}")
    if "fora_da_grade" in esp and sorted(p.fora_da_grade) != sorted(esp["fora_da_grade"]):
        erros.append(f"fora_da_grade {sorted(p.fora_da_grade)} != {sorted(esp['fora_da_grade'])}")
    for mid in esp.get("fora_da_grade_contem", []):
        if mid not in p.fora_da_grade:
            erros.append(f"{mid} devia estar em fora_da_grade")
    if esp.get("so_baixa_carga") and any(b.carga == "alta" for b in p.blocos):
        erros.append("alta carga num dia de redução de danos")
    if "max_blocos_dia" in esp:
        por = Counter(b.dia for b in p.blocos)
        if por and max(por.values()) > esp["max_blocos_dia"]:
            erros.append(f"{max(por.values())} blocos num dia (máx. {esp['max_blocos_dia']})")
    for mid in esp.get("sem_blocos_de", []):
        if any(b.material_id == mid for b in p.blocos):
            erros.append(f"{mid} não devia ter blocos")
    if cobertura_prazos(p, ctx, esp.get("prazos_a_tempo", [])) not in (1.0, None):
        erros.append("material com prazo sem as horas inteiras antes do prazo")
    return float(not erros), erros


# ---------------------------------------------------------------- reajuste
def _foco_no_dia(p: PropostaGrade, dia) -> int:
    return sum(b.foco_min for b in p.blocos if b.dia == dia)


def reajuste(antes: PropostaGrade, depois: PropostaGrade, violacoes: list[Violacao],
             ctx: ContextoEstudante) -> dict:
    """Quantas violações sumiram sem que o reajuste criasse outra.

    Com bloco_id: resolvida se o bloco saiu ou deixou de violar as regras. SOBRECARGA: o foco do dia caiu
    pelo menos `excesso_min`. Se aparecer qualquer violação nova (invariantes ou regras), nenhuma conta."""
    restantes = {(v.bloco_id, v.regra) for v in regras.detectar(depois, ctx)}
    novas = sorted({f"{k}:{i}" for k, ids in inv.todas(depois, ctx).items() for i in ids}
                   | {f"{r}:{b}" for b, r in restantes if b not in {v.bloco_id for v in violacoes}})
    resolvidas = 0
    for v in violacoes:
        if v.regra == "SOBRECARGA":
            ok = _foco_no_dia(depois, v.dia) <= _foco_no_dia(antes, v.dia) - (v.excesso_min or 0)
        else:
            ok = (v.bloco_id, v.regra) not in restantes
        resolvidas += ok
    return {"violacoes": len(violacoes), "resolvidas": resolvidas if not novas else 0, "novas": novas,
            "regras": sorted(v.regra for v in violacoes)}


# ---------------------------------------------------------------- agregação
@dataclass(frozen=True)
class Meta:
    chave: str
    nome: str
    alvo: str                      # texto da meta, para o relatório
    ok: callable                   # valor agregado -> atingiu?
    fmt: str = "pct"               # pct | num | int


METAS = [
    Meta("contrato_valido", "Validade do contrato", "100%", lambda v: v == 1.0),
    Meta("integridade", "Integridade (regras duras)", "100%", lambda v: v == 1.0),
    Meta("alta_no_vale", "Alta carga no vale", "0 blocos", lambda v: v == 0, "int"),
    Meta("aderencia_circadiana", "Aderência circadiana", "≥ 80%", lambda v: v >= 0.8),
    Meta("cobertura_prazos", "Cobertura de prazos", "100%", lambda v: v == 1.0),
    Meta("ocupacao_max", "Uso das janelas (pior cenário)", "≤ 75%", lambda v: v <= 0.75),
    Meta("pausas_adequadas", "Adequação das pausas", "100%", lambda v: v == 1.0),
    Meta("reajuste", "Sucesso do reajuste", "100%", lambda v: v == 1.0),
    Meta("rotulo", "Acerto da resposta esperada", "100%", lambda v: v == 1.0),
    Meta("json_valido", "Justificativa: JSON válido", "≥ 95%", lambda v: v >= 0.95),
    Meta("citacao_valida", "Justificativa: citação válida", "≥ 95%", lambda v: v >= 0.95),
    Meta("citacoes_mantidas", "Justificativa: precisão das citações", "≥ 95%", lambda v: v >= 0.95),
    Meta("tecnica_adequada", "Justificativa: técnica adequada", "≥ 95%", lambda v: v >= 0.95),
    Meta("fidelidade", "Justificativa: fidelidade (juiz)", "≥ 85%", lambda v: v >= 0.85),
]


def _media(v: list) -> float | None:
    v = [x for x in v if x is not None]
    return statistics.fmean(v) if v else None


def agregar(linhas: list[dict], llm: list[dict]) -> dict[str, float | None]:
    """`linhas`: uma por cenário. `llm`: uma por material justificado (vazia sem --llm)."""
    plan = [l for l in linhas if l["tipo"] == "planejar"]
    reaj = [l for l in linhas if l["tipo"] == "reajustar"]
    total_v = sum(l["violacoes"] for l in reaj)
    return {
        "contrato_valido": _media([l["contrato_valido"] for l in linhas]),
        "integridade": _media([l["integridade"] for l in linhas]),
        "alta_no_vale": sum(l["alta_no_vale"] for l in linhas),
        "aderencia_circadiana": _media([l["aderencia_circadiana"] for l in plan]),
        "cobertura_prazos": _media([l["cobertura_prazos"] for l in plan]),
        "ocupacao_max": max((l["ocupacao"] for l in plan), default=None),
        "ocupacao_media": _media([l["ocupacao"] for l in plan]),
        "pausas_adequadas": _media([l["pausas_adequadas"] for l in plan]),
        "reajuste": (sum(l["resolvidas"] for l in reaj) / total_v) if total_v else None,
        "rotulo": _media([l["rotulo"] for l in linhas]),
        "json_valido": _media([r["json_valido"] for r in llm]),
        "citacao_valida": _media([r["citacao_valida"] for r in llm]),
        "citacoes_mantidas": _media([r["citacoes_mantidas"] for r in llm]),
        "tecnica_adequada": _media([r["tecnica_adequada"] for r in llm]),
        "fidelidade": _media([r.get("fidelidade") for r in llm]),
    }
