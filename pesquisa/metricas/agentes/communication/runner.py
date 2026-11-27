"""Avalia o Communication Agent sobre as fixtures, sem depender dos outros agentes.

Uso (a partir de pesquisa/):
    python -m metricas.agentes.communication.runner --nome qwen3_8b
    python -m metricas.agentes.communication.runner --nome smoke --limite 3
    python -m metricas.agentes.communication.runner --nome qwen3_8b --so-gerar
    python -m metricas.agentes.communication.runner --nome qwen3_8b --so-avaliar
    python -m metricas.agentes.communication.runner --nome qwen3_8b --sem-juiz

Fase 1 (gerar): roda `communication.montar_mensagem` em cada cenário de `cenarios.json`, usando a
grade e as evidências de `pesquisa/fixtures/communication/`. Salva as saídas brutas em
`saidas/communication_respostas_<nome>.json`.

Fase 2 (avaliar): calcula as métricas determinísticas (fidelidade ao plano, horários inventados,
citações, clareza, tom pela regra) e, opcionalmente, as do juiz (adequação do tom e faithfulness).
Salva `saidas/communication_<nome>.json`, `.csv` e `.md`.

O gerador é o modelo configurado em OLLAMA_COMMUNICATION_MODEL (padrão qwen3:8b); o juiz é
OLLAMA_JUIZ_MODEL (padrão gemma3:12b), sempre diferente do gerador.

O agente Communication vive na API (`api/app/modules/agentes/communication.py`), entregue pela
issue #20. As métricas puras (`metrics.py`) e os testes não dependem dele; só a geração precisa.
"""

import argparse
import csv
import json
import os
import platform
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from . import metrics as mc

RAIZ = Path(__file__).resolve().parents[4]
API = RAIZ / "api"
FIXTURES = RAIZ / "pesquisa" / "fixtures" / "communication"
CENARIOS = Path(__file__).with_name("cenarios.json")
SAIDAS = Path(__file__).with_name("saidas")

METAS = {
    "fidelidade_plano": 1.0,
    "planos_fieis": 1.0,
    "horarios_inventados": 0,
    "citacoes_invalidas": 0,
    "citacoes_validas": 1.0,
    "clareza_indice": 50.0,
    "tom_regra": 1.0,
    "tom_juiz": 0.8,
    "fidelidade_evidencias": 0.9,
    "latencia_s_p95": 30.0,
}


def carregar_api() -> SimpleNamespace:
    """Importa o agente da API. Falha com uma mensagem clara se o PR do Communication não estiver aqui."""
    if str(API) not in sys.path:
        sys.path.insert(0, str(API))
    try:
        from langchain_core.documents import Document

        from app.core.config import settings
        from app.modules.agentes import communication
        from app.modules.agentes.communication_schemas import CheckIn, Evidencia, PropostaGrade
        from app.modules.rag.verificador import verificar
    except ImportError as exc:
        raise SystemExit(
            "O runner precisa do Communication Agent (issue #20, PR #61) no código da API. "
            "Faça merge da branch feat/communication-modelos-locais antes de gerar as respostas."
        ) from exc
    return SimpleNamespace(settings=settings, communication=communication, CheckIn=CheckIn,
                           Evidencia=Evidencia, PropostaGrade=PropostaGrade,
                           verificar=verificar, Document=Document)


class Medidor:
    """Envolve o ChatOllama para guardar a saída bruta e a latência da chamada."""

    def __init__(self, modelo):
        self.modelo = modelo
        self.ultimo_conteudo = ""
        self.latencia_s = 0.0

    def invoke(self, mensagens):
        inicio = time.perf_counter()
        resposta = self.modelo.invoke(mensagens)
        self.latencia_s = time.perf_counter() - inicio
        self.ultimo_conteudo = resposta.content
        return resposta


def criar_modelo(nome: str, settings):
    from langchain_ollama import ChatOllama

    return ChatOllama(model=nome, temperature=0, reasoning=False,
                      base_url=settings.ollama_base_url,
                      client_kwargs={"timeout": settings.ollama_timeout_llm})


def carregar_fixtures(api: SimpleNamespace):
    cenarios = json.loads(CENARIOS.read_text(encoding="utf-8"))
    grade = api.PropostaGrade.model_validate(
        json.loads((FIXTURES / "grade.json").read_text(encoding="utf-8")))
    evidencias = [api.Evidencia.model_validate(e) for e in
                  json.loads((FIXTURES / "evidencias.json").read_text(encoding="utf-8"))]
    return cenarios, grade, evidencias


