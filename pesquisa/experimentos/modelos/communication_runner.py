"""Compara modelos locais no agente Communication: latência, tokens/s, memória e fidelidade à grade.

Uso (a partir da raiz do repositório):
    python pesquisa/experimentos/modelos/communication_runner.py
    python pesquisa/experimentos/modelos/communication_runner.py --modelos qwen3:4b --cenarios 1 --repeticoes 1 --saida /tmp/smoke

Para cada modelo x cenário de check-in, roda `communication.montar_mensagem` com um medidor em volta
do modelo do Ollama e grava:
  - communication.csv: uma linha por execução;
  - communication_resultados.json: tudo, inclusive a abertura bruta;
  - communication_cego.md: aberturas embaralhadas sem o nome do modelo, para leitura humana;
  - communication_gabarito.json: qual modelo gerou cada abertura do arquivo cego;
  - communication.md: relatório com médias e a escolha do modelo.

A fidelidade é medida de forma independente do agente: o runner confere cada bloco da grade no texto
final, conta horários que não existem na grade e citações removidas pelo verificador.
"""

import argparse
import csv
import json
import os
import platform
import random
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "api"))

from langchain_core.documents import Document  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.agentes import communication  # noqa: E402
from app.modules.agentes.communication_schemas import (  # noqa: E402
    CheckIn, Evidencia, PropostaGrade,
)
from app.modules.rag.verificador import verificar  # noqa: E402

MODELOS_PADRAO = ["qwen3:8b", "llama3.1:8b", "gemma3:12b", "qwen3:4b"]
CENARIOS = Path(__file__).with_name("communication_cenarios.json")
GRADE = RAIZ / "pesquisa" / "fixtures" / "communication" / "grade.json"
EVIDENCIAS = RAIZ / "pesquisa" / "fixtures" / "communication" / "evidencias.json"
HORARIO = re.compile(r"\b\d{1,2}:\d{2}\b")


class Medidor:
    """Envolve o ChatOllama e guarda a resposta bruta e os metadados de custo da última chamada."""

    def __init__(self, modelo):
        self.modelo = modelo
        self.ultima = {}

    def invoke(self, mensagens):
        inicio = time.perf_counter()
        resposta = self.modelo.invoke(mensagens)
        self.ultima = {"latencia_llm_s": time.perf_counter() - inicio,
                       **resposta.response_metadata}
        self.ultimo_conteudo = resposta.content
        return resposta


def criar_modelo(nome: str):
    from langchain_ollama import ChatOllama

    return ChatOllama(model=nome, temperature=0, reasoning=False,
                      base_url=settings.ollama_base_url,
                      client_kwargs={"timeout": settings.ollama_timeout_llm})


def vram_mb(nome: str) -> float | None:
    try:
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/ps", timeout=30) as resposta:
            modelos = json.load(resposta).get("models", [])
    except OSError:
        return None
    for item in modelos:
        if item.get("name") == nome or item.get("model") == nome:
            return round(item.get("size_vram", 0) / 1024 / 1024, 1)
    return None


def plano_esperado(grade: PropostaGrade) -> list[str]:
    linhas = ["## Seu plano da semana"]
    for bloco in grade.blocos:
        linha = f"- {bloco.dia}, {bloco.inicio}-{bloco.fim}: {bloco.disciplina}"
        linha += f". Material: [Material]({bloco.material})" if bloco.material is not None else "."
        linhas.append(linha)
    return linhas


def avaliar_saida(markdown: str, abertura_bruta: str, grade: PropostaGrade,
                  documentos: list[Document]) -> dict:
    linhas = plano_esperado(grade)
    posicoes = [markdown.find(linha) for linha in linhas]
    abertura = communication.limpar_raciocinio(abertura_bruta)
    horarios_grade = {f"{b.inicio}" for b in grade.blocos} | {f"{b.fim}" for b in grade.blocos}
    _, verificacao = verificar(abertura, documentos)
    return {
        "plano_fiel": all(p >= 0 for p in posicoes) and posicoes == sorted(posicoes),
        "horarios_inventados": sorted(set(HORARIO.findall(abertura)) - horarios_grade),
        "citacoes_invalidas": len(verificacao.fora_do_contexto),
        "caracteres_uteis": len(abertura),
        "caracteres_brutos": len(abertura_bruta),
        "abertura": abertura,
        "abertura_bruta": abertura_bruta,
        "citou": [f for f in verificacao.citadas],
    }


