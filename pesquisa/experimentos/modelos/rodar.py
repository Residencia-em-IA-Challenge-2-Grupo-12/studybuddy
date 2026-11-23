"""Harness de experimentação com modelos locais do Ollama ([0.3]). Serve a qualquer agente.

Uso (a partir de pesquisa/):
    python -m experimentos.modelos.rodar analysis                     # roda as configurações padrão do agente
    python -m experimentos.modelos.rodar analysis --modelos qwen3:8b gemma3:12b --limite 3
    python -m experimentos.modelos.rodar analysis --modelos qwen3:8b --reasoning --rotulo qwen3_8b_think
    python -m experimentos.modelos.rodar analysis --juiz               # fidelidade (LLM-juiz) do que já rodou
    python -m experimentos.modelos.rodar analysis --resumo             # só refaz o CSV e o Markdown

Fase 1 (gerar): para cada configuração × caso, salva a saída bruta, o tempo, tokens/s (metadados do
Ollama), se o JSON validou no contrato e o erro. Um JSONL por configuração em resultados/<agente>/.
A primeira chamada de cada modelo é de aquecimento (carrega o modelo) e não entra na latência.
Fase 2 (--juiz): fidelidade de cada resposta ao contexto, com o juiz de metricas/geracao/juiz.py.
O juiz é sempre diferente do modelo julgado (padrão gemma3:12b; para o gemma3, OLLAMA_JUIZ_ALT=qwen3:8b).
Fase 3 (resumo): <agente>.csv e <agente>.md em experimentos/modelos/, uma linha por configuração.

Plugar um agente novo: criar agentes/<nome>.py com uma classe que segue o Protocol `Agente` abaixo e
registrá-la em AGENTES.
"""

import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

AQUI = Path(__file__).resolve().parent
API_DIR = AQUI.parents[2] / "api"
RESULTADOS = AQUI / "resultados"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


# ---------------------------------------------------------------- o que cada agente fornece
@dataclass
class Caso:
    id: str
    prompt: str
    contexto: str = ""                      # o que o juiz usa para conferir a fidelidade
    dados: dict = field(default_factory=dict)  # o que o avaliador do agente precisa


@dataclass
class Config:
    modelo: str
    temperature: float = 0.0
    reasoning: bool = False
    formato: bool = True  # True: JSON Schema do contrato como `format`; False: JSON só pedido no prompt
    rotulo: str = ""

    def __post_init__(self):
        if not self.rotulo:
            r = self.modelo.replace(":", "_").replace("/", "_")
            r += f"_t{self.temperature:g}" if self.temperature else ""
            r += "_think" if self.reasoning else ""
            r += "" if self.formato else "_sem_format"
            self.rotulo = r


class Agente(Protocol):
    nome: str
    contrato: Any                       # modelo Pydantic que a saída precisa validar
    configs_padrao: list[Config]

    def casos(self) -> list[Caso]: ...
    def avaliar(self, caso: Caso, objeto: Any | None) -> dict: ...   # métricas do agente (hook)
    def resposta(self, objeto: Any) -> str: ...                     # texto que o juiz confere
    def metricas(self) -> list[str]: ...                            # colunas do resumo, na ordem


def _agentes() -> dict[str, Callable[[], Agente]]:
    from .agentes.analysis import AgenteAnalysisExperimento

    return {"analysis": AgenteAnalysisExperimento}


# ---------------------------------------------------------------- Ollama
def ollama_url() -> str:
    from app.core.config import settings

    return os.getenv("OLLAMA_BASE_URL", settings.ollama_base_url).rstrip("/")


def _get(caminho: str) -> dict:
    with urllib.request.urlopen(f"{ollama_url()}{caminho}", timeout=10) as r:
        return json.loads(r.read())


def modelos_disponiveis() -> set[str]:
    nomes = {m["name"] for m in _get("/api/tags").get("models", [])}
    return nomes | {n.removesuffix(":latest") for n in nomes}


