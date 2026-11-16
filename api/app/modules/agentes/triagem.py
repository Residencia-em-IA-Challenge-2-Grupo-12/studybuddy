"""Agente de Triagem: entende o estudante antes de qualquer resposta.

Lê a mensagem e devolve um diagnóstico estruturado (JSON de esquema fixo):
  - qual é o problema real (procrastinação, sono, overplanning, priorização...);
  - o objetivo e as restrições ditas pelo estudante (horas livres, prazo, rotina);
  - DECIDE o tipo de resposta: "plano" (o estudante quer saber o que fazer) ou "explicacao"
    (quer entender por que algo acontece ou como uma técnica funciona);
  - escreve consultas para a base no vocabulário dos artigos, que o Planejador usa além da pergunta.

A Triagem não responde nem consulta a base: só diagnostica.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from app.modules.rag import llm

logger = logging.getLogger("studybuddy.agentes")

PLANO, EXPLICACAO = "plano", "explicacao"
MAX_CONSULTAS = 3

PROBLEMAS = [
    "procrastinacao", "sono_e_rotina", "foco_e_distracao", "planejamento_excessivo",
    "priorizacao_de_conteudo", "memoria_e_revisao", "habito_e_motivacao", "conciliar_trabalho_e_estudo", "outro",
]

PROMPT_TRIAGEM = """Você é o Agente de Triagem de um mentor de estudos baseado em artigos científicos.
Não responda à pergunta. Sua tarefa é DIAGNOSTICAR o estudante a partir da mensagem dele.

1. "problema_principal": escolha UM entre {problemas}.
2. "objetivo": o que o estudante quer alcançar, em uma frase curta.
3. "restricoes": copie só o que o estudante DISSE (não invente). Quando ele não disse, deixe a string vazia ""
   (não escreva "não especificado" nem "não mencionado").
   - "tempo_disponivel": horas livres, jornada de trabalho, dias disponíveis.
   - "prazo": data da prova ou prazo.
   - "contexto": outras condições ditas (ex.: trabalha em regime CLT, faz estágio, tem ansiedade).
4. "tipo_resposta":
   - "plano" se o estudante quer saber O QUE FAZER (rotina, passos, como organizar, como começar).
   - "explicacao" se quer ENTENDER algo (por que acontece, o que é, como funciona uma técnica).
5. "consultas": de 1 a {max_consultas} buscas curtas para uma base de artigos sobre técnicas de estudo,
   produtividade e comportamento. Escreva com termos técnicos que os artigos usariam (ex.: "repetição
   espaçada", "intenções de implementação", "resíduo de atenção", "consolidação da memória no sono"),
   cobrindo aspectos diferentes da mensagem.

MENSAGEM DO ESTUDANTE:
{pergunta}"""

ESQUEMA_DIAGNOSTICO = {
    "type": "object",
    "properties": {
        "problema_principal": {"type": "string", "enum": PROBLEMAS},
        "objetivo": {"type": "string"},
        "restricoes": {
            "type": "object",
            "properties": {"tempo_disponivel": {"type": "string"}, "prazo": {"type": "string"},
                           "contexto": {"type": "string"}},
            "required": ["tempo_disponivel", "prazo", "contexto"],
        },
        "tipo_resposta": {"type": "string", "enum": [PLANO, EXPLICACAO]},
        "consultas": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["problema_principal", "objetivo", "restricoes", "tipo_resposta", "consultas"],
}


_NAO_DITO = re.compile(r"^(n[aã]o (especificad|mencionad|informad|dit|se aplica)\w*|nenhum\w*|n/?a|-|desconhecid\w*)\.?$")


def _vazio(valor: str) -> bool:
    return not valor.strip() or bool(_NAO_DITO.match(valor.strip().lower()))


@dataclass
class Diagnostico:
    problema_principal: str = "outro"
    objetivo: str = ""
    restricoes: dict = field(default_factory=dict)
    tipo_resposta: str = EXPLICACAO
    consultas: list[str] = field(default_factory=list)
    falhou: bool = False

    def restricoes_ditas(self) -> dict:
        """Só o que o estudante disse. O modelo às vezes preenche "não especificado" em vez de deixar vazio."""
        return {k: v.strip() for k, v in self.restricoes.items() if v and not _vazio(v)}

    def como_texto(self) -> str:
        """Bloco que o Planejador recebe no prompt."""
        linhas = [f"- Problema principal: {self.problema_principal.replace('_', ' ')}"]
        if self.objetivo:
            linhas.append(f"- Objetivo: {self.objetivo}")
        rotulos = {"tempo_disponivel": "Tempo disponível", "prazo": "Prazo", "contexto": "Contexto"}
        for chave, valor in self.restricoes_ditas().items():
            linhas.append(f"- {rotulos.get(chave, chave)}: {valor}")
        return "\n".join(linhas)

    def para_dict(self) -> dict:
        return asdict(self)


def interpretar(bruto: str) -> Diagnostico:
    """JSON do modelo -> Diagnostico. Se vier quebrado, devolve um diagnóstico neutro (explicação, sem consultas):
    o Planejador ainda responde com a busca pela pergunta, como o pipeline clássico."""
    try:
        d = json.loads(bruto)
        consultas = [c.strip() for c in d.get("consultas", []) if isinstance(c, str) and c.strip()]
        return Diagnostico(
            problema_principal=d.get("problema_principal") if d.get("problema_principal") in PROBLEMAS else "outro",
            objetivo=str(d.get("objetivo", "")).strip(),
            restricoes={k: str(v) for k, v in (d.get("restricoes") or {}).items()},
            tipo_resposta=d.get("tipo_resposta") if d.get("tipo_resposta") in (PLANO, EXPLICACAO) else EXPLICACAO,
            consultas=consultas[:MAX_CONSULTAS],
        )
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        logger.warning("Triagem devolveu JSON inválido (%s); seguindo com diagnóstico neutro", exc)
        return Diagnostico(falhou=True)


class AgenteTriagem:
    nome = "Triagem"

    def diagnosticar(self, pergunta: str) -> Diagnostico:
        prompt = PROMPT_TRIAGEM.format(problemas=", ".join(PROBLEMAS), max_consultas=MAX_CONSULTAS, pergunta=pergunta)
        return interpretar(llm.triagem().invoke(prompt).content)
