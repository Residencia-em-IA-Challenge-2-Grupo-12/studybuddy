"""AgenteAnalysis: ContextoEstudante -> PropostaGrade (contrato da [0.1]).

- Ritmo do Pomodoro pelo índice de capacidade do check-in (pomodoro.py).
- Prioridade por prazo e dificuldade: urgentes primeiro e com mais blocos (prioridade.py).
- Rota "reducao_danos" do Maestro: dia leve, só baixa carga, pausas maiores, poucos blocos por dia.
  A alta carga vai inteira para fora_da_grade.
O reajuste ([3.3]) e a justificativa por LLM entram depois.
"""

from app.core.config import settings
from app.modules.agentes.contratos import ContextoEstudante, DiretivaMaestro, PropostaGrade

from . import prioridade
from .alocacao import alocar
from .pomodoro import ritmo


class AgenteAnalysis:
    nome = "Analysis"

    def propor(self, ctx: ContextoEstudante, diretiva: DiretivaMaestro | None = None) -> PropostaGrade:
        reducao = diretiva is not None and diretiva.rota == "reducao_danos"
        r = ritmo(ctx.indice_capacidade, reducao_danos=reducao)
        hoje = ctx.semana_inicio
        ordenados = prioridade.ordenar(ctx.materiais, hoje)
        cortados = [m.id for m in ordenados if reducao and m.carga == "alta"]

        blocos, fora = alocar(
            ctx, foco_min=r.foco_min, pausa_min=r.pausa_min,
            materiais=[m for m in ordenados if m.id not in cortados],
            necessidade=lambda m: prioridade.blocos(m, r.foco_min, hoje),
            urgentes={m.id for m in ordenados if prioridade.urgente(m, hoje)},
            max_blocos_dia=settings.analysis_reducao_max_blocos_dia if reducao else None,
        )
        return PropostaGrade(
            estudante_id=ctx.estudante_id, semana_inicio=ctx.semana_inicio,
            modo="reducao_danos" if reducao else "normal",
            blocos=blocos, fora_da_grade=cortados + fora,
        )