def gerar(nome: str, modelo: Optional[str], limite: Optional[int] = None) -> List[Dict]:
    api = carregar_api()
    modelo = modelo or api.settings.ollama_communication_model
    cenarios, grade, evidencias = carregar_fixtures(api)
    if limite:
        cenarios = cenarios[:limite]

    original = api.communication.llm.communication
    registros: List[Dict] = []
    for n, cenario in enumerate(cenarios, start=1):
        print(f"  [{n}/{len(cenarios)}] {cenario['id']} gerando...", flush=True)
        medidor = Medidor(criar_modelo(modelo, api.settings))
        api.communication.llm.communication = lambda: medidor
        try:
            mensagem = api.communication.montar_mensagem(
                grade, api.CheckIn(**cenario["checkin"]), evidencias)
        except Exception as exc:  # erro do Ollama não pode derrubar a rodada inteira
            print(f"    erro: {type(exc).__name__}: {exc}", flush=True)
            registros.append({"cenario": cenario["id"], "tom_esperado": cenario["tom_esperado"],
                              "erro": f"{type(exc).__name__}: {exc}"})
            continue
        registros.append({
            "cenario": cenario["id"],
            "tom_esperado": cenario["tom_esperado"],
            "tom_gerado": mensagem.tom,
            "latencia_s": round(medidor.latencia_s, 3),
            "abertura": api.communication.limpar_raciocinio(medidor.ultimo_conteudo),
            "abertura_bruta": medidor.ultimo_conteudo,
            "markdown": mensagem.markdown,
        })
    api.communication.llm.communication = original

    destino = SAIDAS / f"communication_respostas_{nome}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({
        "config": {"modelo": modelo, "cenarios": len(registros), "maquina": descrever_maquina(api.settings)},
        "respostas": registros,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Respostas salvas em {destino}")
    return registros


def avaliar_cenario(registro: Dict, cenario: Dict, grade, evidencias: List, juiz,
                    api: SimpleNamespace) -> Dict:
    if "erro" in registro:
        return registro

    grade_dict = {"blocos": [b.model_dump() for b in grade.blocos]}
    documentos = [api.Document(page_content=e.trecho, metadata={"source": e.fonte})
                  for e in evidencias]
    abertura = registro["abertura"]
    _, verificacao = api.verificar(abertura, documentos)
    total_citacoes = len(verificacao.citadas) + len(verificacao.fora_do_contexto)

    avaliacao = {
        "fidelidade_plano": mc.fidelidade_ao_plano(registro["markdown"], grade_dict),
        "horarios_inventados": mc.horarios_inventados(abertura, grade_dict),
        "citacoes_invalidas": verificacao.fora_do_contexto,
        "citacoes_validas": (round(len(verificacao.citadas) / total_citacoes, 4)
                             if total_citacoes else 1.0),
        "clareza": mc.clareza(abertura),
        "tom_regra": mc.tom_correto(registro["tom_gerado"], registro["tom_esperado"]),
    }
    if juiz is not None:
        avaliacao["tom_juiz"] = juiz.adequacao_tom(cenario["checkin"], cenario["tom_esperado"], abertura)
        avaliacao["fidelidade_evidencias"] = juiz.fidelidade(
            [e.model_dump() for e in evidencias], abertura)
    return avaliacao


def planejar_metas(resumo: Dict) -> List[Dict]:
    linhas = [
        ("Fidelidade ao plano", METAS["fidelidade_plano"], resumo["fidelidade_plano"], "maior ou igual"),
        ("Planos fiéis (todos os blocos, na ordem)", METAS["planos_fieis"], resumo["planos_fieis"], "maior ou igual"),
        ("Horários inventados", METAS["horarios_inventados"], resumo["horarios_inventados"], "igual"),
        ("Citações inválidas", METAS["citacoes_invalidas"], resumo["citacoes_invalidas"], "igual"),
        ("Citações válidas", METAS["citacoes_validas"], resumo["citacoes_validas"], "maior ou igual"),
        ("Clareza (Flesch-PT)", METAS["clareza_indice"], resumo["clareza_indice_mediana"], "maior ou igual"),
        ("Tom pela regra", METAS["tom_regra"], resumo["tom_regra"], "maior ou igual"),
    ]
    if resumo.get("tom_juiz") is not None:
        linhas.append(("Adequação do tom (juiz)", METAS["tom_juiz"], resumo["tom_juiz"], "maior ou igual"))
    if resumo.get("fidelidade_evidencias") is not None:
        linhas.append(("Faithfulness (juiz)", METAS["fidelidade_evidencias"],
                       resumo["fidelidade_evidencias"], "maior ou igual"))
    linhas.append(("Latência p95 (s)", METAS["latencia_s_p95"], resumo["latencia_s_p95"], "menor ou igual"))
    return [
        {"metrica": metrica, "meta": meta, "resultado": resultado, "regra": regra,
         "atingiu": (resultado is not None and
                     (resultado >= meta if regra != "menor ou igual" else resultado <= meta))}
        for metrica, meta, resultado, regra in linhas
    ]


