"""Runner de métricas do Validation Agent e Guardrails (saída em CSV, MD e JSON).

Uso (a partir de pesquisa/):
    python -m metricas.agentes.validation.runner                     # Validation determinístico (sem Ollama, < 1 s)
    python -m metricas.agentes.validation.runner --guardrails        # + 64 cenários de Guardrails no Ollama
    python -m metricas.agentes.validation.runner --guardrails --barreira-hate-speech
    python -m metricas.agentes.validation.runner --guardrails-simulado  # exercita todo o cálculo sem Ollama

Não depende de nenhum outro agente (Analysis, Research, Communication ou Maestro).
"""

import argparse
import csv
import json
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from . import metricas as mt
from .cenarios import (
    EntradaGuardrail,
    EntradaValidation,
    carregar_cenarios_guardrails,
    carregar_cenarios_validation,
)

# cenarios.py já garante `api/` no sys.path
from app.modules.agentes.contratos import Veredito  # noqa: E402
from app.modules.agentes.guardrails import (  # noqa: E402
    CATEGORIA_HATE_SPEECH,
    CATEGORIA_OK,
    hard_stop,
    verificar_entrada,
    verificar_hate_speech,
)
from app.modules.agentes.validation import validar  # noqa: E402
from app.modules.rag import llm as rag_llm  # noqa: E402

RELATORIOS_DIR = Path(__file__).resolve().parents[2] / "relatorios"

_FABRICAS_LLM = ("gerador", "triagem", "guardrails", "guardrails_fallback", "moderacao", "guardrails_veredito")


@contextmanager
def _monitorar_zero_llm():
    """Substitui todas as fábricas de LLM durante a execução do Validation para comprovar 0 chamadas."""
    chamadas: list[str] = []
    originais: dict[str, object] = {}

    def _fazer_bloqueio(nome: str):
        def _bloqueado(*_args, **_kwargs):
            chamadas.append(nome)
            raise RuntimeError(f"Validation determinístico tentou chamar LLM ({nome})")

        return _bloqueado

    for nome in _FABRICAS_LLM:
        if hasattr(rag_llm, nome):
            originais[nome] = getattr(rag_llm, nome)
            setattr(rag_llm, nome, _fazer_bloqueio(nome))
    try:
        yield chamadas
    finally:
        for nome, fn in originais.items():
            setattr(rag_llm, nome, fn)


def executar_validation(entradas: list[EntradaValidation]) -> tuple[list[dict], dict]:
    """Roda todos os cenários determinísticos do Validation com garantia de 0 chamadas a LLM."""
    linhas: list[dict] = []
    for e in entradas:
        with _monitorar_zero_llm() as chamadas_llm:
            inicio = time.perf_counter()
            res = validar(e.proposta, e.contexto, provedor_agenda=e.provedor_agenda)
            latencia_ms = (time.perf_counter() - inicio) * 1000.0

        avaliacao = mt.avaliar_cenario_validation(
            res,
            e.status_esperado,
            e.violacoes_esperadas,
            chamadas_llm=len(chamadas_llm),
            latencia_ms=latencia_ms,
        )
        linhas.append(
            {
                "id": e.id,
                "grupo": e.grupo,
                "descricao": e.descricao,
                **avaliacao,
                "violacoes_obtidas": [v.model_dump(mode="json") for v in res.violacoes],
            }
        )
    return linhas, mt.agregar_validation(linhas)


def executar_guardrails(
    entradas: list[EntradaGuardrail],
    *,
    classificador_fn: Callable[[EntradaGuardrail], Veredito] | None = None,
    barreira: str = "gatekeeper",
    mostrar_progresso: bool = False,
) -> tuple[list[dict], dict]:
    """Roda o conjunto de avaliação dos Guardrails e agrega todas as métricas."""
    if classificador_fn is None:
        if barreira == "hate_speech":
            classificador_fn = lambda e: verificar_hate_speech(e.mensagem)  # noqa: E731
        else:
            classificador_fn = lambda e: verificar_entrada(e.mensagem)  # noqa: E731

    linhas: list[dict] = []
    total = len(entradas)
    for idx, e in enumerate(entradas, start=1):
        esperado_cat = e.categoria
        esperado_bloq = e.esperado_bloqueado
        if barreira == "hate_speech":
            esperado_bloq = e.categoria == CATEGORIA_HATE_SPEECH
            esperado_cat = CATEGORIA_HATE_SPEECH if esperado_bloq else CATEGORIA_OK

        inicio = time.perf_counter()
        veredito = classificador_fn(e)
        latencia_ms = (time.perf_counter() - inicio) * 1000.0

        avaliacao = mt.avaliar_cenario_guardrail(
            categoria_esperada=esperado_cat,
            tipo=e.tipo,
            esperado_bloqueado=esperado_bloq,
            veredito=veredito,
            latencia_ms=latencia_ms,
            barreira=barreira,
        )
        linhas.append({"id": e.id, "subcategoria": e.subcategoria, **avaliacao})
        if mostrar_progresso:
            marca = "OK" if avaliacao["acertou_bloqueio"] else "ERRO"
            print(
                f"  [{idx:02d}/{total:02d}] {e.id:<12} esperado={esperado_cat:<16} "
                f"obtido={veredito.categoria:<16} {marca} ({latencia_ms / 1000:.2f}s)",
                flush=True,
            )

    return linhas, mt.agregar_guardrails(linhas)


