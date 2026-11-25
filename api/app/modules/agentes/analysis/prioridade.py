"""[3.2] Prioridade por prazo e dificuldade.

- Ordem: prazo mais próximo primeiro (sem prazo vai por último); empate -> mais difícil primeiro.
- Urgente: prazo a até ANALYSIS_DIAS_URGENCIA dias do início da semana. Urgentes são alocados antes de
  todos os outros (primeira escolha dos picos) e ganham +1 bloco.
- Difícil (dificuldade >= 4) também ganha +1 bloco.
"""

import math
from datetime import date

from app.core.config import settings
from app.modules.agentes.contratos import Material

DIFICIL = 4


def dias_ate_prazo(m: Material, hoje: date) -> int | None:
    return (m.prazo - hoje).days if m.prazo else None


def urgente(m: Material, hoje: date) -> bool:
    d = dias_ate_prazo(m, hoje)
    return d is not None and d <= settings.analysis_dias_urgencia


def ordenar(materiais: list[Material], hoje: date) -> list[Material]:
    def chave(m: Material):
        d = dias_ate_prazo(m, hoje)
        return (d is None, d if d is not None else 0, -m.dificuldade, m.id)

    return sorted(materiais, key=chave)


def blocos(m: Material, foco_min: int, hoje: date) -> int:
    base = math.ceil(m.horas_estimadas * 60 / foco_min)
    return base + int(urgente(m, hoje)) + int(m.dificuldade >= DIFICIL)
