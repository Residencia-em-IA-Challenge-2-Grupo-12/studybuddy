"""Verificador de citações: confere a resposta do LLM antes de ela sair. Só regras, sem LLM.

O prompt manda citar a fonte como [Fonte: artigo_NN_nome.txt], mas é só instrução: o modelo pode citar
um artigo que não recebeu (citação inventada) ou não citar nada. O verificador:
  - remove do texto cada [Fonte: ...] que só aponta para artigos fora dos trechos entregues ao LLM;
  - reconhece citações em outro formato que alguns modelos copiam do cabeçalho do trecho
    ("[Fragmento #1 | Fonte: ../api/data/artigo_03_x.txt]", "[Fragmento #1: ...artigo_03_x.txt]") e as
    reescreve no formato padrão [Fonte: artigo_03_x.txt]; as que já vêm no formato padrão ficam como estão;
  - resolve citações só pelo número do trecho ("[Fragmento #2]", "[Fonte: Fragmento #2]"): os trechos chegam
    numerados a partir de 1 (fontes.formatar_trechos), então #2 é o artigo do segundo trecho. Número que não
    existe nos trechos conta como citação inventada e sai;
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

# Qualquer colchete com "Fonte:" ou "Fragmento #N:" dentro. Grupo 1: espaço antes; grupo 2: o conteúdo.
_CITACAO = re.compile(r"(\s*)\[([^\[\]]*?(?:Fonte\s*:|Fragmento\s*#\s*\d+)[^\[\]]*)\]", re.IGNORECASE)
_PADRAO = re.compile(r"^\s*Fonte\s*:", re.IGNORECASE)
_ARTIGO = re.compile(r"artigo_(\d{2})")
_FRAGMENTO = re.compile(r"#\s*(\d+)")

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
    normalizadas: int = 0                                        # citações reescritas para o formato padrão

    @property
    def alterou(self) -> bool:
        return bool(self.fora_do_contexto) or self.sem_citacao or bool(self.normalizadas)

    def resumo(self) -> str:
        if self.recusa:
            return "recusa: nada a conferir"
        partes = [f"{len(self.citadas)} artigo(s) citado(s) e presente(s) nos trechos"]
        if self.fora_do_contexto:
            partes.append(f"removida(s) citação(ões) de artigo(s) fora dos trechos: {', '.join(self.fora_do_contexto)}")
        if self.normalizadas:
            partes.append(f"{self.normalizadas} citação(ões) reescrita(s) no formato [Fonte: ...]")
        if self.sem_citacao:
            partes.append("sem citação válida: acrescentada a lista dos trechos consultados")
        return "; ".join(partes)

    def para_dict(self) -> dict:
        return {**asdict(self), "alterou": self.alterou}


def verificar(resposta: str, trechos: list[Document]) -> tuple[str, Verificacao]:
    """(resposta conferida, o que foi encontrado). A resposta só muda nos casos descritos no módulo."""
    if e_recusa(resposta):
        return resposta, Verificacao(recusa=True)

    ordem = [nome_fonte(d.metadata.get("source", "")) for d in trechos]  # Fragmento #1 = ordem[0]
    fontes = []
    for d in trechos:
        nome = nome_fonte(d.metadata.get("source", ""))
        if nome and nome not in fontes:
            fontes.append(nome)
    por_numero = {m.group(1): f for f in fontes if (m := _ARTIGO.search(f))}
    recebidos = set(por_numero)

    v = Verificacao()

    def conferir(m: re.Match) -> str:
        numeros = _ARTIGO.findall(m.group(2))
        if not numeros and "fragmento" in m.group(2).lower():  # "[Fragmento #2]": resolve pelo número do trecho
            frags = [int(n) for n in _FRAGMENTO.findall(m.group(2))]
            fora = [f"fragmento_{n}" for n in frags if not 1 <= n <= len(ordem)]
            numeros = [a.group(1) for n in frags if 1 <= n <= len(ordem) and (a := _ARTIGO.search(ordem[n - 1]))]
            if not numeros:
                v.fora_do_contexto.extend(f for f in fora if f not in v.fora_do_contexto)
                return "" if fora else m.group(0)
            if fora:
                v.fora_do_contexto.extend(f for f in fora if f not in v.fora_do_contexto)
            validos = list(dict.fromkeys(numeros))
            for n in validos:
                if f"artigo_{n}" not in v.citadas:
                    v.citadas.append(f"artigo_{n}")
            v.normalizadas += 1
            return f"{m.group(1)}[Fonte: {', '.join(dict.fromkeys(por_numero[n] for n in validos))}]"
        if not numeros:  # título solto ou "[Fonte: livro X]": não rastreável, mas não é um artigo inventado
            return m.group(0)
        validos = [n for n in numeros if n in recebidos]
        # Com pelo menos um artigo recebido, a citação fica (o estudante consegue conferir); sem nenhum, sai.
        destino = v.citadas if validos else v.fora_do_contexto
        for n in validos or numeros:
            if f"artigo_{n}" not in destino:
                destino.append(f"artigo_{n}")
        if not validos:
            return ""
        if _PADRAO.match(m.group(2)):
            return m.group(0)
        v.normalizadas += 1
        return f"{m.group(1)}[Fonte: {', '.join(dict.fromkeys(por_numero[n] for n in validos))}]"

    texto = _CITACAO.sub(conferir, resposta).strip()

    if not v.citadas and fontes:
        v.sem_citacao = True
        texto = f"{texto}\n\n{NOTA_SEM_CITACAO.format(fontes=', '.join(fontes))}"
    return texto, v