def agregar(registros: List[Dict]) -> Dict:
    ok = [r for r in registros if "erro" not in r]
    return {
        "n": len(ok),
        "erros": len(registros) - len(ok),
        "fidelidade_plano": mc.media(r["avaliacao"]["fidelidade_plano"]["score"] for r in ok),
        "planos_fieis": mc.media(1.0 if r["avaliacao"]["fidelidade_plano"]["fiel"] else 0.0 for r in ok),
        "horarios_inventados": sum(len(r["avaliacao"]["horarios_inventados"]) for r in ok),
        "citacoes_invalidas": sum(len(r["avaliacao"]["citacoes_invalidas"]) for r in ok),
        "citacoes_validas": mc.media(r["avaliacao"]["citacoes_validas"] for r in ok),
        "clareza_indice_mediana": mc.mediana(r["avaliacao"]["clareza"]["indice"] for r in ok),
        "tom_regra": mc.media(1.0 if r["avaliacao"]["tom_regra"] else 0.0 for r in ok),
        "tom_juiz": mc.media(r["avaliacao"].get("tom_juiz", {}).get("score") for r in ok),
        "fidelidade_evidencias": mc.media(
            r["avaliacao"].get("fidelidade_evidencias", {}).get("score") for r in ok),
        "latencia_s_p50": mc.percentil((r["latencia_s"] for r in ok if "latencia_s" in r), 50),
        "latencia_s_p95": mc.percentil((r["latencia_s"] for r in ok if "latencia_s" in r), 95),
    }


def escrever_csv(registros: List[Dict], destino: Path) -> None:
    colunas = ["cenario", "tom_esperado", "tom_gerado", "tom_regra", "fidelidade_plano",
               "planos_fieis", "horarios_inventados", "citacoes_invalidas", "citacoes_validas",
               "clareza_indice", "tom_juiz", "fidelidade_evidencias", "latencia_s", "erro"]
    with open(destino, "w", encoding="utf-8", newline="") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(colunas)
        for r in registros:
            if "erro" in r:
                escritor.writerow([r["cenario"], r.get("tom_esperado"), None, None, None, None,
                                   None, None, None, None, None, None, None, r["erro"]])
                continue
            a = r["avaliacao"]
            escritor.writerow([
                r["cenario"], r["tom_esperado"], r["tom_gerado"], a["tom_regra"],
                a["fidelidade_plano"]["score"], a["fidelidade_plano"]["fiel"],
                ";".join(a["horarios_inventados"]), ";".join(a["citacoes_invalidas"]),
                a["citacoes_validas"], a["clareza"]["indice"],
                a.get("tom_juiz", {}).get("nota"), a.get("fidelidade_evidencias", {}).get("score"),
                r.get("latencia_s"), None,
            ])


def escrever_relatorio(resumo: Dict, linhas_meta: List[Dict], registros: List[Dict],
                       config: Dict, destino: Path) -> None:
    def fmt(valor):
        return "—" if valor is None else f"{valor:.4g}"

    linhas = [
        "# Communication: avaliação do agente", "",
        f"Modelo gerador: `{config['modelo']}`. "
        f"Juiz: {('`' + config['juiz'] + '`') if config.get('juiz') else 'não usado'}. "
        f"Cenários: {resumo['n']} (+{resumo['erros']} com erro).", "",
        f"Máquina: {config['maquina']}.", "",
        "## Resumo", "",
        "| métrica | meta | resultado | atingiu? |",
        "| --- | ---: | ---: | :---: |",
    ]
    for linha in linhas_meta:
        linhas.append(f"| {linha['metrica']} | {fmt(linha['meta'])} | {fmt(linha['resultado'])} | "
                      f"{'sim' if linha['atingiu'] else 'não'} |")
    linhas += ["", "## Por cenário", "",
               "| cenário | tom esperado | tom gerado | plano fiel | citações inválidas | clareza | latência (s) |",
               "| --- | --- | --- | :---: | :---: | ---: | ---: |"]
    for r in registros:
        if "erro" in r:
            linhas.append(f"| {r['cenario']} | {r.get('tom_esperado', '—')} | erro | — | — | — | — |")
            continue
        a = r["avaliacao"]
        linhas.append(
            f"| {r['cenario']} | {r['tom_esperado']} | {r['tom_gerado']} | "
            f"{'sim' if a['fidelidade_plano']['fiel'] else 'não'} | "
            f"{len(a['citacoes_invalidas'])} | {fmt(a['clareza']['indice'])} | {fmt(r.get('latencia_s'))} |")
    linhas += ["", "## O que cada métrica significa", "",
               "As definições, fórmulas e fontes estão em `METRICAS.md`, na mesma pasta.", ""]
    destino.write_text("\n".join(linhas), encoding="utf-8")


