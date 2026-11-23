"""AgenteAnalysis: ContextoEstudante -> PropostaGrade (contrato da [0.1]).

Por enquanto o Pomodoro é fixo em 25/5. O tamanho adaptativo, a prioridade por prazo e a redução de danos
entram na [3.2], o reajuste na [3.3] e a justificativa por LLM depois da alocação.
"""

from app.modules.agentes.contratos import ContextoEstudante, DiretivaMaestro, PropostaGrade

from .alocacao import alocar


class AgenteAnalysis:
    nome = "Analysis"

    def propor(self, ctx: ContextoEstudante, diretiva: DiretivaMaestro | None = None) -> PropostaGrade:
        blocos, fora = alocar(ctx)
        return PropostaGrade(estudante_id=ctx.estudante_id, semana_inicio=ctx.semana_inicio,
                             blocos=blocos, fora_da_grade=fora)
