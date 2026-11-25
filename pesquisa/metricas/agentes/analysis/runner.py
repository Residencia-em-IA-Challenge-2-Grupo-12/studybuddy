"""Runner das métricas do Analysis ([3.4] e [3.5]). Roda a partir de pesquisa/:

    python -m metricas.agentes.analysis.runner                          # só a parte determinística (sem Ollama)
    python -m metricas.agentes.analysis.runner --llm qwen3.5:4b         # + técnica e justificativa pelo LLM
    python -m metricas.agentes.analysis.runner --llm qwen3.5:4b --juiz  # + fidelidade pelo LLM-juiz

Sem depender dos outros agentes: as entradas vêm de cenarios.json + fixtures da [0.2], e as violações do
reajuste vêm das fixtures ou de `regras.py`. Saídas em metricas/relatorios/:
- analysis_<nome>.csv: uma linha por cenário (e, com --llm, analysis_<nome>_llm.csv: uma por material);
- analysis_<nome>.json: as saídas brutas (propostas, relatos do LLM, vereditos do juiz);
- analysis_<nome>.md: tabela-resumo (métrica, meta, resultado, atingiu?).
"""

import argparse
import csv
import json
import time
from pathlib import Path

from .cenarios import AgenteAnalysis, Entrada, entradas
from . import metricas as mt

RELATORIOS = Path(__file__).resolve().parents[2] / "relatorios"


# ---------------------------------------------------------------- parte determinística
def avaliar(e: Entrada) -> tuple[dict, dict]:
    agente = AgenteAnalysis()
    if e.reajuste:
        p = agente.reajustar(e.proposta, e.violacoes, e.ctx)
        r = mt.reajuste(e.proposta, p, e.violacoes, e.ctx)
        erros = []
        if r["regras"] != sorted(e.esperado["violacoes"]):
            erros.append(f"violações {r['regras']} != rótulo {sorted(e.esperado['violacoes'])}")
        if r["resolvidas"] < r["violacoes"]:
            erros.append(f"resolveu {r['resolvidas']}/{r['violacoes']}; novas: {r['novas']}")
        erros += mt.rotulo(p, e.ctx, {k: v for k, v in e.esperado.items() if k != "violacoes"})[1]
        linha = {"cenario": e.id, "tipo": "reajustar", "contrato_valido": mt.contrato_valido(p),
                 "integridade": mt.integridade(p, e.ctx), "alta_no_vale": mt.alta_no_vale(p, e.ctx),
                 "violacoes": r["violacoes"], "resolvidas": r["resolvidas"], "novas": ";".join(r["novas"]),
                 "rotulo": float(not erros), "erros": "; ".join(erros), "blocos": len(p.blocos),
                 "fora_da_grade": ";".join(p.fora_da_grade)}
        return linha, {"antes": e.proposta.model_dump(mode="json"), "depois": p.model_dump(mode="json"),
                       "violacoes": [v.model_dump(mode="json") for v in e.violacoes]}
    p = agente.propor(e.ctx, e.diretiva)
    ok, erros = mt.rotulo(p, e.ctx, e.esperado)
    linha = {"cenario": e.id, "tipo": "planejar", "contrato_valido": mt.contrato_valido(p),
             "integridade": mt.integridade(p, e.ctx), "alta_no_vale": mt.alta_no_vale(p, e.ctx),
             "aderencia_circadiana": mt.aderencia_circadiana(p, e.ctx),
             "cobertura_prazos": mt.cobertura_prazos(p, e.ctx, e.esperado.get("prazos_a_tempo", [])),
             "ocupacao": round(mt.ocupacao(p, e.ctx), 4), "pico_diario_min": mt.pico_diario(p),
             "pausas_adequadas": mt.pausas_adequadas(p, e.esperado["ritmo"]),
             "rotulo": ok, "erros": "; ".join(erros), "blocos": len(p.blocos), "fora_da_grade": ";".join(p.fora_da_grade)}
    return linha, {"proposta": p.model_dump(mode="json")}