def garantir_modelos(modelos: list[str], baixar: bool) -> None:
    faltam = [m for m in dict.fromkeys(modelos) if m not in modelos_disponiveis()]
    if faltam and not baixar:
        raise SystemExit(f"Modelos ausentes no Ollama: {faltam}. Rode `ollama pull <modelo>` ou use --pull.")
    for m in faltam:
        print(f"ollama pull {m} ...")
        subprocess.run(["ollama", "pull", m], check=True)


def memoria_gb(modelo: str) -> tuple[float | None, float | None]:
    """(RAM total, parte em VRAM) do modelo carregado, pelo /api/ps. Em Apple Silicon a memória é unificada."""
    try:
        for m in _get("/api/ps").get("models", []):
            if m["name"] in (modelo, f"{modelo}:latest"):
                return round(m["size"] / 1e9, 2), round(m.get("size_vram", 0) / 1e9, 2)
    except OSError:
        pass
    return None, None


def chat_ollama(cfg: Config, esquema: dict):
    from langchain_ollama import ChatOllama

    from app.core.config import settings

    return ChatOllama(model=cfg.modelo, temperature=cfg.temperature, reasoning=cfg.reasoning,
                      format=esquema if cfg.formato else None, base_url=ollama_url(),
                      client_kwargs={"timeout": settings.ollama_timeout_llm})


def hardware() -> str:
    try:
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 2**30
        return f"{cpu}, {ram:.0f} GB de memória unificada, {platform.system()} {platform.release()}"
    except (OSError, ValueError):
        return f"{platform.processor() or platform.machine()}, {platform.system()} {platform.release()}"


# ---------------------------------------------------------------- fase 1: gerar
def _arquivo(agente: Agente, cfg: Config) -> Path:
    return RESULTADOS / agente.nome / f"{cfg.rotulo}.jsonl"


def rodar_config(agente: Agente, cfg: Config, casos: list[Caso], fabrica_chat=chat_ollama) -> list[dict]:
    chat = fabrica_chat(cfg, agente.contrato.model_json_schema())
    try:
        versao = _get("/api/version").get("version", "")
    except OSError:
        versao = ""  # sem Ollama (testes com chat falso)
    try:
        chat.invoke("Responda apenas: ok")  # aquecimento: carregar o modelo não conta na latência
    except Exception as exc:  # noqa: BLE001 - modelo sem suporte a reasoning, por exemplo: registra e segue
        print(f"  [{cfg.rotulo}] aquecimento falhou: {exc}")
    registros = []
    for caso in casos:
        reg = {"rotulo": cfg.rotulo, "config": asdict(cfg), "caso": caso.id, "ollama": versao}
        inicio = time.perf_counter()
        try:
            r = chat.invoke(caso.prompt)
            reg["segundos"] = round(time.perf_counter() - inicio, 2)
            reg["bruto"] = r.content
            meta = getattr(r, "response_metadata", {}) or {}
            if meta.get("eval_count") and meta.get("eval_duration"):
                reg["tokens_s"] = round(meta["eval_count"] / (meta["eval_duration"] / 1e9), 1)
        except Exception as exc:  # noqa: BLE001
            reg.update(segundos=round(time.perf_counter() - inicio, 2), bruto="", erro=f"{type(exc).__name__}: {exc}")
        objeto = None
        if reg.get("bruto"):
            try:
                objeto = agente.contrato.model_validate_json(reg["bruto"])
            except Exception as exc:  # noqa: BLE001
                reg["erro"] = f"contrato: {str(exc).splitlines()[0]}"
        reg["json_valido"] = objeto is not None
        reg["metricas"] = agente.avaliar(caso, objeto)
        reg["resposta"] = agente.resposta(objeto) if objeto else ""
        registros.append(reg)
        print(f"  [{cfg.rotulo}] {caso.id}: {reg['segundos']}s json={'ok' if objeto else 'X'} {reg['metricas']}")
    ram, vram = memoria_gb(cfg.modelo)
    for reg in registros:
        reg["ram_gb"], reg["vram_gb"] = ram, vram
    return registros


