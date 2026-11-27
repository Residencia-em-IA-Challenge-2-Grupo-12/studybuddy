from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .schemas import PaginaPDF

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PAGINAS_PDF = 5
MAX_CARACTERES_PDF = 20_000


class PDFEntradaInvalida(ValueError):
    pass


def extrair_paginas(caminho: str | Path) -> list[PaginaPDF]:
    arquivo = Path(caminho)
    try:
        tamanho = arquivo.stat().st_size
    except OSError as exc:
        raise PDFEntradaInvalida("Não foi possível acessar o arquivo PDF.") from exc

    if not arquivo.is_file():
        raise PDFEntradaInvalida("O caminho informado não aponta para um arquivo.")
    if tamanho > MAX_PDF_BYTES:
        raise PDFEntradaInvalida("O PDF excede o limite de 10 MiB.")

    try:
        with arquivo.open("rb") as entrada:
            conteudo = entrada.read(MAX_PDF_BYTES + 1)
    except OSError as exc:
        raise PDFEntradaInvalida("Não foi possível ler o arquivo PDF.") from exc

    if len(conteudo) > MAX_PDF_BYTES:
        raise PDFEntradaInvalida("O PDF excede o limite de 10 MiB.")
    if b"%PDF-" not in conteudo[:1024]:
        raise PDFEntradaInvalida("O arquivo informado não é um PDF.")

    try:
        leitor = PdfReader(BytesIO(conteudo))
        if leitor.is_encrypted:
            raise PDFEntradaInvalida("PDFs protegidos por senha não são aceitos.")
        total_paginas = len(leitor.pages)
        if total_paginas == 0:
            raise PDFEntradaInvalida("O PDF não contém páginas.")
        if total_paginas > MAX_PAGINAS_PDF:
            raise PDFEntradaInvalida("O PDF excede o limite de 5 páginas.")

        paginas = []
        total_caracteres = 0
        for numero, pagina in enumerate(leitor.pages, start=1):
            texto = pagina.extract_text() or ""
            total_caracteres += len(texto)
            if total_caracteres > MAX_CARACTERES_PDF:
                raise PDFEntradaInvalida("O texto extraído excede o limite de 20.000 caracteres.")
            paginas.append(PaginaPDF(numero=numero, texto=texto))
    except PDFEntradaInvalida:
        raise
    except (PdfReadError, TypeError, ValueError) as exc:
        raise PDFEntradaInvalida("O PDF está corrompido ou não pôde ser lido.") from exc

    if not any(pagina.texto.strip() for pagina in paginas):
        raise PDFEntradaInvalida("O PDF não contém texto selecionável.")
    return paginas
