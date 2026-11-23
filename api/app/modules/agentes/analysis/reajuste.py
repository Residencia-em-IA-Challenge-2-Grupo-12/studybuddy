"""[3.3] Reajuste a partir das violações do Validation. Determinístico, sem LLM.

Recebe a proposta reprovada + as `Violacao` e refaz SÓ o que foi apontado. Os outros blocos ficam
exatamente como estavam (mesmo id, dia e horário).

- CONFLITO_AGENDA / INTEGRIDADE_CIRCADIANA: tira o bloco apontado e tenta pô-lo de novo com a mesma
  `alocar`, só no tempo que sobrou. O horário de onde ele saiu fica proibido, porque o Validation pode
  enxergar um compromisso ou uma janela (ex.: higiene do sono) que o contexto não mostra.
  Sem `bloco_id`, saem os blocos daquele dia que os invariantes acusam.
- SOBRECARGA: corta do dia apontado, começando pelos blocos de menor prioridade, até somar `excesso_min`
  de foco. Os cortados só podem ir para outros dias.
- Nenhum dia passa a ter mais blocos que o limite: o maior dia da proposta original ou, havendo
  SOBRECARGA, o que sobrou no dia cortado. Assim o reajuste não cria uma sobrecarga nova.
- O que não couber vai para `fora_da_grade` (a proposta sai com carga reduzida e diz o que ficou de fora).
  Os blocos novos ganham o id "r<iteracao>-NN" e a `iteracao` sobe 1.
"""

from collections import Counter, defaultdict
from datetime import date

from app.modules.agentes.contratos import BlocoEstudo, ContextoEstudante, PropostaGrade, Violacao

from . import invariantes, prioridade
from .alocacao import alocar
from .janelas import Intervalo, fatias, minutos, recortar

DIA_INTEIRO: Intervalo = (0, 24 * 60)


def _ocupa(b: BlocoEstudo) -> Intervalo:
    return minutos(b.inicio), minutos(b.fim) + b.pausa_min


def _apontados_no_dia(p: PropostaGrade, ctx: ContextoEstudante, dia: date) -> set[str]:
    acusados = {i for ids in invariantes.todas(p, ctx).values() for i in ids}
    return {b.id for b in p.blocos if b.dia == dia and b.id in acusados}


def _cortar_excesso(blocos_do_dia: list[BlocoEstudo], excesso_min: int, ordem: dict[str, int]) -> set[str]:
    """Ids a cortar: menor prioridade primeiro; no mesmo material, o bloco mais tarde do dia."""
    cortados, soma = set(), 0
    for b in sorted(blocos_do_dia, key=lambda b: (ordem.get(b.material_id, len(ordem)), b.inicio), reverse=True):
        if soma >= excesso_min:
            break
        cortados.add(b.id)
        soma += b.foco_min
    return cortados


def reajustar(proposta: PropostaGrade, violacoes: list[Violacao], ctx: ContextoEstudante) -> PropostaGrade:
    hoje = ctx.semana_inicio
    ordenados = prioridade.ordenar(ctx.materiais, hoje)
    ordem = {m.id: i for i, m in enumerate(ordenados)}  # 0 = mais prioritário
    por_id = {b.id: b for b in proposta.blocos}

    remover: set[str] = set()
    dias_fechados: set[date] = set()  # dias com SOBRECARGA: nada novo entra neles
    for v in violacoes:
        if v.regra == "SOBRECARGA":
            do_dia = [b for b in proposta.blocos if b.dia == v.dia and b.id not in remover]
            excesso = v.excesso_min if v.excesso_min is not None else max((b.foco_min for b in do_dia), default=0)
            remover |= _cortar_excesso(do_dia, excesso, ordem)
            dias_fechados.add(v.dia)
        elif v.bloco_id in por_id:
            remover.add(v.bloco_id)
        else:
            remover |= _apontados_no_dia(proposta, ctx, v.dia)

    mantidos = [b for b in proposta.blocos if b.id not in remover]
    saindo = [por_id[i] for i in sorted(remover)]

    carga = Counter(b.dia for b in mantidos)
    limite = max(Counter(b.dia for b in proposta.blocos).values(), default=0)
    if dias_fechados:
        limite = min([limite, *(carga[d] for d in dias_fechados)])

    cortes: dict[date, list[Intervalo]] = defaultdict(list)
    for b in [*mantidos, *saindo]:
        cortes[b.dia].append(_ocupa(b))  # o que fica não se mexe; de onde saiu, não volta
    for d in dias_fechados:
        cortes[d].append(DIA_INTEIRO)
    sobra = recortar(fatias(ctx), cortes)

    iteracao = proposta.iteracao + 1
    novos: list[BlocoEstudo] = []
    nao_couberam: list[str] = []
    materiais = {m.id: m for m in ctx.materiais}
    # um ritmo por vez (numa proposta normal há um só): cada bloco volta com o foco e a pausa que tinha
    for (foco, pausa), grupo in _por_ritmo(saindo).items():
        falta = Counter(b.material_id for b in grupo)
        lista = [m for m in ordenados if m.id in falta and m.id in materiais]
        nao_couberam += [mid for mid in falta if mid not in materiais]  # material sumiu do contexto
        blocos, fora = alocar(
            ctx, foco_min=foco, pausa_min=pausa, materiais=lista, necessidade=lambda m: falta[m.id],
            urgentes={m.id for m in lista if prioridade.urgente(m, hoje)},
            max_blocos_dia=limite, fatias_base=sobra, carga_inicial=carga,
        )
        novos += blocos
        nao_couberam += fora
        for b in blocos:  # o próximo ritmo não pode usar o que este acabou de ocupar
            carga[b.dia] += 1
            cortes[b.dia].append(_ocupa(b))
        sobra = recortar(fatias(ctx), cortes)

    novos = [b.model_copy(update={"id": f"r{iteracao}-{i:02d}"})
             for i, b in enumerate(sorted(novos, key=lambda b: (b.dia, b.inicio)), start=1)]
    fora_da_grade = list(dict.fromkeys([*proposta.fora_da_grade, *nao_couberam]))
    return proposta.model_copy(update={
        "blocos": sorted([*mantidos, *novos], key=lambda b: (b.dia, b.inicio)),
        "fora_da_grade": fora_da_grade,
        "iteracao": iteracao,
    })


def _por_ritmo(blocos: list[BlocoEstudo]) -> dict[tuple[int, int], list[BlocoEstudo]]:
    grupos: dict[tuple[int, int], list[BlocoEstudo]] = defaultdict(list)
    for b in blocos:
        grupos[b.foco_min, b.pausa_min].append(b)
    return dict(grupos)