def descrever_maquina(settings) -> str:
    try:
        ram_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3)
        ram = f"{ram_gb} GB de RAM"
    except (ValueError, OSError, AttributeError):
        ram = "RAM desconhecida"
    return (f"{platform.system()} {platform.release()}, {platform.machine()}, {ram}, "
            f"Ollama em {settings.ollama_base_url}")


def avaliar(nome: str, sem_juiz: bool, modelo_juiz: str) -> None:
    api = carregar_api()
    caminho = SAIDAS / f"communication_respostas_{nome}.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    registros = dados["respostas"]
    cenarios = {c["id"]: c for c in json.loads(CENARIOS.read_text(encoding="utf-8"))}
    _, grade, evidencias = carregar_fixtures(api)

    juiz = None
    if not sem_juiz:
        from .juiz_tom import JuizCommunication

        if dados["config"]["modelo"] == modelo_juiz:
            raise SystemExit(f"O juiz ({modelo_juiz}) não pode ser o mesmo modelo do gerador.")
        juiz = JuizCommunication(modelo_juiz)

    for n, registro in enumerate(registros, start=1):
        print(f"  [{n}/{len(registros)}] {registro['cenario']} avaliando...", flush=True)
        registro["avaliacao"] = avaliar_cenario(
            registro, cenarios[registro["cenario"]], grade, evidencias, juiz, api)

    resumo = agregar(registros)
    linhas_meta = planejar_metas(resumo)
    config = {**dados["config"], "juiz": juiz.modelo if juiz else None}

    (SAIDAS / f"communication_{nome}.json").write_text(json.dumps({
        "config": config, "resumo": resumo, "metas": linhas_meta, "cenarios": registros,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    escrever_csv(registros, SAIDAS / f"communication_{nome}.csv")
    escrever_relatorio(resumo, linhas_meta, registros, config, SAIDAS / f"communication_{nome}.md")
    imprimir(resumo, linhas_meta)
    print(f"\nSalvo em {SAIDAS}")


def imprimir(resumo: Dict, linhas_meta: List[Dict]) -> None:
    print(f"\nCENÁRIOS: {resumo['n']} (+{resumo['erros']} com erro)")
    for linha in linhas_meta:
        resultado = "—" if linha["resultado"] is None else f"{linha['resultado']:.4g}"
        print(f"  {linha['metrica']:<42} meta={linha['meta']:<6g} resultado={resultado:<8} "
              f"{'OK' if linha['atingiu'] else 'ABAIXO'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nome", default="qwen3_8b")
    ap.add_argument("--modelo", default=None,
                    help="modelo gerador (padrão: OLLAMA_COMMUNICATION_MODEL)")
    ap.add_argument("--juiz-modelo", default=os.getenv("OLLAMA_JUIZ_MODEL", "gemma3:12b"))
    ap.add_argument("--limite", type=int, help="só os N primeiros cenários (teste rápido)")
    ap.add_argument("--sem-juiz", action="store_true", help="só as métricas determinísticas")
    fase = ap.add_mutually_exclusive_group()
    fase.add_argument("--so-gerar", action="store_true")
    fase.add_argument("--so-avaliar", action="store_true")
    args = ap.parse_args()

    SAIDAS.mkdir(parents=True, exist_ok=True)
    if not args.so_avaliar:
        gerar(args.nome, args.modelo, args.limite)
    if not args.so_gerar:
        avaliar(args.nome, args.sem_juiz, args.juiz_modelo)


if __name__ == "__main__":
    main()
