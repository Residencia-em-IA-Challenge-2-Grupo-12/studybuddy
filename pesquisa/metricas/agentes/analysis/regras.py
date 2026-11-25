"""Regras das fixtures: um substituto mínimo do Validation (épico [4]) só para medir o Analysis.

Gera as mesmas `Violacao` do contrato da [0.1] a partir do contexto, sem chamar o agente de ninguém:
- CONFLITO_AGENDA: o bloco (foco + pausa) cruza um compromisso ou sai dos horários livres;
- INTEGRIDADE_CIRCADIANA: cruza o sono ou uma refeição, ou é de alta carga e cai num vale;
- SOBRECARGA: o dia passa de `limite_dia_min` de foco (só quando o cenário dá um limite).
"""

from collections import defaultdict

from app.modules.agentes.analysis.janelas import contido, minutos, por_dia, sobrepoe
from app.modules.agentes.contratos import ContextoEstudante, PropostaGrade, Violacao


def detectar(p: PropostaGrade, ctx: ContextoEstudante, limite_dia_min: int | None = None) -> list[Violacao]:
    ocupados, livres, vales = por_dia(ctx.ocupados), por_dia(ctx.livres), por_dia(ctx.vales)
    corpo = por_dia([*ctx.sono, *ctx.refeicoes])
    achadas = []
    for b in p.blocos:
        foco, tudo = (minutos(b.inicio), minutos(b.fim)), (minutos(b.inicio), minutos(b.fim) + b.pausa_min)
        if sobrepoe(tudo, ocupados.get(b.dia, [])):
            regra, msg = "CONFLITO_AGENDA", "cruza um compromisso"
        elif sobrepoe(tudo, corpo.get(b.dia, [])):
            regra, msg = "INTEGRIDADE_CIRCADIANA", "cruza o sono ou uma refeição"
        elif b.carga == "alta" and sobrepoe(foco, vales.get(b.dia, [])):
            regra, msg = "INTEGRIDADE_CIRCADIANA", "alta carga no vale"
        elif not contido(tudo, livres.get(b.dia, [])):
            regra, msg = "CONFLITO_AGENDA", "fora dos horários livres"
        else:
            continue
        achadas.append(Violacao(regra=regra, dia=b.dia, bloco_id=b.id, mensagem=f"bloco {b.id}: {msg}"))
    if limite_dia_min is not None:
        foco_dia: dict = defaultdict(int)
        for b in p.blocos:
            foco_dia[b.dia] += b.foco_min
        for dia, total in sorted(foco_dia.items()):
            if total > limite_dia_min:
                achadas.append(Violacao(regra="SOBRECARGA", dia=dia, mensagem=f"{total} min de foco",
                                        excesso_min=total - limite_dia_min))
    return achadas