# ---------------------------------------------------------------- parte com LLM
def justificar(e: Entrada, proposta_json: dict, modelo: str, juiz, cache: dict) -> list[dict]:
    from experimentos.modelos.agentes.analysis import contexto_do_juiz, tecnica_adequada

    from app.modules.agentes.analysis import justificativa as j
    from app.modules.agentes.contratos import PropostaGrade
    from app.modules.rag import llm

    proposta = PropostaGrade.model_validate(proposta_json)

    def buscar(consulta: str):
        if consulta not in cache:
            cache[consulta] = j._buscar_padrao(consulta)
        return cache[consulta]

    nova, relatos = j.justificar(proposta, e.ctx, chat=llm.analysis(modelo), buscar=buscar)
    materiais = {m.id: m for m in e.ctx.materiais}
    estado = j.estado_da_proposta(proposta, e.ctx)
    saidas = []
    for rel in relatos:
        m = materiais[rel.material_id]
        bloco = next(b for b in nova.blocos if b.material_id == m.id)
        falhou = rel.motivo_padrao.startswith(("JSON", "falha"))
        total = len(rel.citadas) + len(rel.removidas)
        reg = {"cenario": e.id, "material": m.id, "carga": m.carga, "modelo": modelo, "usou_llm": rel.usou_llm,
               "motivo_padrao": rel.motivo_padrao, "segundos": rel.segundos,
               "json_valido": float(not falhou), "citacao_valida": float(rel.usou_llm),
               "citacoes_mantidas": (len(rel.citadas) / total) if total and not falhou else None,
               "tecnica_adequada": float(rel.usou_llm and tecnica_adequada(bloco.tecnica, m.carga)),
               "tecnica": bloco.tecnica, "justificativa": bloco.justificativa, "fontes": bloco.fontes,
               "removidas": rel.removidas}
        if juiz is not None and rel.usou_llm:
            blocos = [b for b in proposta.blocos if b.material_id == m.id]
            trechos = buscar(j.consulta(m))
            contexto = contexto_do_juiz(j.montar_prompt(m, blocos, e.ctx, trechos, estado), trechos)
            afirmacoes = juiz.fidelidade(contexto, bloco.justificativa)
            reg["fidelidade"] = (sum(bool(a["sustentada"]) for a in afirmacoes) / len(afirmacoes)) if afirmacoes else 0.0
            reg["afirmacoes"] = afirmacoes
        saidas.append(reg)
        print(f"    {e.id}/{m.id}: {rel.segundos}s llm={rel.usou_llm} {bloco.tecnica!r}"
              + (f" fid={reg['fidelidade']:.2f}" if "fidelidade" in reg else ""))
    return saidas


# ---------------------------------------------------------------- saída
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
        atingiu = "–" if v is None else ("sim" if meta.ok(v) else "**não**")
        linhas.append(f"| {meta.nome} | {meta.alvo} | {_fmt(meta, v)} | {atingiu} |")
    return "\n".join(linhas)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--llm", help="modelo do Ollama para a justificativa (sem isto, só a parte determinística)")
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

    inicio = time.perf_counter()
    linhas, brutos, llm_regs, cache = [], [], [], {}
    for e in entradas():
        linha, bruto = avaliar(e)
        print(f"  {e.id}: rótulo={'ok' if linha['rotulo'] else 'X ' + linha['erros']}")
        if args.llm and not e.reajuste:
            bruto["justificativas"] = justificar(e, bruto["proposta"], args.llm, juiz, cache)
            llm_regs += bruto["justificativas"]
        linhas.append(linha)
        brutos.append({"cenario": e.id, "linha": linha, **bruto})

    agregado = mt.agregar(linhas, llm_regs)
    RELATORIOS.mkdir(parents=True, exist_ok=True)
    base = RELATORIOS / f"analysis_{nome}"
    _csv(base.with_suffix(".csv"), linhas)
    _csv(base.parent / f"{base.name}_llm.csv", llm_regs, ignorar=("afirmacoes",))
    base.with_suffix(".json").write_text(json.dumps(
        {"llm": args.llm, "juiz": modelo_juiz,
         "agregado": agregado, "cenarios": brutos}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    cmd = "python -m metricas.agentes.analysis.runner" + (f" --llm {args.llm}" if args.llm else "") + (" --juiz" if juiz else "")
    base.with_suffix(".md").write_text(
        f"# Métricas do Analysis: {nome}\n\nGerado por `{cmd}` (a partir de `pesquisa/`), "
        f"{len(linhas)} cenários de `metricas/agentes/analysis/cenarios.json`"
        + (f", {len(llm_regs)} justificativas do `{args.llm}`" if args.llm else "")
        + (f", juiz `{modelo_juiz}`" if juiz else "") + ".\n\n" + tabela_resumo(agregado) + "\n", encoding="utf-8")
    print(f"\n{tabela_resumo(agregado)}\n\n{len(linhas)} cenários em {time.perf_counter() - inicio:.0f}s -> {base}.*")


if __name__ == "__main__":
    main()
