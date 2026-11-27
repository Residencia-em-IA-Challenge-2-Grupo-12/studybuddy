"""Métricas determinísticas do Communication Agent. Funções puras (só stdlib), sem LLM.

O agente tem duas partes com naturezas diferentes:
  - o PLANO, montado sem LLM a partir da PropostaGrade aprovada;
  - a ABERTURA, escrita pelo LLM com o tom escolhido pelo check-in.
Por isso as métricas recebem as duas separadas: o plano é cobrado por fidelidade exata; a abertura,
por horários inventados, citações e legibilidade.
"""

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence

_HORARIO = re.compile(r"\b\d{1,2}:\d{2}\b")
_CITACAO = re.compile(r"\[\s*Fonte\s*:\s*([^\]]+)\]", re.IGNORECASE)
_ARTIGO = re.compile(r"artigo_(\d{2})")
_VOGAIS = set("aeiouáàâãéêíóôõúü")


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.split())


def linha_do_bloco(bloco: Dict) -> str:
    """A mesma linha que `communication.montar_plano_markdown` produz para um bloco."""
    linha = f"- {bloco['dia']}, {bloco['inicio']}-{bloco['fim']}: {bloco['disciplina']}"
    material = bloco.get("material")
    linha += f". Material: [Material]({material})" if material is not None else "."
    return linha


def linhas_da_grade(grade: Dict) -> List[str]:
    return [linha_do_bloco(bloco) for bloco in grade["blocos"]]


def fidelidade_ao_plano(markdown: str, grade: Dict) -> Dict:
    """Fração de blocos reproduzidos com dia, horário, disciplina e material exatos, na ordem aprovada.

    Um bloco conta como presente só se a linha inteira aparecer. A ordem entra no veredito `fiel`:
    o plano pode ter todos os blocos e ainda assim estar embaralhado, o que já é uma alteração.
    """
    linhas = linhas_da_grade(grade)
    posicoes = [markdown.find(linha) for linha in linhas]
    presentes = sum(posicao >= 0 for posicao in posicoes)
    na_ordem = all(posicao >= 0 for posicao in posicoes) and posicoes == sorted(posicoes)
    total = len(linhas)
    return {
        "blocos": total,
        "blocos_presentes": presentes,
        "blocos_ausentes": [linha for linha, posicao in zip(linhas, posicoes) if posicao < 0],
        "na_ordem": na_ordem,
        "score": round(presentes / total, 4) if total else 1.0,
        "fiel": presentes == total and na_ordem,
    }


def horarios_inventados(abertura: str, grade: Dict) -> List[str]:
    """Horários citados na abertura que não existem na grade aprovada.

    A abertura é a parte escrita pelo LLM; o plano é montado por código e não entra nesta conta.
    """
    da_grade = {b["inicio"] for b in grade["blocos"]} | {b["fim"] for b in grade["blocos"]}
    return sorted(set(_HORARIO.findall(abertura)) - da_grade)


def artigos_citados(texto: str) -> List[str]:
    """Números de artigo citados em [Fonte: ...], sem repetição e na ordem de aparição."""
    vistos: List[str] = []
    for bloco in _CITACAO.findall(texto):
        for numero in _ARTIGO.findall(bloco):
            if numero not in vistos:
                vistos.append(numero)
    return vistos


def citacoes_validas(texto: str, fontes_validas: Iterable[str]) -> Dict:
    """Citações rastreáveis contra os artigos entregues ao agente.

    Mesma convenção do verificador da API (`rag/verificador.py`): só conta como citação o padrão
    `artigo_NN`; um `[Fonte: Título solto]` fica de fora por não ser rastreável.
    """
    recebidos = {m.group(1) for fonte in fontes_validas if (m := _ARTIGO.search(fonte))}
    citados = artigos_citados(texto)
    invalidos = [numero for numero in citados if numero not in recebidos]
    total = len(citados)
    return {
        "total": total,
        "citados": citados,
        "invalidos": invalidos,
        "score": round((total - len(invalidos)) / total, 4) if total else 1.0,
    }


def _silabas(palavra: str) -> int:
    """Aproximação por grupos de vogais, suficiente para a fórmula de Flesch."""
    grupos, vogal_anterior = 0, False
    for letra in palavra.lower():
        vogal = letra in _VOGAIS
        if vogal and not vogal_anterior:
            grupos += 1
        vogal_anterior = vogal
    return max(grupos, 1)


def clareza(texto: str, remover_links: bool = True) -> Dict:
    """Índice de legibilidade de Flesch adaptado ao português.

    Fórmula: 248,835 − 1,015 × (palavras/frases) − 84,6 × (sílabas/palavras).
    Faixa 0–100: quanto maior, mais fácil. Marcas de markdown, links e citações saem da conta
    porque não são lidos como texto pelo estudante.
    """
    if remover_links:
        texto = _CITACAO.sub("", texto)
        texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"^#+\s*", "", texto, flags=re.MULTILINE)
    palavras = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", texto)
    frases = [frase for frase in re.split(r"[.!?]+", texto) if frase.strip()]
    if not palavras or not frases:
        return {"palavras": 0, "frases": 0, "palavras_por_frase": None,
                "silabas_por_palavra": None, "indice": None}
    silabas = sum(_silabas(palavra) for palavra in palavras)
    palavras_por_frase = len(palavras) / len(frases)
    silabas_por_palavra = silabas / len(palavras)
    indice = 248.835 - 1.015 * palavras_por_frase - 84.6 * silabas_por_palavra
    return {
        "palavras": len(palavras),
        "frases": len(frases),
        "palavras_por_frase": round(palavras_por_frase, 2),
        "silabas_por_palavra": round(silabas_por_palavra, 2),
        "indice": round(indice, 1),
    }


def tom_correto(tom_gerado: str, tom_esperado: str) -> bool:
    return tom_gerado == tom_esperado


def media(valores: Sequence[Optional[float]]) -> Optional[float]:
    valores = [valor for valor in valores if valor is not None]
    return round(sum(valores) / len(valores), 4) if valores else None


def mediana(valores: Sequence[Optional[float]]) -> Optional[float]:
    valores = sorted(valor for valor in valores if valor is not None)
    if not valores:
        return None
    meio = len(valores) // 2
    if len(valores) % 2:
        return round(valores[meio], 4)
    return round((valores[meio - 1] + valores[meio]) / 2, 4)


def percentil(valores: Sequence[Optional[float]], p: float) -> Optional[float]:
    """Percentil por interpolação linear (p entre 0 e 100)."""
    ordenados = sorted(valor for valor in valores if valor is not None)
    if not ordenados:
        return None
    if len(ordenados) == 1:
        return round(ordenados[0], 4)
    posicao = (len(ordenados) - 1) * p / 100
    baixo, alto = int(posicao), min(int(posicao) + 1, len(ordenados) - 1)
    fracao = posicao - baixo
    return round(ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * fracao, 4)
