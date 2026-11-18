"""Agente Planejador: transforma evidências em orientação concreta para ESTE estudante.

1. Escopo: busca a pergunta (k=5) e aplica o porteiro. Barrada -> recusa sem LLM.
2. Evidências: além da pergunta, busca as consultas da Triagem (k=3 cada) e junta os trechos novos,
   sem repetir e sem passar de MAX_TRECHOS. Assim a resposta cobre aspectos que a pergunta crua não achava.
3. Resposta: o formato depende da decisão da Triagem.
   - "plano": passos concretos, ordenados, dentro das restrições ditas, cada um com a fonte;
   - "explicacao": o prompt do pipeline clássico, com o diagnóstico como contexto extra.
O prompt de sistema é o mesmo do notebook (RAG_SYSTEM_PROMPT): não inventar, recusar, citar a fonte.
"""

from dataclasses import dataclass

from langchain_core.documents import Document

from app.modules.rag import repository
from app.modules.rag.classico import gerar
from app.modules.rag.fontes import formatar_trechos

from .triagem import PLANO, Diagnostico

K_CONSULTA = 3    # trechos por consulta da Triagem
MAX_TRECHOS = 8   # teto do contexto (k=5 da pergunta + até 3 novos)

PLANO_USER_PROMPT = """CONTEXTO RECUPERADO:
{context}

PERGUNTA DO USUÁRIO:
{question}

DIAGNÓSTICO DO ESTUDANTE (feito pelo Agente de Triagem):
{diagnostico}

Monte um PLANO DE AÇÃO para este estudante:
- Comece com uma frase que responde diretamente à pergunta.
- Depois, liste passos concretos e numerados (o que fazer, quando, por quanto tempo, como), na ordem em que ele deve aplicar.
- Monte o plano DENTRO das restrições do diagnóstico: use o tempo e o horário que o estudante disse ter e não
  proponha nada que exija mais tempo do que isso. Se um fragmento recomendar outro horário ou mais tempo,
  mencione como sugestão, sem trocar o plano.
- Cada passo deve vir dos fragmentos e terminar com o nome do arquivo de onde saiu, no formato
  [Fonte: artigo_NN_nome.txt] (copie o nome que aparece no cabeçalho do fragmento, nunca "Fragmento #N").
- Se alguma parte da pergunta não estiver nos fragmentos, diga isso nessa parte, sem inventar.

PLANO FUNDAMENTADO:"""

EXPLICACAO_USER_PROMPT = """CONTEXTO RECUPERADO:
{context}

PERGUNTA DO USUÁRIO:
{question}

DIAGNÓSTICO DO ESTUDANTE (feito pelo Agente de Triagem):
{diagnostico}

RESPOSTA FUNDAMENTADA:"""


@dataclass
class Escopo:
    trechos: list[Document]
    d1: float
    barrada: bool


def _chave(d: Document):
    return (d.metadata.get("source"), d.metadata.get("chunk_id"))


def juntar_trechos(base: list[Document], extras: list[tuple[Document, float]], teto: int = MAX_TRECHOS) -> list[Document]:
    """Trechos da pergunta + os mais próximos das consultas que ainda não estão lá, até o teto."""
    vistos = {_chave(d) for d in base}
    novos: list[tuple[Document, float]] = []
    for d, dist in sorted(extras, key=lambda x: x[1]):
        if _chave(d) not in vistos:
            vistos.add(_chave(d))
            novos.append((d, dist))
    return base + [d for d, _ in novos][: max(0, teto - len(base))]


class AgentePlanejador:
    nome = "Planejador"

    def verificar_escopo(self, pergunta: str) -> Escopo:
        pares = repository.buscar(pergunta)
        d1 = pares[0][1] if pares else float("inf")
        return Escopo([d for d, _ in pares], d1, repository.barrada(d1))

    def reunir_evidencias(self, trechos: list[Document], diag: Diagnostico) -> list[Document]:
        extras = []
        for consulta in diag.consultas:
            # trechos longe demais da base (acima do corte do porteiro) não entram
            extras += [(d, dist) for d, dist in repository.buscar(consulta, k=K_CONSULTA) if not repository.barrada(dist)]
        return juntar_trechos(trechos, extras)

    def responder(self, pergunta: str, trechos: list[Document], diag: Diagnostico) -> str:
        modelo = PLANO_USER_PROMPT if diag.tipo_resposta == PLANO else EXPLICACAO_USER_PROMPT
        return gerar(formatar_trechos(trechos), pergunta, modelo, diagnostico=diag.como_texto())