def _fmt(meta: mt.Meta, valor) -> str:
    if valor is None:
        return "–"
    if meta.fmt == "pct":
        return f"{valor:.1%}"
    if meta.fmt == "ms":
        return f"{valor:.2f} ms"
    return str(valor)


def tabela_resumo(metas: tuple[mt.Meta, ...], agregado: dict) -> str:
    linhas = ["| Métrica | Meta | Resultado | Atingiu? |", "| :-- | :-- | --: | :-: |"]
    for meta in metas:
        v = agregado.get(meta.chave)
        atingiu = "–" if v is None or meta.alvo == "–" else ("sim" if meta.ok(v) else "**não**")
        linhas.append(f"| {meta.nome} | {meta.alvo} | {_fmt(meta, v)} | {atingiu} |")
    return "\n".join(linhas)


def _salvar_csv(caminho: Path, linhas: list[dict], ignorar: tuple[str, ...] = ()) -> None:
    if not linhas:
        return
    campos = list(dict.fromkeys(k for row in linhas for k in row if k not in ignorar))
    with caminho.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def _linhas_csv_validation(linhas: list[dict]) -> list[dict]:
    saida = []
    for r in linhas:
        plano = {k: v for k, v in r.items() if k not in ("contagens_por_regra", "violacoes_obtidas")}
        for regra in mt.REGRAS_VALIDATION:
            c = r["contagens_por_regra"][regra]
            plano[f"{regra}_tp"] = c["tp"]
            plano[f"{regra}_fp"] = c["fp"]
            plano[f"{regra}_fn"] = c["fn"]
        saida.append(plano)
    return saida


