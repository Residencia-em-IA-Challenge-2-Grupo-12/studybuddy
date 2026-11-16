"""Verificador de citações: confere a resposta do LLM antes de ela sair. Só regras, sem LLM.

O prompt manda citar a fonte como [Fonte: artigo_NN_nome.txt], mas é só instrução: o modelo pode citar
um artigo que não recebeu (citação inventada) ou não citar nada. O verificador:
  - remove do texto cada [Fonte: ...] que só aponta para artigos fora dos trechos entregues ao LLM;
  - quando não sobra nenhuma citação válida, acrescenta uma linha com os artigos consultados, para o
    estudante ainda poder conferir (sem o formato [Fonte: ...]: não finge que o modelo citou);
  - não mexe em recusas.
As regras são as mesmas das métricas de citação (pesquisa/metricas/geracao/metrics.py).
"""

import re
import unicodedata
from dataclasses import asdict, dataclass, field

from langchain_core.documents import Document

from .fontes import nome_fonte
from .prompts import FRASE_RECUSA

_CITACAO = re.compile(r"\s*\[\s*Fonte\s*:\s*([^\]]+)\]", re.IGNORECASE)
_ARTIGO = re.compile(r"artigo_(\d{2})")

NOTA_SEM_CITACAO = "Trechos consultados (a resposta não citou a fonte): {fontes}."


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.split())


def e_recusa(resposta: str) -> bool:
    return _normalizar(FRASE_RECUSA.rstrip(".")) in _normalizar(resposta)


@dataclass
class Verificacao:
    recusa: bool = False
    citadas: list[str] = field(default_factory=list)            # artigos citados e presentes nos trechos
    fora_do_contexto: list[str] = field(default_factory=list)   # citações removidas: só artigos que o LLM não recebeu
    sem_citacao: bool = False                                    # não sobrou nenhuma citação válida

    @property
    def alterou(self) -> bool:
        return bool(self.fora_do_contexto) or self.sem_citacao

    def resumo(self) -> str:
        if self.recusa:
            return "recusa: nada a conferir"
        partes = [f"{len(self.citadas)} artigo(s) citado(s) e presente(s) nos trechos"]
        if self.fora_do_contexto:
            partes.append(f"removida(s) citação(ões) de artigo(s) fora dos trechos: {', '.join(self.fora_do_contexto)}")
        if self.sem_citacao:
            partes.append("sem citação válida: acrescentada a lista dos trechos consultados")
        return "; ".join(partes)

    def para_dict(self) -> dict:
        return {**asdict(self), "alterou": self.alterou}


def verificar(resposta: str, trechos: list[Document]) -> tuple[str, Verificacao]:
    """(resposta conferida, o que foi encontrado). A resposta só muda nos casos descritos no módulo."""
    if e_recusa(resposta):
        return resposta, Verificacao(recusa=True)

    fontes = []
    for d in trechos:
        nome = nome_fonte(d.metadata.get("source", ""))
        if nome and nome not in fontes:
            fontes.append(nome)
    recebidos = {m.group(1) for f in fontes if (m := _ARTIGO.search(f))}

    v = Verificacao()

    def conferir(m: re.Match) -> str:
        numeros = _ARTIGO.findall(m.group(1))
        if not numeros:  # "[Fonte: Fragmento #2]", título solto: não rastreável, mas não é um artigo inventado
            return m.group(0)
        validos = [n for n in numeros if n in recebidos]
        # Com pelo menos um artigo recebido, a citação fica (o estudante consegue conferir); sem nenhum, sai.
        destino = v.citadas if validos else v.fora_do_contexto
        for n in validos or numeros:
            if f"artigo_{n}" not in destino:
                destino.append(f"artigo_{n}")
        return m.group(0) if validos else ""

    texto = _CITACAO.sub(conferir, resposta).strip()

    if not v.citadas and fontes:
        v.sem_citacao = True
        texto = f"{texto}\n\n{NOTA_SEM_CITACAO.format(fontes=', '.join(fontes))}"
    return texto, v
