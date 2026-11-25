"""Regras que toda PropostaGrade do Analysis precisa cumprir. Só regras, sem LLM.

Servem aos testes e às métricas ([3.4]) sem depender do Validation (épico [4]). Cada função devolve
os ids dos blocos que violam a regra.
"""

from app.modules.agentes.contratos import ContextoEstudante, PropostaGrade

from .janelas import contido, disponivel, minutos, por_dia, sobrepoe


def _iv(b) -> tuple[int, int]:
    return minutos(b.inicio), minutos(b.fim)


def alta_em_vale(p: PropostaGrade, ctx: ContextoEstudante) -> list[str]:
    vales = por_dia(ctx.vales)
    return [b.id for b in p.blocos if b.carga == "alta" and sobrepoe(_iv(b), vales.get(b.dia, []))]


def fora_dos_livres(p: PropostaGrade, ctx: ContextoEstudante) -> list[str]:
    """Bloco (foco + pausa) fora do tempo disponível: livres - ocupados - sono - refeições."""
    disp = disponivel(ctx)
    return [b.id for b in p.blocos
            if not contido((minutos(b.inicio), minutos(b.fim) + b.pausa_min), disp.get(b.dia, []))]


def apos_prazo(p: PropostaGrade, ctx: ContextoEstudante) -> list[str]:
    prazos = {m.id: m.prazo for m in ctx.materiais if m.prazo}
    return [b.id for b in p.blocos if b.material_id in prazos and b.dia >= prazos[b.material_id]]


def sobrepostos(p: PropostaGrade) -> list[str]:
    ids = []
    for i, b in enumerate(p.blocos):
        outros = [(minutos(o.inicio), minutos(o.fim) + o.pausa_min) for o in p.blocos[:i] + p.blocos[i + 1:]
                  if o.dia == b.dia]
        if sobrepoe((minutos(b.inicio), minutos(b.fim) + b.pausa_min), outros):
            ids.append(b.id)
    return ids


def todas(p: PropostaGrade, ctx: ContextoEstudante) -> dict[str, list[str]]:
    """Só as regras violadas, com os blocos de cada uma. Vazio = proposta limpa."""
    achados = {"alta_em_vale": alta_em_vale(p, ctx), "fora_dos_livres": fora_dos_livres(p, ctx),
               "apos_prazo": apos_prazo(p, ctx), "sobrepostos": sobrepostos(p)}
    return {k: v for k, v in achados.items() if v}