def salvar_relatorios(
    *,
    nome: str,
    cmd: str,
    val_linhas: list[dict],
    val_agregado: dict,
    guard_linhas: list[dict] | None = None,
    guard_agregado: dict | None = None,
    pasta: Path = RELATORIOS_DIR,
) -> dict[str, Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos: dict[str, Path] = {}

    csv_val = pasta / f"validation_{nome}.csv"
    _salvar_csv(csv_val, _linhas_csv_validation(val_linhas))
    caminhos["csv_validation"] = csv_val

    if guard_linhas:
        csv_guard = pasta / f"validation_{nome}_guardrails.csv"
        _salvar_csv(csv_guard, guard_linhas)
        caminhos["csv_guardrails"] = csv_guard

    json_path = pasta / f"validation_{nome}.json"
    json_path.write_text(
        json.dumps(
            {
                "comando": cmd,
                "validation": {"agregado": val_agregado, "cenarios": val_linhas},
                "guardrails": (
                    {"agregado": guard_agregado, "cenarios": guard_linhas} if guard_agregado is not None else None
                ),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    caminhos["json"] = json_path

    partes_md = [
        f"# Métricas do Validation e Guardrails: `{nome}`",
        "",
        f"Gerado por `{cmd}` (a partir de `pesquisa/`), sobre `cenarios_validation.json` ({len(val_linhas)} cenários)"
        + (f" e `cenarios_guardrails.json` ({len(guard_linhas)} cenários)." if guard_linhas else "."),
        "",
        "## 1. Validation Determinístico (sem LLM)",
        "",
        tabela_resumo(mt.METAS_VALIDATION, val_agregado),
    ]

    if guard_agregado:
        partes_md.extend(
            [
                "",
                "## 2. Guardrails (Barreiras 4.4 a 4.7)",
                "",
                tabela_resumo(mt.METAS_GUARDRAILS, guard_agregado),
                "",
                "### Latência por categoria (ms)",
                "",
                "| Categoria | n | Média (ms) | p50 (ms) | p95 (ms) |",
                "| :-- | --: | --: | --: | --: |",
            ]
        )
        for cat, stats in guard_agregado.get("latencia_por_categoria_ms", {}).items():
            partes_md.append(
                f"| `{cat}` | {stats['n']} | {stats['media_ms']:.2f} | {stats['p50_ms']:.2f} | {stats['p95_ms']:.2f} |"
            )

    md_path = pasta / f"validation_{nome}.md"
    md_path.write_text("\n".join(partes_md) + "\n", encoding="utf-8")
    caminhos["md"] = md_path
    return caminhos


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", help="sufixo dos relatórios (padrão: 'deterministico' ou 'completo')")
    ap.add_argument("--guardrails", action="store_true", help="avalia também os 64 cenários de Guardrails no Ollama")
    ap.add_argument(
        "--barreira-hate-speech",
        action="store_true",
        help="com --guardrails: avalia a barreira dedicada 4.5 (HATE_SPEECH) em vez do gatekeeper completo",
    )
    ap.add_argument(
        "--guardrails-simulado",
        action="store_true",
        help="exercita também as métricas de Guardrails com classificador stub (sem Ollama)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="timeout (s) por chamada ao Ollama no runner de Guardrails (padrão: 120s para suportar CPU/cold-start)",
    )
    args = ap.parse_args()

    nome = args.nome or (
        "completo" if args.guardrails else ("simulado" if args.guardrails_simulado else "deterministico")
    )
    entradas_val = carregar_cenarios_validation()
    val_linhas, val_agregado = executar_validation(entradas_val)

    guard_linhas, guard_agregado = None, None
    if args.guardrails:
        from app.core.config import settings

        settings.ollama_timeout_guardrails = args.timeout
        rag_llm.guardrails_veredito.cache_clear()
        rag_llm.moderacao.cache_clear()

        entradas_g = carregar_cenarios_guardrails()
        barreira = "hate_speech" if args.barreira_hate_speech else "gatekeeper"
        try:
            print(
                f"\nAquecendo modelo '{settings.ollama_guardrails_model}' no Ollama "
                f"(timeout={args.timeout:.0f}s)...",
                flush=True,
            )
            warmup_fn = verificar_hate_speech if barreira == "hate_speech" else verificar_entrada
            warmup_fn("Como organizar minha agenda semanal de estudos?")
            print(f"Modelo carregado. Avaliando {len(entradas_g)} cenários de Guardrails...\n", flush=True)
            guard_linhas, guard_agregado = executar_guardrails(
                entradas_g, barreira=barreira, mostrar_progresso=True
            )
        except Exception as exc:
            nome_erro = type(exc).__name__
            if nome_erro in ("ConnectError", "ConnectionError", "ResponseError", "ReadTimeout"):
                raise SystemExit(
                    f"Erro ao chamar o Ollama em {settings.ollama_base_url} ({nome_erro}: {exc}).\n"
                    "Para rodar com --guardrails, abra o Ollama (ou execute 'ollama serve') e garanta "
                    f"que o modelo '{settings.ollama_guardrails_model}' está baixado (ou aumente --timeout).\n"
                    "Sem Ollama, rode sem --guardrails (só Validation determinístico) ou com --guardrails-simulado."
                ) from None
            raise
    elif args.guardrails_simulado:
        entradas_g = carregar_cenarios_guardrails()
        guard_linhas, guard_agregado = executar_guardrails(
            entradas_g,
            classificador_fn=lambda e: hard_stop(e.categoria) if e.esperado_bloqueado else hard_stop(CATEGORIA_OK),
            barreira="simulado",
        )

    cmd = "python -m metricas.agentes.validation.runner"
    if args.guardrails:
        cmd += " --guardrails"
    if args.barreira_hate_speech:
        cmd += " --barreira-hate-speech"
    if args.guardrails_simulado:
        cmd += " --guardrails-simulado"

    caminhos = salvar_relatorios(
        nome=nome,
        cmd=cmd,
        val_linhas=val_linhas,
        val_agregado=val_agregado,
        guard_linhas=guard_linhas,
        guard_agregado=guard_agregado,
    )

    print("\n=== VALIDATION DETERMINÍSTICO ===")
    print(tabela_resumo(mt.METAS_VALIDATION, val_agregado))
    if guard_agregado:
        print("\n=== GUARDRAILS ===")
        print(tabela_resumo(mt.METAS_GUARDRAILS, guard_agregado))
    print("\nRelatórios gravados:")
    for chave, caminho in caminhos.items():
        print(f"  {chave}: {caminho}")


if __name__ == "__main__":
    main()