def salvar(agente: Agente, cfg: Config, registros: list[dict]) -> Path:
    caminho = _arquivo(agente, cfg)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros), encoding="utf-8")
    return caminho


def carregar(caminho: Path) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


# ---------------------------------------------------------------- fase 2: juiz
def julgar(agente: Agente, casos: list[Caso], juiz_padrao: str, juiz_alt: str, so: list[str] | None = None) -> None:
    """Grava cada veredito na hora: interromper não perde nada, e rodar de novo continua de onde parou.
    `so` escolhe e ordena as configurações (rótulos); sem isso, julga todas."""
    from metricas.geracao.juiz import Juiz

    por_caso = {c.id: c for c in casos}
    juizes: dict[str, Juiz] = {}
    pasta = RESULTADOS / agente.nome
    caminhos = [pasta / f"{r}.jsonl" for r in so] if so else sorted(pasta.glob("*.jsonl"))
    for caminho in caminhos:
        if not caminho.exists():
            print(f"  {caminho.name}: não existe, pulando")
            continue
        registros = carregar(caminho)
        modelo = registros[0]["config"]["modelo"] if registros else ""
        nome_juiz = juiz_alt if modelo.split(":")[0] == juiz_padrao.split(":")[0] else juiz_padrao
        juiz = juizes.setdefault(nome_juiz, Juiz(nome_juiz))
        mudou = False
        for reg in registros:
            if "fidelidade" in reg or not reg.get("resposta") or reg["caso"] not in por_caso:
                continue
            afirmacoes = juiz.fidelidade(por_caso[reg["caso"]].contexto, reg["resposta"])
            reg["fidelidade"] = (sum(bool(a["sustentada"]) for a in afirmacoes) / len(afirmacoes)) if afirmacoes else 0.0
            reg["juiz"], reg["afirmacoes"] = nome_juiz, afirmacoes
            mudou = True
            caminho.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros), encoding="utf-8")
        print(f"  juiz {nome_juiz} -> {caminho.name}{'' if mudou else ' (já julgado)'}")


# ---------------------------------------------------------------- fase 3: resumo
def _media(v: list[float]) -> float | None:
    return round(statistics.fmean(v), 3) if v else None


def _p95(v: list[float]) -> float | None:
    if not v:
        return None
    s = sorted(v)
    return round(s[min(len(s) - 1, max(0, int(round(0.95 * len(s))) - 1))], 2)


