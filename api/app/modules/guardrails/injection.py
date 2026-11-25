"""Barreira 1 de guardrails: detecta tentativas de prompt injection.

A classificação é determinística. Normaliza o texto, desfaz leetspeak, decodifica base64
e aplica padrões conhecidos. Roda antes de qualquer pipeline, sem LLM.
"""

import base64
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

FRASE_BLOQUEIO = (
    "Não consigo ajudar com esse pedido. Posso ajudar com organização dos estudos, "
    "técnicas de aprendizagem e rotina."
)

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

_PADROES = {
    "ignore_instrucoes": re.compile(
        r"\b(ignore|desconsidere|esqueca)\s+(todas\s+as\s+)?(instrucoes|regras|orientacoes)\b"
    ),
    "instrucoes_anteriores": re.compile(
        r"\b(instrucoes|regras|orientacoes)\b.{0,20}\b(anteriores|acima|do sistema|do modelo)\b"
    ),
    "modo_desenvolvedor": re.compile(
        r"\b(voce|vc)\b.{0,30}\b(modo desenvolvedor|developer mode|dan mode|sem restricoes)\b"
    ),
    "persona": re.compile(
        r"\b(assuma|entre em|inicie)\b.{0,20}\b(persona|papel|identidade|modo desenvolvedor|developer)\b"
    ),
    "system_prompt": re.compile(
        r"\b(revele|revela|mostre|repita|imprima|exiba|diga)\b.{0,30}"
        r"\b(system prompt|prompt do sistema|instrucoes do sistema|instrucoes iniciais)\b"
    ),
    "texto_acima": re.compile(
        r"\b(repita|imprima|exiba)\b.{0,20}\b(texto|prompt|mensagem)\b.{0,10}\b(acima|anterior|do sistema)\b"
    ),
    "jailbreak": re.compile(r"\b(jailbreak|dan mode|do anything now|sem filtros)\b"),
    "a_partir_de_agora": re.compile(
        r"\ba partir de agora\b.{0,20}\b(voce|vc)\b.{0,20}\b(e|sera|esta)\b"
    ),
    "tag_injection": re.compile(r"</?\s*user_input\s*>|\[/?(system|inst)\]"),
    "override": re.compile(r"\boverride\b.{0,20}\b(instructions|system)\b"),
}

_BASE64 = re.compile(r"[A-Za-z0-9+/=]{16,}")


class Categoria(str, Enum):
    OK = "OK"
    INJECTION = "INJECTION"


@dataclass(frozen=True)
class Veredito:
    categoria: Categoria
    motivos: tuple[str, ...] = ()

    def para_dict(self) -> dict:
        return {"categoria": self.categoria.value, "motivos": list(self.motivos)}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.translate(_LEET).split())


def _motivos(texto: str) -> list[str]:
    return [nome for nome, padrao in _PADROES.items() if padrao.search(texto)]


def envolver_input(texto: str) -> str:
    limpo = re.sub(r"</\s*user_input\s*>", "", texto, flags=re.IGNORECASE)
    return f"<user_input>{limpo}</user_input>"


def avaliar(texto: str) -> Veredito:
    motivos = _motivos(_normalizar(texto))
    if motivos:
        return Veredito(Categoria.INJECTION, tuple(motivos))

    for token in _BASE64.findall(texto):
        try:
            decodificado = base64.b64decode(token, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        achados = _motivos(_normalizar(decodificado))
        if achados:
            return Veredito(Categoria.INJECTION, tuple(f"base64:{m}" for m in achados))

    return Veredito(Categoria.OK)
