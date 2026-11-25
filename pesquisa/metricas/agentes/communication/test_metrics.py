"""Testes das métricas determinísticas do Communication e da integridade do conjunto de avaliação.

Rodar (a partir de pesquisa/): python -m pytest metricas/agentes/communication/test_metrics.py
"""

import json
import sys
from pathlib import Path

from metricas.agentes.communication import metrics as mc

RAIZ = Path(__file__).resolve().parents[4]
CENARIOS = Path(__file__).with_name("cenarios.json")
FIXTURES = RAIZ / "pesquisa" / "fixtures" / "communication"

GRADE = {
    "blocos": [
        {"dia": "segunda", "inicio": "19:00", "fim": "20:00", "disciplina": "Matemática",
         "material": "https://example.org/matematica"},
        {"dia": "quarta", "inicio": "20:00", "fim": "21:00", "disciplina": "Biologia", "material": None},
    ]
}
EVIDENCIAS = ["artigo_05_sleep.txt", "artigo_19_clt.txt"]


def plano(grade=GRADE) -> str:
    return "## Seu plano da semana\n" + "\n".join(mc.linhas_da_grade(grade))


def test_plano_completo_e_fiel():
    resultado = mc.fidelidade_ao_plano(plano(), GRADE)
    assert resultado["score"] == 1.0
    assert resultado["fiel"] is True
    assert resultado["blocos_ausentes"] == []


def test_bloco_ausente_reduz_o_score():
    markdown = plano().replace(mc.linha_do_bloco(GRADE["blocos"][1]), "")
    resultado = mc.fidelidade_ao_plano(markdown, GRADE)
    assert resultado["score"] == 0.5
    assert resultado["fiel"] is False
    assert GRADE["blocos"][1]["disciplina"] in resultado["blocos_ausentes"][0]


def test_horario_alterado_quebra_a_fidelidade():
    linhas = mc.linhas_da_grade(GRADE)
    alterada = linhas[1].replace("20:00", "20:30")
    markdown = "## Seu plano da semana\n" + linhas[0] + "\n" + alterada
    assert mc.fidelidade_ao_plano(markdown, GRADE)["blocos_presentes"] == 1


def test_blocos_embaralhados_nao_sao_fieis():
    linhas = mc.linhas_da_grade(GRADE)
    markdown = "## Seu plano da semana\n" + "\n".join(reversed(linhas))
    resultado = mc.fidelidade_ao_plano(markdown, GRADE)
    assert resultado["blocos_presentes"] == 2
    assert resultado["fiel"] is False


def test_horarios_inventados_na_abertura():
    abertura = "Comece às 07:30 e depois siga às 19:00."
    assert mc.horarios_inventados(abertura, GRADE) == ["07:30"]


def test_citacoes_validas_e_invalidas():
    texto = "Durma bem [Fonte: artigo_05_sleep.txt] e evite [Fonte: artigo_99_x.txt]."
    resultado = mc.citacoes_validas(texto, EVIDENCIAS)
    assert resultado["total"] == 2
    assert resultado["citados"] == ["05", "99"]
    assert resultado["invalidos"] == ["99"]
    assert resultado["score"] == 0.5


def test_texto_sem_citacao_tem_score_cheio():
    assert mc.citacoes_validas("Sem fonte aqui.", EVIDENCIAS)["score"] == 1.0


def test_clareza_devolve_faixa_plausivel():
    resultado = mc.clareza("Você vai estudar matemática hoje. Faça uma pausa depois.")
    assert resultado["palavras"] == 9
    assert resultado["frases"] == 2
    assert 0 <= resultado["indice"] <= 100


def test_clareza_ignora_marcacao_de_markdown():
    com_link = mc.clareza("Veja o [Material](https://example.org/x) e estude.")
    sem_link = mc.clareza("Veja o Material e estude.")
    assert com_link["indice"] == sem_link["indice"]


def test_conjunto_tem_pelo_menos_20_cenarios():
    cenarios = json.loads(CENARIOS.read_text(encoding="utf-8"))
    assert len(cenarios) >= 20
    ids = [c["id"] for c in cenarios]
    assert len(ids) == len(set(ids))
    assert {c["tom_esperado"] for c in cenarios} == {"acolhedor", "equilibrado", "desafiador"}


def test_cenarios_batem_com_a_regra_do_agente():
    try:
        sys.path.insert(0, str(RAIZ / "api"))
        from app.modules.agentes import communication
        from app.modules.agentes.communication_schemas import CheckIn
    except ImportError:  # ambiente sem as dependências da API
        return
    cenarios = json.loads(CENARIOS.read_text(encoding="utf-8"))
    for cenario in cenarios:
        esperado = communication.escolher_tom(CheckIn(**cenario["checkin"]))
        assert esperado == cenario["tom_esperado"], cenario["id"]


def test_fixtures_cobrem_os_tres_tons():
    try:
        sys.path.insert(0, str(RAIZ / "api"))
        from app.modules.agentes import communication
        from app.modules.agentes.communication_schemas import CheckIn
    except ImportError:
        return
    checkins = json.loads((FIXTURES / "checkins.json").read_text(encoding="utf-8"))
    tons = {communication.escolher_tom(CheckIn(**c)) for c in checkins.values()}
    assert tons == {"acolhedor", "equilibrado", "desafiador"}


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print("ok ", nome)
    print("todos passaram")
