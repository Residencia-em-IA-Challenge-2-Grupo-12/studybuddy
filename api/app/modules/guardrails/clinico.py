"""Barreira 3 de guardrails ([4.6]): limite clínico. Determinística, sem LLM (roda no CI e antes do Maestro).

| Permitido (bem-estar e cronobiologia)      | Bloqueado (saúde clínica)                              |
| :----------------------------------------- | :----------------------------------------------------- |
| Higiene do sono, pausas, alongamento leve  | Remédios (ex.: para TDAH), nootrópicos, suplementos    |
| Ajuste de carga por fadiga                 | Diagnóstico (ansiedade, depressão, burnout)            |
| Rotina pelo ciclo circadiano               | Dietas, tratamento psicológico                         |

Como decide:
1. Normaliza o texto (minúsculas, sem acento) e procura quatro grupos de padrões: substâncias, diagnóstico,
   dieta e tratamento.
2. Nenhum padrão: passa. Cansaço, sono ruim e "ansioso com a prova" não casam com nada, porque são estados,
   não pedidos clínicos.
3. Achou um padrão num contexto de estudo do tema (ex.: "revisar farmacologia para a prova") e sem pedido
   para uso próprio ("posso tomar", "quanto tomo", "para mim"): passa. Senão, bloqueia com a mensagem
   fixa do plano.

Os motivos (`motivos(texto)`) vão só para o log e o rastro, nunca para o estudante.
"""

import re
import unicodedata

from app.modules.agentes.contratos import Veredito

MENSAGEM_BLOQUEIO = (
    "Como mentor de estudos, posso ajustar sua carga horária e pausas de acordo com seu cansaço, mas não "
    "forneço recomendações médicas, nutricionais ou sobre medicamentos. Consulte um profissional de saúde."
)

_SUBSTANCIAS = (
    r"remedios?|medicamentos?|medicac\w*|medica(?:r|do|da)|comprimidos?|capsulas?|pilulas?|gotas de|"
    r"doses?|dosagem|posologia|\d+\s*mg|miligramas?|tarja preta|receita medica|sem receita|"
    r"antidepressivos?|ansioliticos?|calmantes?|estimulantes?|psicoestimulantes?|nootropicos?|"
    r"suplementos?|suplementac\w*|vitaminas?|creatina|omega ?3|cafeina em (?:capsula|comprimido)|"
    r"ritalina|metilfenidato|venvanse|lisdexanfetamina|adderall|modafinil|stavigile|"
    r"zolpidem|clonazepam|rivotril|alprazolam|diazepam|lorazepam|"
    r"sertralina|fluoxetina|escitalopram|venlafaxina|bupropiona|"
    r"melatonina|canabidiol|cbd|microdos\w*"
)
_CONDICOES = r"tdah|deficit de atencao|depressao|depressivo|ansiedade|burnout|bipolar|toc|autismo|autista|transtorno\w*|insonia|sindrome do panico|panico"

PADROES = {
    "substancia": re.compile(rf"\b(?:{_SUBSTANCIAS})\b"),
    "diagnostico": re.compile(
        rf"\b(?:sera que|acho que|como (?:sei|saber) se|posso ter|devo ter|tenho cara de)\b.{{0,25}}"
        rf"\b(?:tenho|sou|estou com|to com|tou com|tenha|ter)\b.{{0,15}}\b(?:{_CONDICOES})\b"
        rf"|\b(?:me )?diagnostic\w*|\bsintomas de (?:{_CONDICOES})\b|\bisso e (?:{_CONDICOES})\b"
        rf"|\btestes? de (?:{_CONDICOES})\b|\b(?:tenho|sou) (?:{_CONDICOES})\s*\?"
    ),
    "dieta": re.compile(
        r"\b(?:dietas?|jejum|cardapio|emagrec\w*|perder peso|low carb|cetogenica|"
        r"(?:o que|quanto) (?:devo )?comer|alimentos? (?:para|que) (?:foco|memoria|concentrac\w*|estudar|o cerebro))\b"
    ),
    "tratamento": re.compile(
        rf"\b(?:tratar|tratamento|curar|cura|terapia|terapeutic\w*)\b.{{0,30}}\b(?:{_CONDICOES})\b"
        rf"|\b(?:{_CONDICOES})\b.{{0,30}}\b(?:tratar|tratamento|curar|cura)\b"
        r"|\b(?:faz|faca|seja|atue como|funcione como)\b.{0,20}\b(?:meu |minha )?(?:terapeuta|psicologo|psicologa|psiquiatra|medico|medica|nutricionista)\b"
    ),
}

# Estudar o tema (prova de farmacologia, redação sobre depressão) não é pedir conselho clínico. Exige a área
# ou o formato do estudo: "prova" e "estudar" sozinhos não bastam, porque aparecem em quase toda mensagem.
_ACADEMICO = re.compile(
    r"\b(?:farmacologia|farmacia|medicina|enfermagem|nutricao|psicologia|psiquiatria|bioquimica|fisiologia|"
    r"neurociencia|redacao|seminario|trabalho sobre|tcc sobre|artigo sobre|resumo (?:da|de|sobre)|"
    r"flashcards? (?:de|sobre)|aula (?:de|sobre))\b"
)
# ... a não ser que o pedido seja para a própria pessoa.
_USO_PESSOAL = re.compile(
    r"\b(?:posso|devo|quero|preciso|vale a pena|e seguro|faz mal|seria bom)\b.{0,15}"
    r"\b(?:tomar|usar|parar|misturar|aumentar|diminuir|comecar|comprar|fazer)\b"
    r"|\b(?:eu tomo|to tomando|estou tomando|tomei|tomaria|me receita|me indica|me recomenda|"
    r"(?:qual|quais|quanto|quantos|quantas) (?:a |o |de )?(?:remedio|dose|dosagem|suplemento|dieta|mg|devo|tomo|tomar)|"
    r"para mim|pra mim|e seguro|funciona(?:m)? para|ajuda(?:m)? a (?:estudar|focar|dormir|virar)|"
    r"me (?:ajuda|ajude) a (?:tomar|parar|escolher)|onde (?:compro|consigo)|sem receita)\b"
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.split())


def motivos(texto: str) -> list[str]:
    """Os grupos que casaram e, quando liberado por ser estudo do tema, o marcador "academico"."""
    t = _normalizar(texto)
    achados = [nome for nome, padrao in PADROES.items() if padrao.search(t)]
    if achados and _ACADEMICO.search(t) and not _USO_PESSOAL.search(t):
        achados.append("academico")
    return achados


def avaliar(texto: str) -> Veredito:
    m = motivos(texto)
    if not m or "academico" in m:
        return Veredito(permitido=True, categoria="OK")
    return Veredito(permitido=False, categoria="MEDICAL_ADVICE", resposta_bloqueio=MENSAGEM_BLOQUEIO)