def rodar_cenario(nome_modelo: str, cenario: dict, grade: PropostaGrade,
                  evidencias: list[Evidencia]) -> dict:
    medidor = Medidor(criar_modelo(nome_modelo))
    communication.llm.communication = lambda: medidor
    checkin = CheckIn(**cenario["checkin"])
    inicio = time.perf_counter()
    try:
        mensagem = communication.montar_mensagem(grade, checkin, evidencias)
    except Exception as exc:  # erro do Ollama ou do contrato não pode derrubar a rodada inteira
        return {"modelo": nome_modelo, "cenario": cenario["id"],
                "tom_esperado": cenario["tom_esperado"], "erro": f"{type(exc).__name__}: {exc}"}
    total_s = time.perf_counter() - inicio
    meta = medidor.ultima
    tokens_saida = meta.get("eval_count")
    duracao_saida = meta.get("eval_duration", 0) / 1e9
    documentos = [Document(page_content=e.trecho, metadata={"source": e.fonte}) for e in evidencias]
    avaliacao = avaliar_saida(mensagem.markdown, medidor.ultimo_conteudo, grade, documentos)
    return {
        "modelo": nome_modelo,
        "cenario": cenario["id"],
        "tom_esperado": cenario["tom_esperado"],
        "tom_gerado": mensagem.tom,
        "tom_correto": mensagem.tom == cenario["tom_esperado"],
        "latencia_llm_s": round(meta.get("latencia_llm_s", 0), 2),
        "latencia_total_s": round(total_s, 2),
        "tokens_entrada": meta.get("prompt_eval_count"),
        "tokens_saida": tokens_saida,
        "tokens_por_s": round(tokens_saida / duracao_saida, 1) if tokens_saida and duracao_saida else None,
        "vram_mb": vram_mb(nome_modelo),
        **avaliacao,
        "markdown": mensagem.markdown,
    }


def media(valores):
    valores = [v for v in valores if v is not None]
    return round(statistics.mean(valores), 2) if valores else None


def mediana(valores):
    valores = [v for v in valores if v is not None]
    return round(statistics.median(valores), 2) if valores else None


def percentil(valores, p: float):
    """Percentil com interpolação linear (mesma convenção do numpy.percentile)."""
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    if len(valores) == 1:
        return round(valores[0], 2)
    posicao = (len(valores) - 1) * p / 100
    inferior = int(posicao)
    superior = min(inferior + 1, len(valores) - 1)
    fracao = posicao - inferior
    return round(valores[inferior] + (valores[superior] - valores[inferior]) * fracao, 2)


def descrever_maquina() -> str:
    try:
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3)
        ram = f"{ram_gb} GB de RAM"
    except (ValueError, OSError, AttributeError):
        ram = "RAM desconhecida"
    return (f"{platform.system()} {platform.release()}, {platform.machine()}, {ram}, "
            f"Ollama em {settings.ollama_base_url}")


def agregar(registros: list[dict], modelos: list[str]) -> dict:
    resumo = {}
    for nome in modelos:
        grupo = [r for r in registros if r["modelo"] == nome and "erro" not in r]
        resumo[nome] = {
            "n": len(grupo),
            "erros": sum(1 for r in registros if r["modelo"] == nome and "erro" in r),
            "tom_correto": media(1.0 if r["tom_correto"] else 0.0 for r in grupo),
            "plano_fiel": media(1.0 if r["plano_fiel"] else 0.0 for r in grupo),
            "horarios_inventados": sum(len(r["horarios_inventados"]) for r in grupo),
            "citacoes_invalidas": sum(r["citacoes_invalidas"] for r in grupo),
            "latencia_llm_s_mediana": mediana(r["latencia_llm_s"] for r in grupo),
            "latencia_llm_s_p95": percentil([r["latencia_llm_s"] for r in grupo], 95),
            "latencia_total_s_mediana": mediana(r["latencia_total_s"] for r in grupo),
            "latencia_total_s_p95": percentil([r["latencia_total_s"] for r in grupo], 95),
            "tokens_por_s_mediana": mediana(r["tokens_por_s"] for r in grupo),
            "tokens_saida_mediana": mediana(r["tokens_saida"] for r in grupo),
            "caracteres_uteis_mediana": mediana(r["caracteres_uteis"] for r in grupo),
            "fracao_descartada": (
                round(1 - sum(r["caracteres_uteis"] for r in grupo)
                      / max(sum(r["caracteres_brutos"] for r in grupo), 1), 3)
                if grupo else None),
            "vram_mb": next((r["vram_mb"] for r in grupo if r["vram_mb"] is not None), None),
        }
    return resumo