def resumir(agente: Agente) -> tuple[Path, Path]:
    linhas = []
    for caminho in sorted((RESULTADOS / agente.nome).glob("*.jsonl")):
        regs = carregar(caminho)
        if not regs:
            continue
        cfg = regs[0]["config"]
        # latência só de chamadas que responderam (JSON fora do contrato conta; Ollama fora do ar, não)
        tempos = [r["segundos"] for r in regs if not r.get("erro") or r["erro"].startswith("contrato")]
        linha = {
            "rotulo": cfg["rotulo"], "modelo": cfg["modelo"], "temperature": cfg["temperature"],
            "reasoning": cfg["reasoning"], "format": cfg["formato"], "n": len(regs),
            "json_valido": _media([float(r["json_valido"]) for r in regs]),
            "fidelidade": _media([r["fidelidade"] for r in regs if "fidelidade" in r]),
            "juiz": next((r["juiz"] for r in regs if "juiz" in r), ""),
        }
        for m in agente.metricas():
            linha[m] = _media([float(r["metricas"][m]) for r in regs if r["metricas"].get(m) is not None])
        linha.update(latencia_media_s=_media(tempos), latencia_p95_s=_p95(tempos),
                     tokens_s=_media([r["tokens_s"] for r in regs if r.get("tokens_s")]),
                     ram_gb=regs[0].get("ram_gb"), ollama=regs[0].get("ollama", ""))
        linhas.append(linha)

    csv_path, md_path = AQUI / f"{agente.nome}.csv", AQUI / f"{agente.nome}.md"
    if linhas:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(linhas[0]))
            w.writeheader()
            w.writerows(linhas)
    colunas = ["rotulo", "json_valido", "fidelidade", *agente.metricas(), "latencia_media_s", "latencia_p95_s",
               "tokens_s", "ram_gb", "ollama"]

    def fmt(v):
        if v is None:
            return "–"
        if isinstance(v, float) and v <= 1 and not isinstance(v, bool):
            return f"{v:.0%}"
        return str(v)

    tabela = ["| " + " | ".join(colunas) + " |", "|" + "|".join([" :-- "] + [" --: "] * (len(colunas) - 1)) + "|"]
    for linha in linhas:
        tabela.append("| " + " | ".join(
            str(linha[c] or "–") if c == "ollama" else
            fmt(linha[c]) if c not in ("latencia_media_s", "latencia_p95_s", "tokens_s", "ram_gb") else
            ("–" if linha[c] is None else f"{linha[c]:g}") for c in colunas) + " |")
    md_path.write_text(
        f"# Comparação de modelos locais: {agente.nome}\n\n"
        f"Gerado por `python -m experimentos.modelos.rodar {agente.nome}`. Hardware: {hardware()}. "
        f"A latência só é comparável entre linhas com a mesma versão do Ollama.\n\n"
        + "\n".join(tabela) + "\n", encoding="utf-8")
    return csv_path, md_path


# ---------------------------------------------------------------- CLI
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("agente", choices=sorted(_agentes()))
    p.add_argument("--modelos", nargs="*", help="sem isto, roda as configurações padrão do agente")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--reasoning", action="store_true")
    p.add_argument("--sem-format", action="store_true", help="não passa o JSON Schema como format")
    p.add_argument("--rotulo", default="")
    p.add_argument("--limite", type=int, help="só os N primeiros casos (rodada rápida)")
    p.add_argument("--pull", action="store_true", help="baixa os modelos que faltarem")
    p.add_argument("--refazer", action="store_true", help="roda de novo configurações que já têm resultado")
    p.add_argument("--juiz", action="store_true", help="fase 2: fidelidade com o LLM-juiz")
    p.add_argument("--so", nargs="*", help="com --juiz: só estes rótulos, nesta ordem")
    p.add_argument("--resumo", action="store_true", help="só refaz o CSV e o Markdown")
    a = p.parse_args()

    agente = _agentes()[a.agente]()
    casos = agente.casos()[: a.limite] if a.limite else agente.casos()
    if a.juiz:
        julgar(agente, casos, os.getenv("OLLAMA_JUIZ_MODEL", "gemma3:12b"), os.getenv("OLLAMA_JUIZ_ALT", "qwen3:8b"), a.so)
    elif not a.resumo:
        configs = ([Config(m, a.temperature, a.reasoning, not a.sem_format, a.rotulo if len(a.modelos) == 1 else "")
                    for m in a.modelos] if a.modelos else agente.configs_padrao)
        garantir_modelos([c.modelo for c in configs], a.pull)
        print(f"{len(casos)} casos × {len(configs)} configurações. Hardware: {hardware()}")
        for cfg in configs:
            if _arquivo(agente, cfg).exists() and not a.refazer:
                print(f"  [{cfg.rotulo}] já rodado (use --refazer)")
                continue
            print(f"  [{cfg.rotulo}] salvo em {salvar(agente, cfg, rodar_config(agente, cfg, casos))}")
    for caminho in resumir(agente):
        print(f"resumo: {caminho}")


if __name__ == "__main__":
    main()
