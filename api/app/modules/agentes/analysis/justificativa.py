"""Técnica + justificativa de cada material, pelo LLM, citando a base de artigos.

O LLM só escreve texto: dia, horário, carga e pausa já vêm da alocação e não mudam. Uma chamada por
material (todos os blocos daquele material recebem a mesma técnica e justificativa):

1. Busca na base (ChromaDB) com uma consulta montada a partir do material e da carga; trechos longe demais
   (acima do corte do porteiro) não entram.
2. O modelo devolve JSON de esquema fixo {tecnica, justificativa} (structured output do Ollama).
3. O verificador de citações (rag/verificador.py) tira [Fonte: ...] de artigos que o modelo não recebeu.
4. Qualquer falha (Ollama fora, JSON inválido, campo a mais, nenhuma citação válida) mantém a técnica
   padrão da tabela (tecnicas.py): a grade nunca deixa de sair por causa do LLM.

Chamado só depois que o Validation aprova a grade, para o loop de reajuste não gastar chamadas ao LLM.
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from langchain_core.documents import Document
from pydantic import Field, ValidationError

from app.modules.agentes.contratos import BlocoEstudo, ContextoEstudante, Contrato, Material, PropostaGrade, esquema
from app.modules.rag.fontes import formatar_trechos, nome_fonte
from app.modules.rag.verificador import verificar

from .janelas import minutos, por_dia, sobrepoe
from .pomodoro import ritmo

logger = logging.getLogger("studybuddy.agentes")

K_TRECHOS = 4
_ARTIGO = re.compile(r"artigo_(\d{2})")


class JustificativaLLM(Contrato):
    tecnica: str = Field(min_length=3, max_length=80)
    justificativa: str = Field(min_length=20, max_length=700)


ESQUEMA_JUSTIFICATIVA = esquema(JustificativaLLM)

PROMPT_JUSTIFICATIVA = """Você é o Analysis Agent de um mentor de estudos baseado em artigos científicos.
A grade da semana JÁ ESTÁ MONTADA (dias, horários e pausas não mudam). Sua tarefa é só escolher a técnica
de estudo para este material e justificar a escolha com os fragmentos abaixo.

MATERIAL: {titulo} ({disciplina})
CARGA COGNITIVA: {carga}
TÉCNICAS ADEQUADAS PARA ESTA CARGA: {tecnicas}
HORÁRIOS NA GRADE: {horarios}
RITMO: blocos de {foco} min de foco com {pausa} min de pausa (estado do estudante: {estado})

FRAGMENTOS DA BASE:
{trechos}

Responda em JSON:
- "tecnica": nome curto, em português e com inicial maiúscula, de UMA das técnicas adequadas acima que
  apareça nos fragmentos (ex.: "Prática intercalada", "Flashcards com repetição espaçada").
- "justificativa": 1 a 3 frases em português explicando por que a técnica e esse horário servem para este
  material, usando SÓ o que está nos fragmentos. Atribua cada ideia ao fragmento de onde ela saiu. Cada frase termina com a fonte no formato
  [Fonte: artigo_NN_nome.txt], copiando o nome do arquivo do cabeçalho do fragmento.
