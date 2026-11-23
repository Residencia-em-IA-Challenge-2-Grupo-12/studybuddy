"""[3.1] Alocação por carga cognitiva: heurística determinística, sem LLM.

1. O tempo disponível (livres - ocupados - sono - refeições) é recortado em fatias de pico, vale e neutro.
2. Cada material precisa de ceil(horas*60 / foco_min) blocos. Cada bloco ocupa foco + pausa dentro de uma fatia.
3. Preferência de fatia pela carga:
   - alta:  pico -> neutro  (NUNCA vale)
   - baixa: vale -> neutro -> pico (usa a sobra do pico)
4. Os materiais entram intercalados (um bloco de cada por rodada, na ordem de prioridade). Na mesma
   preferência, ganha o dia com menos blocos daquele material: espalha a matéria pela semana
   (prática intercalada e repetição espaçada) em vez de empilhar tudo na segunda-feira.
5. Com prazo, o bloco só entra em dia ANTES do prazo. O que não couber vai para fora_da_grade.
"""

import math
from collections import Counter
from collections.abc import Callable

from app.modules.agentes.contratos import BlocoEstudo, CargaCognitiva, ContextoEstudante, Material

from .janelas import Fatia, fatias, hora
from .tecnicas import TECNICA_PADRAO

PREFERENCIA: dict[CargaCognitiva, tuple[str, ...]] = {
    "alta": ("pico", "neutro"),
    "baixa": ("vale", "neutro", "pico"),
}


def blocos_necessarios(m: Material, foco_min: int) -> int:
    return math.ceil(m.horas_estimadas * 60 / foco_min)


def alocar(
    ctx: ContextoEstudante,
    *,
    foco_min: int = 25,
    pausa_min: int = 5,
    ordem: Callable[[list[Material]], list[Material]] | None = None,
    necessidade: Callable[[Material], int] | None = None,
    fatias_base: list[Fatia] | None = None,
) -> tuple[list[BlocoEstudo], list[str]]:
    """Devolve (blocos ordenados por dia e horário, ids dos materiais que não couberam inteiros).

    `ordem` e `necessidade` são os ganchos da prioridade ([3.2]); `fatias_base` permite realocar
    só no que sobrou de uma proposta anterior ([3.3]).
    """
    materiais = (ordem or (lambda ms: sorted(ms, key=lambda m: m.id)))(list(ctx.materiais))
    faltam = {m.id: (necessidade or (lambda m: blocos_necessarios(m, foco_min)))(m) for m in materiais}
    livres = [Fatia(f.dia, f.ini, f.fim, f.tipo) for f in (fatias_base if fatias_base is not None else fatias(ctx))]
    por_dia: Counter = Counter()  # (material_id, dia) -> blocos já postos
    colocados: list[tuple[Fatia, int, Material]] = []
    precisa = foco_min + pausa_min

    pendentes = [m for m in materiais if faltam[m.id] > 0]
    while pendentes:
        for m in list(pendentes):
            candidatas = [
                f for f in livres
                if f.tipo in PREFERENCIA[m.carga] and f.livre_min >= precisa and (m.prazo is None or f.dia < m.prazo)
            ]
            if not candidatas:
                pendentes.remove(m)  # não cabe mais nada: o resto fica fora da grade
                continue
            f = min(candidatas, key=lambda f: (PREFERENCIA[m.carga].index(f.tipo), por_dia[m.id, f.dia], f.dia, f.ini))
            colocados.append((Fatia(f.dia, f.ini, f.ini + foco_min, f.tipo), pausa_min, m))
            f.ini += precisa
            por_dia[m.id, f.dia] += 1
            faltam[m.id] -= 1
            if faltam[m.id] == 0:
                pendentes.remove(m)

    blocos = []
    for i, (f, pausa, m) in enumerate(sorted(colocados, key=lambda c: (c[0].dia, c[0].ini)), start=1):
        tecnica, justificativa, fontes = TECNICA_PADRAO[m.carga]
        blocos.append(BlocoEstudo(
            id=f"b{i:02d}", dia=f.dia, inicio=hora(f.ini), fim=hora(f.fim), disciplina=m.disciplina,
            material_id=m.id, carga=m.carga, tecnica=tecnica, foco_min=foco_min, pausa_min=pausa,
            justificativa=justificativa, fontes=list(fontes),
        ))
    return blocos, [m.id for m in materiais if faltam[m.id] > 0]
