"""Perguntas com evidência sobre um PDF com texto selecionável.

Uso a partir de api/: python demo_multimodal_pdf.py arquivo.pdf "Qual é a data da prova?"
"""

import argparse
import sys

from app.modules.multimodal.pdf_text import PDFEntradaInvalida, extrair_paginas
from app.modules.multimodal.qa import (
    EntradaPDFBloqueada,
    FalhaConsultaModeloPDF,
    PerguntaPDFInvalida,
    RespostaModeloPDFInvalida,
    responder,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="caminho de um PDF com texto selecionável")
    parser.add_argument("pergunta", help="pergunta em texto sobre o PDF")
    args = parser.parse_args(argv)

    try:
        paginas = extrair_paginas(args.pdf)
        resposta = responder(paginas, args.pergunta)
    except (
        PDFEntradaInvalida,
        EntradaPDFBloqueada,
        FalhaConsultaModeloPDF,
        PerguntaPDFInvalida,
        RespostaModeloPDFInvalida,
    ) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(f"Status: {resposta.status}")
    print(f"Resposta: {resposta.resposta}")
    if resposta.evidencias:
        paginas_citadas = ", ".join(str(item.pagina) for item in resposta.evidencias)
        print(f"Páginas: {paginas_citadas}")
        for evidencia in resposta.evidencias:
            print(f'  Página {evidencia.pagina}: "{evidencia.trecho}"')
    else:
        print("Páginas: nenhuma")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