Não invente artigos nem dados que não estejam nos fragmentos."""

# A busca e o leque de técnicas dependem da carga: sem isso, o modelo chegou a sugerir flashcards para
# uma lista de exercícios de Cálculo (alta carga), porque a busca genérica não trazia active recall.
CONSULTA = {
    "alta": "prática de recuperação active recall e prática intercalada para resolver exercícios de {disciplina}",
    "baixa": "repetição espaçada e flashcards para revisão leve de {disciplina}",
}
TECNICAS_ADEQUADAS = {
    "alta": "active recall (resolver sem consultar), prática intercalada, técnica Feynman, Pomodoro, deep work",
    "baixa": "flashcards com repetição espaçada, leitura com resumo, revisão espaçada",
}


@dataclass
class Relato:
    """O que aconteceu na justificativa de um material (vai para o rastro e para a comparação de modelos)."""

    material_id: str
    usou_llm: bool = False
    motivo_padrao: str = ""             # por que ficou a técnica padrão, quando ficou
    citadas: list[str] = field(default_factory=list)
    removidas: list[str] = field(default_factory=list)
    segundos: float = 0.0

    def para_dict(self) -> dict:
        return asdict(self)


def _horarios(blocos: list[BlocoEstudo], ctx: ContextoEstudante) -> str:
    picos, vales = por_dia(ctx.picos), por_dia(ctx.vales)

    def tipo(b: BlocoEstudo) -> str:
        iv = (minutos(b.inicio), minutos(b.fim))
        return "pico" if sobrepoe(iv, picos.get(b.dia, [])) else "vale" if sobrepoe(iv, vales.get(b.dia, [])) else "neutro"

    dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    return ", ".join(f"{dias[b.dia.weekday()]} {b.inicio:%H:%M} ({tipo(b)})" for b in blocos)


def _buscar_padrao(consulta: str) -> list[Document]:
    from app.modules.rag import repository

    return [d for d, dist in repository.buscar(consulta, k=K_TRECHOS) if not repository.barrada(dist)]


def _chat_padrao():
    from app.modules.rag import llm

    return llm.analysis()


def consulta(m: Material) -> str:
    return CONSULTA[m.carga].format(disciplina=m.disciplina)


def montar_prompt(m: Material, blocos: list[BlocoEstudo], ctx: ContextoEstudante, trechos: list[Document],
                  estado: str = "normal") -> str:
    """O prompt exato que vai ao LLM (também usado pela comparação de modelos da [3.0])."""
    b0 = blocos[0]
    return PROMPT_JUSTIFICATIVA.format(
        titulo=m.titulo, disciplina=m.disciplina, carga=m.carga, tecnicas=TECNICAS_ADEQUADAS[m.carga],
        horarios=_horarios(blocos, ctx), foco=b0.foco_min, pausa=b0.pausa_min, estado=estado,
        trechos=formatar_trechos(trechos))


def estado_da_proposta(proposta: PropostaGrade, ctx: ContextoEstudante) -> str:
    return ritmo(ctx.indice_capacidade, reducao_danos=proposta.modo == "reducao_danos").estado.replace("_", " ")


def fontes_citadas(citadas: list[str], trechos: list[Document]) -> list[str]:
    """["artigo_03"] -> ["artigo_03_interleaving_rohwer.txt"], com o nome do arquivo dos trechos recebidos."""
    por_numero = {m_.group(1): nome_fonte(d.metadata.get("source", ""))
                  for d in trechos if (m_ := _ARTIGO.search(nome_fonte(d.metadata.get("source", ""))))}
    return [por_numero[c.removeprefix("artigo_")] for c in citadas if c.removeprefix("artigo_") in por_numero]


def justificar_material(
    m: Material, blocos: list[BlocoEstudo], ctx: ContextoEstudante, *, chat, buscar: Callable[[str], list[Document]],
    estado: str = "normal",
) -> tuple[list[BlocoEstudo], Relato]:
    relato = Relato(m.id)
    inicio = time.perf_counter()
    try:
        trechos = buscar(consulta(m))
        if not trechos:
            relato.motivo_padrao = "nenhum trecho da base perto o bastante"
            return blocos, relato
        prompt = montar_prompt(m, blocos, ctx, trechos, estado)
        saida = JustificativaLLM.model_validate_json(chat.invoke(prompt).content)
    except ValidationError as exc:
        relato.motivo_padrao = f"JSON fora do esquema: {exc.error_count()} erro(s)"
        logger.warning("Analysis: justificativa de %s fora do esquema; ficou a técnica padrão", m.id)
        return blocos, relato
    except Exception as exc:  # Ollama fora do ar, timeout, índice ausente: a grade sai com a técnica padrão
        relato.motivo_padrao = f"falha ao chamar o LLM: {type(exc).__name__}"
        logger.warning("Analysis: justificativa de %s falhou (%s); ficou a técnica padrão", m.id, exc)
        return blocos, relato
    finally:
        relato.segundos = round(time.perf_counter() - inicio, 2)

    texto, v = verificar(saida.justificativa, trechos)
    relato.removidas = v.fora_do_contexto
    if not v.citadas:
        relato.motivo_padrao = "nenhuma citação válida"
        return blocos, relato

    fontes = fontes_citadas(v.citadas, trechos)
    relato.usou_llm, relato.citadas = True, fontes
    novos = [b.model_copy(update={"tecnica": saida.tecnica.strip(), "justificativa": texto, "fontes": fontes})
             for b in blocos]
    return novos, relato


def justificar(
    proposta: PropostaGrade, ctx: ContextoEstudante, *, chat=None, buscar: Callable[[str], list[Document]] | None = None,
) -> tuple[PropostaGrade, list[Relato]]:
    """Proposta com técnica e justificativa do LLM em cada bloco + um relato por material.
    `chat` e `buscar` podem ser trocados (testes e comparação de modelos)."""
    chat = chat or _chat_padrao()
    buscar = buscar or _buscar_padrao
    materiais = {m.id: m for m in ctx.materiais}
    estado = estado_da_proposta(proposta, ctx)
    trocados: dict[str, BlocoEstudo] = {}
    relatos = []
    for mid in dict.fromkeys(b.material_id for b in proposta.blocos):
        if mid not in materiais:
            continue
        blocos = [b for b in proposta.blocos if b.material_id == mid]
        novos, relato = justificar_material(materiais[mid], blocos, ctx, chat=chat, buscar=buscar,
                                             estado=estado)
        trocados.update({b.id: b for b in novos})
        relatos.append(relato)
    return proposta.model_copy(update={"blocos": [trocados.get(b.id, b) for b in proposta.blocos]}), relatos
