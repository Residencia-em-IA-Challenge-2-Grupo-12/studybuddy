"""Harness de experimentação de modelos locais (Ollama) para os Guardrails do StudyBuddy.

Executa o prompt do Gatekeeper (ou o modo nativo de moderação para modelos como
Llama Guard 3) sobre `fixtures_guardrails.json`, medindo:
  - Recall de bloqueio por categoria (INJECTION, HATE_SPEECH, MEDICAL_ADVICE, OFF_TOPIC)
  - Acurácia de categoria exata por categoria
  - Falso positivo (% de pedidos válidos e limítrofes bloqueados indevidamente)
  - Latência por chamada (média e p95 em segundos, após warmup)
  - Memória (RAM/VRAM alocada pelo Ollama via GET /api/ps)
  - Taxa de JSON válido (para comparar `format=JSON Schema` vs sem `format`)
  - Metadados de hardware e versão do Ollama

Uso (a partir de `studybuddy/pesquisa/experimentos/modelos/` ou qualquer diretório):
    python3 harness_guardrails.py --suite completa
    python3 harness_guardrails.py --suite rapida
    python3 harness_guardrails.py --apenas qwen3_4b_padrao gemma3_4b
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API_DIR = HERE.parents[2] / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.modules.agentes.guardrails import (  # noqa: E402
    CATEGORIAS_BLOQUEIO,
    ESQUEMA_GUARDRAILS,
    PROMPT_GUARDRAILS,
    SAFE,
    DecisaoGuardrail,
    interpretar,
)

OLLAMA_BASE_URL = "http://localhost:11434"
FIXTURES_PATH = HERE / "fixtures_guardrails.json"
OUT_JSON = HERE / "resultados_guardrails.json"
OUT_CSV = HERE / "resultados_guardrails.csv"

# Mapeamento dos códigos MLCommons Hazard Taxonomy do Llama Guard 3
LLAMA_GUARD_MAP = {
    "S1": "HATE_SPEECH",     # Violent Crimes
    "S5": "HATE_SPEECH",     # Defamation
    "S6": "MEDICAL_ADVICE",  # Specialized Advice (inclui médico/financeiro/jurídico)
    "S10": "HATE_SPEECH",    # Hate
    "S11": "HATE_SPEECH",    # Suicide & Self-Harm
    "S14": "INJECTION",      # Code Interpreter Abuse
}


@dataclass(frozen=True)
class ExperimentoConfig:
    id: str
    modelo: str
    tipo: str  # "gatekeeper" ou "moderacao"
    descricao: str
    grupo: str  # "principal" ou "variacao"
    temperature: float = 0.0
    reasoning: bool | None = None  # True/False apenas para modelos com modo think (ex.: qwen3)
    usar_format: bool = True
    quantizacao: str = "q4_K_M"
    num_predict: int = 256
    timeout_s: float = 120.0


SUITE_PRINCIPAL: list[ExperimentoConfig] = [
    ExperimentoConfig(
        id="qwen3_4b",
        modelo="qwen3:4b",
        tipo="gatekeeper",
        descricao="Gatekeeper genérico (padrão: q4_K_M, temp=0, reasoning=off, JSON Schema)",
        grupo="principal",
        temperature=0.0,
        reasoning=False,
        usar_format=True,
        quantizacao="q4_K_M",
    ),
    ExperimentoConfig(
        id="gemma3_4b",
        modelo="gemma3:4b",
        tipo="gatekeeper",
        descricao="Gatekeeper genérico (q4_K_M, temp=0, JSON Schema)",
        grupo="principal",
        temperature=0.0,
        reasoning=None,
        usar_format=True,
        quantizacao="q4_K_M",
    ),
    ExperimentoConfig(
        id="phi4_mini",
        modelo="phi4-mini",
        tipo="gatekeeper",
        descricao="Gatekeeper genérico (q4_K_M, temp=0, JSON Schema)",
        grupo="principal",
        temperature=0.0,
        reasoning=None,
        usar_format=True,
        quantizacao="q4_K_M",
    ),
    ExperimentoConfig(
        id="llama_guard3_1b",
        modelo="llama-guard3:1b",
        tipo="moderacao",
        descricao="Classificador de moderação nativo (1B, taxonomia MLCommons)",
        grupo="principal",
        temperature=0.0,
        reasoning=None,
        usar_format=False,
        quantizacao="q4_K_M",
        num_predict=64,
    ),
    ExperimentoConfig(
        id="llama_guard3_8b",
        modelo="llama-guard3:8b",
        tipo="moderacao",
        descricao="Classificador de moderação nativo (8B, taxonomia MLCommons)",
        grupo="principal",
        temperature=0.0,
        reasoning=None,
        usar_format=False,
        quantizacao="q4_K_M",
        num_predict=64,
    ),
]

SUITE_VARIACOES: list[ExperimentoConfig] = [
    ExperimentoConfig(
        id="qwen3_4b_temp03",
        modelo="qwen3:4b",
        tipo="gatekeeper",
        descricao="Variação temperature=0.3 (vs 0.0)",
        grupo="variacao",
        temperature=0.3,
        reasoning=False,
        usar_format=True,
        quantizacao="q4_K_M",
    ),
    ExperimentoConfig(
        id="qwen3_4b_reasoning_on",
        modelo="qwen3:4b",
        tipo="gatekeeper",
        descricao="Variação reasoning=True (modo <think> ligado)",
        grupo="variacao",
        temperature=0.0,
        reasoning=True,
        usar_format=True,
        quantizacao="q4_K_M",
        num_predict=1024,
        timeout_s=180.0,
    ),
    ExperimentoConfig(
        id="qwen3_4b_sem_format",
        modelo="qwen3:4b",
        tipo="gatekeeper",
        descricao="Variação sem structured output (format=None)",
        grupo="variacao",
        temperature=0.0,
        reasoning=False,
        usar_format=False,
        quantizacao="q4_K_M",
    ),
    ExperimentoConfig(
        id="qwen3_4b_q8_0",
        modelo="qwen3:4b-q8_0",
        tipo="gatekeeper",
        descricao="Variação quantização q8_0 (vs q4_K_M)",
        grupo="variacao",
        temperature=0.0,
        reasoning=False,
        usar_format=True,
        quantizacao="q8_0",
    ),
]


def _http_json(method: str, path: str, payload: dict | None = None, timeout_s: float = 120.0) -> dict:
    url = f"{OLLAMA_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def listar_modelos_locais() -> dict[str, dict]:
    resp = _http_json("GET", "/api/tags", timeout_s=15.0)
    out = {}
    for m in resp.get("models", []):
        nome = m["name"]
        out[nome] = m
        if nome.endswith(":latest"):
            out[nome.removesuffix(":latest")] = m
    return out


def descarregar_modelo(modelo: str) -> None:
    try:
        _http_json("POST", "/api/generate", {"model": modelo, "keep_alive": 0}, timeout_s=30.0)
    except Exception:
        pass


def ler_memoria_ollama(modelo: str) -> dict:
    """Consulta GET /api/ps para obter RAM/VRAM alocada pelo modelo ativo."""
    try:
        ps = _http_json("GET", "/api/ps", timeout_s=10.0)
        for item in ps.get("models", []):
            nome = item.get("name", "")
            if nome == modelo or nome == f"{modelo}:latest" or nome.split(":")[0] == modelo.split(":")[0]:
                size_bytes = item.get("size", 0)
                vram_bytes = item.get("size_vram", 0)
                return {
                    "size_bytes": size_bytes,
                    "size_vram_bytes": vram_bytes,
                    "size_gb": round(size_bytes / (1024**3), 2),
                    "vram_gb": round(vram_bytes / (1024**3), 2),
                    "quantization_level": item.get("details", {}).get("quantization_level", ""),
                    "parameter_size": item.get("details", {}).get("parameter_size", ""),
                }
    except Exception:
        pass
    return {"size_bytes": 0, "size_vram_bytes": 0, "size_gb": 0.0, "vram_gb": 0.0,
            "quantization_level": "", "parameter_size": ""}


def coletar_hardware() -> dict:
    def _cmd(args: list[str]) -> str:
        try:
            return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return "desconhecido"

    mem_bytes_str = _cmd(["sysctl", "-n", "hw.memsize"])
    mem_gb = round(int(mem_bytes_str) / (1024**3), 1) if mem_bytes_str.isdigit() else 0.0
    ollama_ver = _cmd(["ollama", "--version"])
    return {
        "os": f"{platform.system()} {platform.mac_ver()[0] or platform.release()}",
        "arquitetura": platform.machine(),
        "cpu_gpu": _cmd(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "nucleos": _cmd(["sysctl", "-n", "hw.ncpu"]),
        "ram_total_gb": mem_gb,
        "python": platform.python_version(),
        "ollama": ollama_ver,
        "data_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def interpretar_moderacao(bruto: str) -> DecisaoGuardrail:
    """Interpreta saída nativa de modelos de moderação (ex.: Llama Guard 3: 'safe' ou 'unsafe\\nS10')."""
    linhas = [ln.strip() for ln in bruto.strip().splitlines() if ln.strip()]
    if not linhas:
        return DecisaoGuardrail(permitido=False, categoria="OFF_TOPIC", motivo="saida_vazia", json_valido=False)
    primeira = linhas[0].lower()
    if primeira.startswith("safe"):
        return DecisaoGuardrail(permitido=True, categoria=SAFE, motivo="safe", json_valido=True)
    if primeira.startswith("unsafe"):
        codigos = []
        for ln in linhas[1:]:
            for tok in ln.replace(",", " ").split():
                if tok.upper().startswith("S") and tok[1:].isdigit():
                    codigos.append(tok.upper())
        categoria = "UNSAFE_OUTRO"
        for cod in codigos:
            if cod in LLAMA_GUARD_MAP:
                categoria = LLAMA_GUARD_MAP[cod]
                break
        motivo = f"unsafe ({', '.join(codigos)})" if codigos else "unsafe"
        return DecisaoGuardrail(permitido=False, categoria=categoria, motivo=motivo, json_valido=True)
    return DecisaoGuardrail(permitido=False, categoria="UNSAFE_OUTRO", motivo=f"inesperado: {bruto[:80]}", json_valido=False)


def chamar_modelo(cfg: ExperimentoConfig, mensagem: str) -> tuple[DecisaoGuardrail, str, float]:
    if cfg.tipo == "gatekeeper":
        prompt = PROMPT_GUARDRAILS.format(mensagem=mensagem)
        payload: dict = {
            "model": cfg.modelo,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": cfg.temperature, "num_predict": cfg.num_predict},
        }
        if cfg.reasoning is not None:
            payload["think"] = cfg.reasoning
        if cfg.usar_format:
            payload["format"] = ESQUEMA_GUARDRAILS
    else:
        payload = {
            "model": cfg.modelo,
            "messages": [{"role": "user", "content": mensagem}],
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": cfg.temperature, "num_predict": cfg.num_predict},
        }

    t0 = time.perf_counter()
    resp = _http_json("POST", "/api/chat", payload, timeout_s=cfg.timeout_s)
    elapsed = time.perf_counter() - t0
    bruto = resp.get("message", {}).get("content", "")
    decisao = interpretar(bruto) if cfg.tipo == "gatekeeper" else interpretar_moderacao(bruto)
    return decisao, bruto, elapsed


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    idx = (len(ordenados) - 1) * p
    baixo = math.floor(idx)
    alto = math.ceil(idx)
    if baixo == alto:
        return ordenados[baixo]
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (idx - baixo)


def calcular_metricas(casos_res: list[dict], latencias: list[float], memoria: dict, cold_start_s: float) -> dict:
    recall_bloqueio: dict[str, float] = {}
    recall_exato: dict[str, float] = {}
    for cat in CATEGORIAS_BLOQUEIO:
        subset = [c for c in casos_res if c["esperado_categoria"] == cat]
        n = len(subset)
        recall_bloqueio[cat] = round(sum(1 for c in subset if c["pred_bloqueado"]) / n, 4) if n else 0.0
        recall_exato[cat] = round(sum(1 for c in subset if c["pred_categoria"] == cat) / n, 4) if n else 0.0

    positivos = [c for c in casos_res if c["esperado_bloqueado"]]
    recall_bloqueio_geral = round(sum(1 for c in positivos if c["pred_bloqueado"]) / len(positivos), 4)
    recall_exato_geral = round(sum(1 for c in positivos if c["pred_categoria"] == c["esperado_categoria"]) / len(positivos), 4)

    seguros = [c for c in casos_res if not c["esperado_bloqueado"]]
    validos = [c for c in seguros if c["subcategoria"] == "valido"]
    limitrofes = [c for c in seguros if c["subcategoria"] == "limitrofe"]

    fp_total = round(sum(1 for c in seguros if c["pred_bloqueado"]) / len(seguros), 4)
    fp_validos = round(sum(1 for c in validos if c["pred_bloqueado"]) / len(validos), 4)
    fp_limitrofes = round(sum(1 for c in limitrofes if c["pred_bloqueado"]) / len(limitrofes), 4)

    # F1 binário (bloqueio correto vs falso positivo)
    tp = sum(1 for c in positivos if c["pred_bloqueado"])
    fp = sum(1 for c in seguros if c["pred_bloqueado"])
    fn = len(positivos) - tp
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = round(2 * prec * rec / (prec + rec), 4) if (prec + rec) else 0.0

    json_ok = round(sum(1 for c in casos_res if c["json_valido"]) / len(casos_res), 4)

    return {
        "recall_bloqueio": recall_bloqueio,
        "recall_bloqueio_geral": recall_bloqueio_geral,
        "recall_exato": recall_exato,
        "recall_exato_geral": recall_exato_geral,
        "fp_total": fp_total,
        "fp_validos": fp_validos,
        "fp_limitrofes": fp_limitrofes,
        "f1_bloqueio": f1,
        "json_valido_taxa": json_ok,
        "latencia_media_s": round(sum(latencias) / len(latencias), 3),
        "latencia_p95_s": round(percentil(latencias, 0.95), 3),
        "cold_start_s": round(cold_start_s, 3),
        "memoria": memoria,
    }


def rodar_experimento(cfg: ExperimentoConfig, fixtures: list[dict]) -> dict:
    print(f"\n=== [{cfg.id}] modelo={cfg.modelo} | tipo={cfg.tipo} | temp={cfg.temperature} | "
          f"reasoning={cfg.reasoning} | format={cfg.usar_format} ===", flush=True)

    # Warmup para separar cold-start e carregar pesos na RAM/VRAM antes de ler /api/ps
    _, _, cold_start_s = chamar_modelo(cfg, "Como organizar minha agenda de estudos da semana?")
    memoria = ler_memoria_ollama(cfg.modelo)
    print(f"  warmup={cold_start_s:.2f}s | mem={memoria['size_gb']} GB (VRAM={memoria['vram_gb']} GB, "
          f"quant={memoria['quantization_level'] or cfg.quantizacao})", flush=True)

    casos_res = []
    latencias = []
    for i, fx in enumerate(fixtures, start=1):
        try:
            dec, bruto, elapsed = chamar_modelo(cfg, fx["mensagem"])
            erro = ""
        except Exception as exc:
            dec = DecisaoGuardrail(permitido=False, categoria="OFF_TOPIC", motivo=f"erro: {exc}", json_valido=False)
            bruto = ""
            elapsed = cfg.timeout_s
            erro = str(exc)

        latencias.append(elapsed)
        pred_bloqueado = not dec.permitido
        acertou_bloqueio = pred_bloqueado == fx["esperado_bloqueado"]
        casos_res.append({
            "id": fx["id"],
            "esperado_categoria": fx["categoria"],
            "subcategoria": fx["subcategoria"],
            "esperado_bloqueado": fx["esperado_bloqueado"],
            "pred_bloqueado": pred_bloqueado,
            "pred_categoria": dec.categoria,
            "motivo": dec.motivo,
            "json_valido": dec.json_valido,
            "acertou_bloqueio": acertou_bloqueio,
            "latencia_s": round(elapsed, 3),
            "bruto": bruto[:300],
            "erro": erro,
        })
        if i % 12 == 0 or i == len(fixtures):
            print(f"  progresso: {i}/{len(fixtures)} (última: {elapsed:.2f}s)", flush=True)

    metricas = calcular_metricas(casos_res, latencias, memoria, cold_start_s)
    print(
        f"  RESUMO -> Recall Bloq: INJ={metricas['recall_bloqueio']['INJECTION']*100:.0f}% "
        f"HATE={metricas['recall_bloqueio']['HATE_SPEECH']*100:.0f}% "
        f"MED={metricas['recall_bloqueio']['MEDICAL_ADVICE']*100:.0f}% "
        f"OFF={metricas['recall_bloqueio']['OFF_TOPIC']*100:.0f}% | "
        f"FP={metricas['fp_total']*100:.1f}% (val={metricas['fp_validos']*100:.0f}%, lim={metricas['fp_limitrofes']*100:.0f}%) | "
        f"Lat={metricas['latencia_media_s']:.2f}s (p95={metricas['latencia_p95_s']:.2f}s) | "
        f"JSON={metricas['json_valido_taxa']*100:.0f}%",
        flush=True,
    )

    descarregar_modelo(cfg.modelo)
    return {
        "config": asdict(cfg),
        "metricas": metricas,
        "casos": casos_res,
    }


def salvar_csv(resultados: list[dict], path: Path) -> None:
    campos = [
        "id", "grupo", "modelo", "tipo", "quantizacao", "temperature", "reasoning", "usar_format",
        "recall_INJECTION", "recall_HATE_SPEECH", "recall_MEDICAL_ADVICE", "recall_OFF_TOPIC",
        "recall_bloqueio_geral", "recall_exato_geral",
        "fp_total", "fp_validos", "fp_limitrofes", "f1_bloqueio", "json_valido_taxa",
        "latencia_media_s", "latencia_p95_s", "cold_start_s", "memoria_gb", "vram_gb",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for r in resultados:
            c = r["config"]
            m = r["metricas"]
            w.writerow({
                "id": c["id"],
                "grupo": c["grupo"],
                "modelo": c["modelo"],
                "tipo": c["tipo"],
                "quantizacao": m["memoria"].get("quantization_level") or c["quantizacao"],
                "temperature": c["temperature"],
                "reasoning": c["reasoning"],
                "usar_format": c["usar_format"],
                "recall_INJECTION": m["recall_bloqueio"]["INJECTION"],
                "recall_HATE_SPEECH": m["recall_bloqueio"]["HATE_SPEECH"],
                "recall_MEDICAL_ADVICE": m["recall_bloqueio"]["MEDICAL_ADVICE"],
                "recall_OFF_TOPIC": m["recall_bloqueio"]["OFF_TOPIC"],
                "recall_bloqueio_geral": m["recall_bloqueio_geral"],
                "recall_exato_geral": m["recall_exato_geral"],
                "fp_total": m["fp_total"],
                "fp_validos": m["fp_validos"],
                "fp_limitrofes": m["fp_limitrofes"],
                "f1_bloqueio": m["f1_bloqueio"],
                "json_valido_taxa": m["json_valido_taxa"],
                "latencia_media_s": m["latencia_media_s"],
                "latencia_p95_s": m["latencia_p95_s"],
                "cold_start_s": m["cold_start_s"],
                "memoria_gb": m["memoria"]["size_gb"],
                "vram_gb": m["memoria"]["vram_gb"],
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="Harness de benchmark de modelos locais nos Guardrails.")
    parser.add_argument("--suite", choices=["completa", "principal", "variacoes", "rapida"], default="completa")
    parser.add_argument("--apenas", nargs="*", help="Lista de IDs de experimentos para rodar.")
    parser.add_argument("--mesclar", action="store_true", help="Mescla resultados novos com resultados_guardrails.json existente.")
    args = parser.parse_args()

    fixtures = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    hardware = coletar_hardware()
    modelos_disponiveis = listar_modelos_locais()

    todas = SUITE_PRINCIPAL + SUITE_VARIACOES
    if args.apenas:
        selecionados = [c for c in todas if c.id in set(args.apenas)]
    elif args.suite == "principal":
        selecionados = SUITE_PRINCIPAL
    elif args.suite == "variacoes":
        selecionados = SUITE_VARIACOES
    elif args.suite == "rapida":
        selecionados = [c for c in SUITE_PRINCIPAL if c.id in {"qwen3_4b", "gemma3_4b", "llama_guard3_1b"}]
    else:
        selecionados = todas

    existentes_por_id: dict[str, dict] = {}
    if args.mesclar and OUT_JSON.exists():
        anterior = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        for r in anterior.get("experimentos", []):
            existentes_por_id[r["config"]["id"]] = r

    resultados: list[dict] = []
    pulados: list[str] = []
    for cfg in selecionados:
        if cfg.modelo not in modelos_disponiveis:
            print(f"[PULADO] {cfg.id}: modelo '{cfg.modelo}' não está instalado no Ollama.", flush=True)
            pulados.append(cfg.modelo)
            continue
        res = rodar_experimento(cfg, fixtures)
        existentes_por_id[cfg.id] = res
        resultados.append(res)

    if args.mesclar:
        ordem = [c.id for c in todas]
        finais = [existentes_por_id[k] for k in ordem if k in existentes_por_id]
    else:
        finais = resultados

    saida = {
        "hardware": hardware,
        "total_fixtures": len(fixtures),
        "modelos_pulados": pulados,
        "experimentos": finais,
    }
    OUT_JSON.write_text(json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")
    salvar_csv(finais, OUT_CSV)
    print(f"\nSalvo em:\n- {OUT_JSON}\n- {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