def escrever_csv(registros: list[dict], destino: Path) -> None:
    colunas = ["modelo", "cenario", "repeticao", "tom_esperado", "tom_gerado", "tom_correto",
               "latencia_llm_s", "latencia_total_s", "tokens_entrada", "tokens_saida",
               "tokens_por_s", "caracteres_uteis", "caracteres_brutos", "vram_mb",
               "plano_fiel", "horarios_inventados", "citacoes_invalidas", "erro"]
    with open(destino, "w", encoding="utf-8", newline="") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(colunas)
        for r in registros:
            linha = []
            for coluna in colunas:
                valor = r.get(coluna)
                if isinstance(valor, list):
                    valor = ";".join(valor)
                linha.append(valor)
            escritor.writerow(linha)


def escrever_cego(registros: list[dict], cenarios: list[dict],
                  destino: Path, gabarito_path: Path, semente: int) -> None:
    sorteio = random.Random(semente)
    gabarito = {}
    linhas = ["# Leitura cega das aberturas do Communication", "",
              "Avalie cada abertura sem saber o modelo. Para cada cenário, dê duas notas de 1 a 5:",
              "naturalidade (soa como um mentor humano?) e adequação ao tom (combina com o check-in?).", "",
              "A grade é a mesma em todos os casos e já foi aprovada: o texto abaixo é só a abertura.", ""]
    for cenario in cenarios:
        grupo = [r for r in registros if r["cenario"] == cenario["id"] and "erro" not in r]
        if not grupo:
            continue
        # a leitura cega compara modelos, não repetições: uma abertura por modelo
        por_modelo = {}
        for registro in grupo:
            por_modelo.setdefault(registro["modelo"], registro)
        grupo = list(por_modelo.values())
        sorteio.shuffle(grupo)
        c = cenario["checkin"]
        linhas.append(f"## {cenario['id']}")
        linhas.append(f"*{cenario['descricao']}*")
        linhas.append(f"Check-in: humor {c['humor']}/5, estresse {c['estresse']}/5, "
                      f"sono {c['sono']}/5, fadiga {c['fadiga']}/5  ")
        linhas.append(f"Tom esperado: **{cenario['tom_esperado']}**")
        linhas.append("")
        for indice, registro in enumerate(grupo, start=1):
            rotulo = f"{cenario['id']}-{indice}"
            gabarito[rotulo] = registro["modelo"]
            linhas.append(f"**{indice}.** {registro['abertura']}")
            linhas.append("")
            linhas.append("Naturalidade: __/5   Tom: __/5")
            linhas.append("")
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
    with open(gabarito_path, "w", encoding="utf-8") as fh:
        json.dump(gabarito, fh, ensure_ascii=False, indent=2)


