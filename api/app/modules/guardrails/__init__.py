"""Guardrails: barreiras que rodam antes do Maestro. Cada barreira devolve um `Veredito` ([0.1])."""

from .injection import Categoria, FRASE_BLOQUEIO, Veredito, avaliar, envolver_input

__all__ = ["Categoria", "FRASE_BLOQUEIO", "Veredito", "avaliar", "envolver_input"]
