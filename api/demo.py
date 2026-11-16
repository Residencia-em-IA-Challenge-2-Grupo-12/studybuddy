"""Demonstração: os agentes colaborando, lado a lado com o pipeline clássico.

Uso (a partir de api/, com o Ollama aberto e o índice em chroma_db/):
    python demo.py                       # os 4 cenários, nos dois pipelines
    python demo.py --so-agentes          # só o multiagente (mais rápido)
    python demo.py "sua pergunta"        # uma pergunta qualquer

Ou contra os containers (docker compose up), sem rodar nada localmente:
    python demo.py --url-classico http://localhost:8001 --url-agentes http://localhost:8002
"""

import argparse
import json
import textwrap
import urllib.request

CENARIOS = [
    ("Persona Lucas (CLT): a Triagem extrai a jornada e decide por um PLANO",
     "Trabalho 8 horas por dia em regime CLT e tenho umas 2 horas livres à noite. Como encaixo o estudo sem prejudicar o sono?"),
    ("Persona Lisa (overplanning): mesma base, outro problema, outro plano",
     "Passo horas montando planilhas e cronogramas que quebram no primeiro imprevisto. O que faço?"),
    ("Pergunta de entendimento: a Triagem decide por uma EXPLICAÇÃO, não um plano",
     "Por que eu vou empurrando o estudo quando a prova ainda está longe?"),
    ("Fora de escopo 'perigosa': passa pelo porteiro, a regra 2 do prompt recusa",
     "Qual o melhor remédio para dormir quando estou ansioso antes da prova?"),
    ("Fora de escopo óbvia: o porteiro barra sem chamar nenhum agente",
     "Qual a capital da Austrália?"),
]

CORES = {"Triagem": "\033[35m", "Planejador": "\033[34m", "busca": "\033[34m", "geração": "\033[32m"}
FIM = "\033[0m"


def local(pipeline: str, pergunta: str) -> dict:
    from app.modules.assistente import service

    return service.responder(pergunta, pipeline).model_dump()


def remoto(url: str, pergunta: str) -> dict:
    req = urllib.request.Request(f"{url}/assistente/perguntar", data=json.dumps({"pergunta": pergunta}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.load(resp)


def imprimir(r: dict) -> None:
    print(f"\n  ▸ pipeline {r['pipeline'].upper()}  ({r['latencia_s']}s · {r['chamadas_llm']} chamada(s) ao LLM"
          ")")
    for e in r["rastro"]:
        cor = CORES.get(e["agente"], "")
        print(f"    {cor}[{e['agente']}]{FIM} {e['acao']} ({e['segundos']}s)")
        for linha in e["detalhe"].splitlines():
            print(f"        {linha.strip()}")
    corpo = textwrap.indent(textwrap.shorten(r["resposta"].replace("\n", " "), 700, placeholder=" [...]"), "      ")
    print(f"    Resposta:\n{corpo}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pergunta", nargs="?")
    ap.add_argument("--so-agentes", action="store_true")
    ap.add_argument("--url-classico")
    ap.add_argument("--url-agentes")
    args = ap.parse_args()

    cenarios = [("Pergunta livre", args.pergunta)] if args.pergunta else CENARIOS
    pipelines = ["agentes"] if args.so_agentes else ["classico", "agentes"]
    urls = {"classico": args.url_classico, "agentes": args.url_agentes}

    for n, (titulo, pergunta) in enumerate(cenarios, 1):
        print("\n" + "=" * 100)
        print(f"CENÁRIO {n}: {titulo}\nPergunta: {pergunta}")
        print("=" * 100)
        for p in pipelines:
            imprimir(remoto(urls[p], pergunta) if urls[p] else local(p, pergunta))


if __name__ == "__main__":
    main()
