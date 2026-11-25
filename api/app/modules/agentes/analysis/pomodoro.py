"""[3.2] Pomodoro adaptativo: tamanho do bloco e da pausa pelo índice de capacidade do check-in.

| Índice de capacidade               | Estado        | Foco | Pausa |
| :--------------------------------- | :------------ | ---: | ----: |
| >= ANALYSIS_INDICE_ALTO (0,7)      | energia alta  | 50   | 10    |
| entre os dois limiares             | normal        | 25   | 5     |
| <  ANALYSIS_INDICE_BAIXO (0,4)     | fadiga        | 25   | 10    |
| rota reducao_danos (Maestro)       | dia leve      | 25   | ANALYSIS_REDUCAO_PAUSA_MIN (15) |

Com energia alta, blocos longos aproveitam o foco profundo [Fonte: artigo_06_deep_work_newport.txt];
no normal fica o ciclo clássico 25/5 [Fonte: artigo_10_pomodoro_cirillo.txt]; com fadiga o foco continua
curto e a pausa cresce, porque o autocontrole se esgota mais rápido [Fonte: artigo_14_willpower_depletion_baumeister.txt].
Os limiares ficam em config.py e podem ser trocados por variável de ambiente.
"""

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Ritmo:
    estado: str
    foco_min: int
    pausa_min: int


def ritmo(indice_capacidade: float, *, reducao_danos: bool = False) -> Ritmo:
    if reducao_danos:
        return Ritmo("reducao_danos", 25, settings.analysis_reducao_pausa_min)
    if indice_capacidade >= settings.analysis_indice_alto:
        return Ritmo("energia_alta", 50, 10)
    if indice_capacidade < settings.analysis_indice_baixo:
        return Ritmo("fadiga", 25, 10)
    return Ritmo("normal", 25, 5)
