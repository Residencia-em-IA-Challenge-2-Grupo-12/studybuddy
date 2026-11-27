"""Runner das métricas do Research Agent ([2.6] Issue #41). Roda a partir de `pesquisa/`:

    python -m metricas.agentes.research.runner                          # avaliação determinística + RAG (sem LLM)
    python -m metricas.agentes.research.runner --llm llama3.1:8b        # + curadoria via LLM local
    python -m metricas.agentes.research.runner --llm llama3.1:8b --juiz # + fidelidade via LLM-juiz

Gera saídas em `pesquisa/metricas/relatorios/`:
  - `research_<nome>.csv`: uma linha por cenário;
  - `research_<nome>.json`: saídas brutas e métricas agregadas;
  - `research_<nome>.md`: tabela-resumo (métrica, meta, resultado, atingiu?).
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from langchain_core.documents import Document

from experimentos.modelos.agentes.research import (
    _buscador_deterministico_offline,
    aderencia_cronotipo_e_estado,
    contexto_do_juiz_research,
)

from app.modules.agentes.research import SaidaResearchLLM, montar_prompt_research

from . import metricas as mt
from .cenarios import EntradaResearch, entradas

RELATORIOS = Path(__file__).resolve().parents[2] / "relatorios"


def _obter_buscador():
    try:
        from app.modules.rag import repository as rag_repo

        rag_repo.buscar("teste", k=1)
        return lambda q, k: rag_repo.buscar(q, k=k)
    except Exception:
        return _buscador_deterministico_offline()


def avaliar(e: EntradaResearch, buscador=None) -> tuple[dict, dict]:
    fn_busca = buscador or _buscador_deterministico_offline()
    c_val = mt.contrato_valido(e.ctx_montado)
    c_db = mt.persistencia_integra(e.ctx_montado, e.agente.repositorio)
    c_circ = mt.integridade_circadiana_janelas(e.ctx_montado, e.esperado)
    c_cap = mt.precisao_checkin_capacidade(e.ctx_montado, e.esperado)
    c_ag = mt.consistencia_agenda(e.ctx_montado, e.agente, e.agenda, e.esperado)
    rec = mt.avaliar_recuperacao(e.ctx_montado, e.agente, e.cenario, fn_busca)

    ok_rotulo, erros = mt.rotulo(
        e.ctx_montado,
        e.esperado,
        cIntegridade=c_circ,
        cCapacidade=c_cap,
        cAgenda=c_ag,
        rec=rec,
    )

    linha = {
        "cenario": e.id,
        "cronotipo": e.ctx_montado.cronotipo,
        "indice_capacidade": e.ctx_montado.indice_capacidade,
        "contrato_valido": c_val,
        "persistencia_integra": c_db,
        "integridade_circadiana": c_circ,
        "precisao_capacidade": c_cap,
        "consistencia_agenda": c_ag,
        "porteiro_ok": rec["porteiro_ok"],
        "hit_rate": rec["hit_rate"],
        "mrr": rec["mrr"],
        "fontes_recuperadas": ";".join(rec["fontes_recuperadas"]),
        "rotulo": ok_rotulo,
        "erros": "; ".join(erros),
    }
    return linha, {"contexto": e.ctx_montado.model_dump(mode="json"), "recuperacao": rec}


def curar_com_llm(e: EntradaResearch, modelo: str, juiz, buscador) -> dict:
    from app.modules.rag import llm

    relato = e.agente.curar_recomendacao(
        e.ctx_montado,
        chat=llm.research(modelo),
        buscador=buscador,
    )
    falhou_json = relato.motivo_fallback.startswith(("JSON", "falha"))
    total_cit = len(relato.fontes_citadas) + len(relato.citacoes_removidas)

    aderencia = 0.0
    if relato.usou_llm:
        saida_obj = SaidaResearchLLM(
            foco_recomendado=relato.foco_recomendado,
            orientacao_circadiana=relato.orientacao_circadiana,
            sintese_evidencias=relato.sintese_evidencias,
        )
        aderencia = float(
            aderencia_cronotipo_e_estado(
                saida_obj,
                e.ctx_montado.cronotipo,
                relato.estado_capacidade,
            )
        )

    reg = {
        "cenario": e.id,
        "modelo": modelo,
        "usou_llm": relato.usou_llm,
        "motivo_fallback": relato.motivo_fallback,
        "segundos": relato.segundos,
        "json_valido": float(not falhou_json),
        "citacao_valida": float(relato.usou_llm),
        "citacoes_mantidas": (len(relato.fontes_citadas) / total_cit) if total_cit and not falhou_json else None,
        "aderencia_cronotipo": aderencia,
        "foco_recomendado": relato.foco_recomendado,
        "orientacao_circadiana": relato.orientacao_circadiana,
        "sintese_evidencias": relato.sintese_evidencias,
        "fontes": relato.fontes_citadas,
    }

    if juiz is not None and relato.usou_llm:
        trechos_docs = [
            Document(page_content=ev.texto, metadata={"source": ev.source, "chunk_id": ev.chunk_id})
            for ev in relato.evidencias
        ]
        prompt = montar_prompt_research(e.ctx_montado, trechos_docs)
        ctx_juiz = contexto_do_juiz_research(prompt, trechos_docs)
        texto_resp = f"{relato.foco_recomendado} {relato.orientacao_circadiana} {relato.sintese_evidencias}"
        afirmacoes = juiz.fidelidade(ctx_juiz, texto_resp)
        reg["fidelidade"] = (
            sum(bool(a["sustentada"]) for a in afirmacoes) / len(afirmacoes) if afirmacoes else 0.0
        )
        reg["afirmacoes"] = afirmacoes

    return reg


def _csv(caminho: Path, linhas: list[dict], ignorar: tuple[str, ...] = ()) -> None:
    if not linhas:
        return
    campos = list(dict.fromkeys(k for l in linhas for k in l if k not in ignorar))
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def _fmt(meta: mt.Meta, v) -> str:
    if v is None:
        return "–"
    return f"{v:.0%}" if meta.fmt == "pct" else str(v)


def tabela_resumo(agregado: dict) -> str:
    linhas = ["| Métrica | Meta | Resultado | Atingiu? |", "| :-- | :-- | --: | :-: |"]
    for meta in mt.METAS:
        v = agregado.get(meta.chave)
        atingiu = "–" if v is None or meta.alvo == "–" else ("sim" if meta.ok(v) else "**não**")
        linhas.append(f"| {meta.nome} | {meta.alvo} | {_fmt(meta, v)} | {atingiu} |")
    return "\n".join(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--llm", help="modelo do Ollama para a curadoria (sem isto, só a parte determinística + RAG)")
    p.add_argument("--juiz", action="store_true", help="com --llm: fidelidade pelo LLM-juiz")
    p.add_argument("--modelo-juiz", help="padrão: gemma3:12b, ou qwen3:8b se o julgado for gemma")
    p.add_argument("--nome", help="sufixo dos arquivos (padrão: o modelo, ou 'deterministico')")
    args = p.parse_args()

    nome = args.nome or (args.llm.replace(":", "_") if args.llm else "deterministico")
    juiz, modelo_juiz = None, None
    if args.llm and args.juiz:
        from experimentos.modelos.rodar import familia
        from metricas.geracao.juiz import Juiz

        modelo_juiz = args.modelo_juiz or ("qwen3:8b" if familia(args.llm) == "gemma" else "gemma3:12b")
        if familia(modelo_juiz) == familia(args.llm):
            raise SystemExit(f"o juiz {modelo_juiz} é da mesma família do julgado {args.llm}")
        juiz = Juiz(modelo_juiz)

    buscador = _obter_buscador()
    inicio = time.perf_counter()
    linhas, brutos, llm_regs = [], [], []
    for e in entradas():
        linha, bruto = avaliar(e, buscador=buscador)
        print(f"  {e.id}: rótulo={'ok' if linha['rotulo'] else 'X ' + linha['erros']}")
        if args.llm and not e.esperado.get("barrada_porteiro"):
            reg_llm = curar_com_llm(e, args.llm, juiz, buscador)
            bruto["curadoria_llm"] = reg_llm
            llm_regs.append(reg_llm)
        linhas.append(linha)
        brutos.append({"cenario": e.id, "linha": linha, **bruto})

    agregado = mt.agregar(linhas, llm_regs)
    RELATORIOS.mkdir(parents=True, exist_ok=True)

    def saida(sufixo: str) -> Path:
        return RELATORIOS / f"research_{nome}{sufixo}"

    _csv(saida(".csv"), linhas)
    _csv(saida("_llm.csv"), llm_regs, ignorar=("afirmacoes",))
    saida(".json").write_text(
        json.dumps(
            {"llm": args.llm, "juiz": modelo_juiz, "agregado": agregado, "cenarios": brutos},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    cmd = (
        "python -m metricas.agentes.research.runner"
        + (f" --llm {args.llm}" if args.llm else "")
        + (" --juiz" if juiz else "")
    )
    saida(".md").write_text(
        f"# Métricas do Research Agent: {nome}\n\n"
        f"Gerado por `{cmd}` (a partir de `pesquisa/`), "
        f"{len(linhas)} cenários de `metricas/agentes/research/cenarios.json`"
        + (f", {len(llm_regs)} curadorias do `{args.llm}`" if args.llm else "")
        + (f", juiz `{modelo_juiz}`" if juiz else "")
        + ".\n\n"
        + tabela_resumo(agregado)
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{tabela_resumo(agregado)}\n\n{len(linhas)} cenários em {time.perf_counter() - inicio:.2f}s -> {saida('.*')}")


if __name__ == "__main__":
    main()
