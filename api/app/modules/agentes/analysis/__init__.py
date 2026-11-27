"""Analysis Agent: cruza a demanda acadêmica com a capacidade do estudante e gera a PropostaGrade.

A alocação (dia, horário, carga) é heurística e determinística. O LLM só escolhe a técnica e escreve a
justificativa citando a base de artigos, sem mexer no controle.
"""

from .agente import AgenteAnalysis

__all__ = ["AgenteAnalysis"]
