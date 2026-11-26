"""Técnica padrão por carga, usada quando o LLM não é chamado ou falha. Cita a base de artigos (api/data)."""

from app.modules.agentes.contratos import CargaCognitiva

TECNICA_PADRAO: dict[CargaCognitiva, tuple[str, str, list[str]]] = {
    "alta": (
        "Pomodoro com active recall",
        "Alta carga no pico de energia: resolver sem consultar e conferir depois fortalece a retenção "
        "[Fonte: artigo_01_active_recall_karpicke.txt], em ciclos de foco com pausa "
        "[Fonte: artigo_10_pomodoro_cirillo.txt].",
        ["artigo_01_active_recall_karpicke.txt", "artigo_10_pomodoro_cirillo.txt"],
    ),
    "baixa": (
        "Flashcards com repetição espaçada",
        "Baixa carga no vale: revisões curtas e espaçadas ao longo da semana rendem mais que uma sessão longa "
        "[Fonte: artigo_02_spaced_repetition_cepeda.txt].",
        ["artigo_02_spaced_repetition_cepeda.txt"],
    ),
}
