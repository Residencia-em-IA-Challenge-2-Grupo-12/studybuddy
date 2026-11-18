"""Demonstração: os agentes colaborando, lado a lado com o pipeline clássico.

Uso (a partir de api/, com o Ollama aberto e o índice em chroma_db/):
    python demo.py                       # os 4 cenários, nos dois pipelines
    python demo.py --so-agentes          # só o multiagente (mais rápido)
    python demo.py "sua pergunta"        # uma pergunta qualquer
    python demo.py --interativo          # conversa: digite perguntas até "sair"

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


def imprimir(r: dict, completo: bool = False) -> None:
    print(f"\n  ▸ pipeline {r['pipeline'].upper()}  ({r['latencia_s']}s · {r['chamadas_llm']} chamada(s) ao LLM"
          ")")
    for e in r["rastro"]:
        cor = CORES.get(e["agente"], "")
        print(f"    {cor}[{e['agente']}]{FIM} {e['acao']} ({e['segundos']}s)")
        for linha in e["detalhe"].splitlines():
            print(f"        {linha.strip()}")
    texto = r["resposta"] if completo else textwrap.shorten(r["resposta"].replace("\n", " "), 700, placeholder=" [...]")
    corpo = textwrap.indent(texto, "      ")
    print(f"    Resposta:\n{corpo}")


AJUDA_INTERATIVO = """Modo interativo. Digite uma pergunta e tecle Enter.
Comandos: :agentes  :classico  :ambos  (troca o pipeline)  ·  :ajuda  ·  sair (ou Ctrl+D)"""
COMANDOS = {":agentes": ["agentes"], ":classico": ["classico"], ":ambos": ["classico", "agentes"]}


def interativo(pipelines: list[str], responder) -> None:
    """Laço de perguntas: cada uma passa pelos pipelines escolhidos e mostra a resposta inteira."""
    print(AJUDA_INTERATIVO)
    while True:
        try:
            pergunta = input(f"\n[{' + '.join(pipelines)}] você> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not pergunta:
            continue
        if pergunta.lower() in ("sair", "exit", "quit", ":sair"):
            return
        if pergunta.lower() == ":ajuda":
            print(AJUDA_INTERATIVO)
            continue
        if pergunta.lower() in COMANDOS:
            pipelines = COMANDOS[pergunta.lower()]
            print(f"Pipeline: {' + '.join(pipelines)}")
            continue
        if len(pergunta) < 3:
            print("Pergunta curta demais.")
            continue
        for p in pipelines:
            try:
                imprimir(responder(p, pergunta), completo=True)
            except Exception as exc:  # Ollama fora do ar, container parado: avisa e continua o laço
                print(f"  Erro no pipeline {p}: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pergunta", nargs="?")
    ap.add_argument("--so-agentes", action="store_true")
    ap.add_argument("--url-classico")
    ap.add_argument("--url-agentes")
    ap.add_argument("--interativo", "-i", action="store_true", help="digita perguntas em sequência até 'sair'")
    args = ap.parse_args()

    cenarios = [("Pergunta livre", args.pergunta)] if args.pergunta else CENARIOS
    pipelines = ["agentes"] if args.so_agentes else ["classico", "agentes"]
    urls = {"classico": args.url_classico, "agentes": args.url_agentes}
    responder = lambda p, pergunta: remoto(urls[p], pergunta) if urls[p] else local(p, pergunta)

    if args.interativo:
        # no modo interativo, o padrão é só o multiagente (o clássico dobra a espera); :ambos compara
        interativo(pipelines if args.so_agentes or args.url_classico else ["agentes"], responder)
        return

    for n, (titulo, pergunta) in enumerate(cenarios, 1):
        print("\n" + "=" * 100)
        print(f"CENÁRIO {n}: {titulo}\nPergunta: {pergunta}")
        print("=" * 100)
        for p in pipelines:
            imprimir(responder(p, pergunta))


if __name__ == "__main__":
    main()