def escrever_relatorio(resumo: dict, registros: list[dict], destino: Path) -> None:
    def chave(nome: str):
        r = resumo[nome]
        return (r["erros"], r["horarios_inventados"], r["citacoes_invalidas"],
                -(r["tom_correto"] or 0), -(r["plano_fiel"] or 0),
                r["latencia_llm_s_mediana"] or 10**9,
                r["latencia_llm_s_p95"] or 10**9)

    melhores = sorted(resumo, key=chave)
    escolhido = melhores[0] if melhores else None
    cenarios = len({r["cenario"] for r in registros})
    repeticoes = max((r.get("repeticao", 1) for r in registros), default=1)
    linhas = [
        "# Communication: comparação de modelos locais", "",
        f"Máquina: {descrever_maquina()}.", "",
        f"Cada modelo respondeu aos mesmos {cenarios} check-in(s) sobre a mesma grade aprovada, "
        f"com {repeticoes} repetição(ões) por cenário. "
        "O plano é montado sem LLM, então a diferença entre modelos aparece na abertura: "
        "tom, naturalidade e custo.", "",
        "Tom e plano são determinísticos (a regra de tom e a montagem da grade não usam LLM) e por "
        "isso não discriminam modelos; servem como trava contra regressão. "
        "As métricas que de fato diferenciam são horários inventados, citações inválidas, "
        "caracteres úteis e custo.", "",
        "## Resultado por modelo", "",
        "| modelo | erros | tom correto | plano fiel | horários inventados | citações inválidas | latência LLM mediana (s) | p95 (s) | tokens/s | chars úteis | VRAM (MB) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for nome, r in resumo.items():
        linhas.append(
            f"| `{nome}` | {r['erros']} | {r['tom_correto']} | {r['plano_fiel']} | "
            f"{r['horarios_inventados']} | {r['citacoes_invalidas']} | "
            f"{r['latencia_llm_s_mediana']} | {r['latencia_llm_s_p95']} | "
            f"{r['tokens_por_s_mediana']} | {r['caracteres_uteis_mediana']} | {r['vram_mb']} |")
    linhas += ["", "Fração descartada da saída bruta (raciocínio que não chega ao usuário): "
               + ", ".join(f"`{n}`={r['fracao_descartada']}" for n, r in resumo.items()), "",
               "## Escolha", "",
               f"Modelo padrão proposto para o Communication: **`{escolhido}`**.", "",
               "Critério, nesta ordem: menos erros, nenhum horário inventado, nenhuma citação inválida, "
               "depois tom e plano corretos, e por fim a latência mediana (o p95 desempata). "
               "A naturalidade fica com a leitura cega (`communication_cego.md`), porque nenhuma "
               "métrica automática a mede.", "",
               "As aberturas de cada execução estão em `communication_resultados.json`. "
               "O gabarito da leitura cega está em `communication_gabarito.json`.", ""]
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", default=",".join(MODELOS_PADRAO),
                    help="lista separada por vírgula (padrão: %(default)s)")
    ap.add_argument("--cenarios", type=int, help="só os N primeiros cenários (teste rápido)")
    ap.add_argument("--saida", type=Path, default=Path(__file__).parent)
    ap.add_argument("--semente", type=int, default=42, help="embaralhamento da leitura cega")
    ap.add_argument("--repeticoes", type=int, default=3,
                    help="execuções por modelo x cenário, para mediana e p95 (padrão: %(default)s)")
    args = ap.parse_args()

    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    cenarios = json.loads(CENARIOS.read_text(encoding="utf-8"))
    if args.cenarios:
        cenarios = cenarios[:args.cenarios]
    grade = PropostaGrade.model_validate(json.loads(GRADE.read_text(encoding="utf-8")))
    evidencias = [Evidencia.model_validate(e) for e in json.loads(EVIDENCIAS.read_text(encoding="utf-8"))]
    for cenario in cenarios:
        esperado = communication.escolher_tom(CheckIn(**cenario["checkin"]))
        if esperado != cenario["tom_esperado"]:
            raise SystemExit(f"{cenario['id']}: fixture espera {cenario['tom_esperado']}, "
                             f"a regra escolhe {esperado}")

    saida = args.saida
    saida.mkdir(parents=True, exist_ok=True)
    registros = []
    for nome in modelos:
        for n, cenario in enumerate(cenarios, start=1):
            for repeticao in range(1, args.repeticoes + 1):
                print(f"[{nome}] {n}/{len(cenarios)} {cenario['id']} "
                      f"(rep {repeticao}/{args.repeticoes})...", flush=True)
                registro = rodar_cenario(nome, cenario, grade, evidencias)
                registro["repeticao"] = repeticao
                if "erro" in registro:
                    print(f"  erro: {registro['erro']}", flush=True)
                else:
                    print(f"  tom={registro['tom_gerado']} latência={registro['latencia_llm_s']}s "
                          f"tokens/s={registro['tokens_por_s']}", flush=True)
                registros.append(registro)

    resumo = agregar(registros, modelos)
    escrever_csv(registros, saida / "communication.csv")
    (saida / "communication_resultados.json").write_text(
        json.dumps({"resumo": resumo, "execucoes": registros}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    escrever_cego(registros, cenarios, saida / "communication_cego.md",
                  saida / "communication_gabarito.json", args.semente)
    escrever_relatorio(resumo, registros, saida / "communication.md")
    print(f"\nSalvo em {saida}")


if __name__ == "__main__":
    main()
