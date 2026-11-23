"""Agente Communication: escolhe o tom pelo check-in e escreve uma mensagem sobre a grade aprovada.

Recebe somente a PropostaGrade aprovada, o CheckIn e as Evidencia citáveis. O tom sai de
uma tabela ordenada de regras; a grade nunca é alterada pelo agente.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.rag import llm

from .communication_schemas import CheckIn, Evidencia, MensagemFinal, PropostaGrade, Tom
from .prompts_communication import INSTRUCOES_TOM, PROMPT_SISTEMA, PROMPT_USUARIO

ACOLHEDOR = "acolhedor"
EQUILIBRADO = "equilibrado"
DESAFIADOR = "desafiador"
TOM_PADRAO = EQUILIBRADO

REGRAS_TOM = (
    (ACOLHEDOR, lambda c: c.fadiga >= 4 or c.estresse >= 4 or c.humor <= 2),
    (DESAFIADOR, lambda c: c.humor >= 4 and c.sono >= 4 and c.fadiga <= 2 and c.estresse <= 2),
)


def escolher_tom(checkin: CheckIn) -> Tom:
    for tom, condicao in REGRAS_TOM:
        if condicao(checkin):
            return tom
    return TOM_PADRAO


def formatar_grade(grade: PropostaGrade) -> str:
    linhas = []
    for bloco in grade.blocos:
        linha = f"- {bloco.dia}, {bloco.inicio}-{bloco.fim}: {bloco.disciplina}"
        if bloco.material is not None:
            linha += f" (material: {bloco.material})"
        linhas.append(linha)
    return "\n".join(linhas)


def links_da_grade(grade: PropostaGrade) -> list[str]:
    return list(dict.fromkeys(b.material for b in grade.blocos if b.material))


def formatar_checkin(checkin: CheckIn) -> str:
    return (
        f"humor {checkin.humor}/5, estresse {checkin.estresse}/5, "
        f"sono {checkin.sono}/5, fadiga {checkin.fadiga}/5"
    )


def formatar_evidencias(evidencias: list[Evidencia]) -> str:
    return "\n".join(f"- [Fonte: {e.fonte}] {e.trecho}" for e in evidencias)


def montar_prompt(grade: PropostaGrade, checkin: CheckIn, tom: str, evidencias: list[Evidencia]) -> str:
    return PROMPT_USUARIO.format(
        tom=tom,
        instrucao_tom=INSTRUCOES_TOM[tom],
        grade=formatar_grade(grade),
        checkin=formatar_checkin(checkin),
        evidencias=formatar_evidencias(evidencias),
    )


def montar_mensagem(grade: PropostaGrade, checkin: CheckIn, evidencias: list[Evidencia]) -> MensagemFinal:
    tom = escolher_tom(checkin)
    pedido = montar_prompt(grade, checkin, tom, evidencias)
    conteudo = llm.gerador().invoke([SystemMessage(PROMPT_SISTEMA), HumanMessage(pedido)]).content
    return MensagemFinal(tom=tom, markdown=conteudo.strip(), links=links_da_grade(grade))
