"""Testes unitários da Fundação de Dados do Research Agent (Etapa 1: Issues #40, #13 e #14)."""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

import pytest
from langchain_core.documents import Document

from app.modules.agentes.contratos import CheckIn, ContextoEstudante, Janela, Material
from app.modules.agentes.research.acervo import (
    CATALOGO_ARTIGOS,
    buscar_evidencias,
    carregar_e_segmentar_acervo,
    criar_material,
    inferir_carga_cognitiva,
)
from app.modules.agentes.research.banco import (
    HorarioSono,
    HorariosRefeicoes,
    MetaEstudo,
    PerfilEstudante,
    RegistroCheckIn,
    RegistroHistoricoEstudo,
    RepositorioEstudante,
)
from app.modules.agentes.research.circadiano import (
    EscalasCheckIn,
    calcular_indice_capacidade,
    classificar_estado_capacidade,
    derivar_picos_e_vales,
    dias_da_semana,
    expandir_janelas_refeicoes,
    expandir_janelas_sono,
    mapear_escalas_para_checkin,
)

FIXTURES_CONTEXTO = Path(__file__).resolve().parent / "fixtures" / "contexto"


# ==============================================================================
# [2.1] Testes do Banco do Estudante (Issue #40)
# ==============================================================================
def test_banco_crud_perfil_materiais_metas_e_checkins(tmp_path: Path):
    db_file = tmp_path / "estudantes_test.db"
    repo = RepositorioEstudante(db_file)

    perfil = PerfilEstudante(
        estudante_id="est-01",
        nome="Lucas",
        cronotipo="matutino",
        sono=HorarioSono(inicio=time(22, 30), fim=time(5, 30)),
        refeicoes=HorariosRefeicoes(almoco=time(12, 0), jantar=time(18, 0)),
        agenda_conectada=True,
    )
    repo.salvar_perfil(perfil)

    recuperado = repo.obter_perfil("est-01")
    assert recuperado == perfil
    assert len(repo.listar_perfis()) == 1

    materiais = [
        Material(
            id="calc-01",
            disciplina="Cálculo I",
            titulo="Limites e derivadas",
            carga="alta",
            horas_estimadas=4.0,
            dificuldade=4,
            prazo=date(2026, 12, 4),
        ),
        Material(
            id="hist-01",
            disciplina="História",
            titulo="Leitura Era Vargas",
            carga="baixa",
            horas_estimadas=2.0,
            dificuldade=2,
            prazo=None,
        ),
    ]
    repo.salvar_materiais("est-01", materiais)
    assert repo.listar_materiais("est-01") == materiais

    meta = MetaEstudo(
        id="meta-concurso",
        estudante_id="est-01",
        titulo="Concluir edital base em 8 semanas",
        horas_semanais_meta=15.0,
        prazo_final=date(2027, 1, 31),
        prioridade=5,
    )
    repo.salvar_meta(meta)
    assert repo.listar_metas("est-01") == [meta]

    ck1 = RegistroCheckIn(
        estudante_id="est-01",
        data_referencia=date(2026, 11, 29),
        checkin=CheckIn(energia=2, horas_sono=5.5, estresse=4),
        indice_capacidade=0.35,
        humor=2,
        qualidade_sono=2,
        fadiga=4,
    )
    ck2 = RegistroCheckIn(
        estudante_id="est-01",
        data_referencia=date(2026, 11, 30),
        checkin=CheckIn(energia=4, horas_sono=7.5, estresse=2),
        indice_capacidade=0.75,
        humor=4,
        qualidade_sono=4,
        fadiga=2,
    )
    repo.registrar_checkin(ck1)
    repo.registrar_checkin(ck2)
    assert repo.obter_ultimo_checkin("est-01") == ck2
    assert len(repo.listar_checkins("est-01")) == 2

    sessao = RegistroHistoricoEstudo(
        id="sess-01",
        estudante_id="est-01",
        material_id="calc-01",
        dia=date(2026, 11, 30),
        minutos_estudados=50,
        tecnica="Active Recall",
    )
    repo.registrar_sessao_estudo(sessao)
    assert repo.listar_historico_estudo("est-01") == [sessao]

    assert repo.remover_material("est-01", "hist-01") is True
    assert len(repo.listar_materiais("est-01")) == 1


def test_banco_salvar_e_recuperar_snapshot_contexto():
    repo = RepositorioEstudante(":memory:")
    ctx_json = (FIXTURES_CONTEXTO / "matutino.json").read_text(encoding="utf-8")
    ctx = ContextoEstudante.model_validate_json(ctx_json)

    repo.salvar_contexto(ctx)
    obtido = repo.obter_contexto(ctx.estudante_id, ctx.semana_inicio)
    assert obtido == ctx
    assert repo.listar_materiais(ctx.estudante_id) == ctx.materiais
    ultimo_ck = repo.obter_ultimo_checkin(ctx.estudante_id)
    assert ultimo_ck is not None
    assert ultimo_ck.checkin == ctx.checkin


# ==============================================================================
# [2.2] Testes do Perfil Circadiano e Check-in (Issue #13)
# ==============================================================================
@pytest.mark.parametrize(
    "nome_fixture,indice_esperado",
    [
        ("matutino", 0.6),
        ("vespertino", 0.6),
        ("noturno", 0.6),
        ("agenda_cheia", 0.6),
        ("prazo_apertado", 0.6),
        ("alta_energia", 0.9),
        ("fadiga", 0.2),
    ],
)
def test_indice_capacidade_bate_com_todas_as_fixtures(nome_fixture: str, indice_esperado: float):
    ctx = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / f"{nome_fixture}.json").read_text(encoding="utf-8")
    )
    calculado = calcular_indice_capacidade(ctx.checkin)
    assert calculado == indice_esperado
    assert calculado == ctx.indice_capacidade


def test_mapeamento_escalas_checkin_e_classificacao():
    escalas = EscalasCheckIn(humor=4, estresse=2, sono=4, fadiga=3, horas_sono=7.0)
    ck = mapear_escalas_para_checkin(escalas)
    assert ck == CheckIn(energia=3, horas_sono=7.0, estresse=2)
    assert classificar_estado_capacidade(0.9) == "alta_energia"
    assert classificar_estado_capacidade(0.6) == "normal"
    assert classificar_estado_capacidade(0.2) == "fadiga"


def test_quebra_meia_noite_sono_e_picos_vales_nas_fixtures():
    dias = dias_da_semana(date(2026, 11, 30), num_dias=5)

    # 1. Matutino: sono 22:00-06:00 vira duas janelas por dia (22:00-23:59 e 00:00-06:00)
    ctx_mat = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "matutino.json").read_text(encoding="utf-8")
    )
    sono_mat = expandir_janelas_sono(dias, time(22, 0), time(6, 0))
    assert sono_mat == ctx_mat.sono

    picos_mat, vales_mat = derivar_picos_e_vales("matutino", dias, livres=ctx_mat.livres, ocupados=ctx_mat.ocupados)
    assert picos_mat == ctx_mat.picos
    assert vales_mat == ctx_mat.vales

    ref_mat = expandir_janelas_refeicoes(dias, almoco=time(12, 0), jantar=time(19, 0))
    assert ref_mat == ctx_mat.refeicoes

    # 2. Noturno: sono 02:00-10:00 não cruza meia-noite -> 1 janela por dia
    ctx_not = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "noturno.json").read_text(encoding="utf-8")
    )
    sono_not = expandir_janelas_sono(dias, time(2, 0), time(10, 0))
    assert sono_not == ctx_not.sono
    picos_not, vales_not = derivar_picos_e_vales("noturno", dias, livres=ctx_not.livres)
    assert picos_not == ctx_not.picos
    assert vales_not == ctx_not.vales

    # 3. Agenda cheia (CLT): pico matutino padrão (08-11h) ocupado -> realoca para 06:00-07:00 e 19:00-20:30
    ctx_clt = ContextoEstudante.model_validate_json(
        (FIXTURES_CONTEXTO / "agenda_cheia.json").read_text(encoding="utf-8")
    )
    picos_clt, vales_clt = derivar_picos_e_vales(
        "matutino", dias, livres=ctx_clt.livres, ocupados=ctx_clt.ocupados
    )
    assert picos_clt == ctx_clt.picos
    assert vales_clt == ctx_clt.vales


# ==============================================================================
# [2.3] Testes do Acervo de Materiais e Metadados (Issue #14)
# ==============================================================================
def test_carregar_e_segmentar_acervo_20_artigos():
    chunks = carregar_e_segmentar_acervo()
    assert len(chunks) >= 40
    arquivos_encontrados = {c.metadata["arquivo"] for c in chunks}
    assert len(arquivos_encontrados) == 20
    assert arquivos_encontrados == set(CATALOGO_ARTIGOS.keys())

    for c in chunks:
        assert len(c.page_content) <= 500
        assert c.metadata["bloco_tematico"] in {
            "retencao_neurociencia",
            "foco_produtividade",
            "comportamento_procrastinacao",
            "planejamento_editais",
        }
        assert c.metadata["carga_recomendada"] in {"alta", "baixa", "ambas"}
        assert c.metadata["tecnica_principal"]


def test_inferencia_carga_cognitiva_e_criacao_material():
    assert inferir_carga_cognitiva("Cálculo I", "Limites e derivadas: lista 3", 4) == "alta"
    assert inferir_carga_cognitiva("Programação", "Exercícios de recursão em Python", 3) == "alta"
    assert inferir_carga_cognitiva("História", "Leitura: capítulo 5 (Era Vargas)", 2) == "baixa"
    assert inferir_carga_cognitiva("Inglês", "Flashcards de vocabulário (unidade 4)", 1) == "baixa"

    mat = criar_material(
        id="alg-01",
        disciplina="Algoritmos",
        titulo="Lista de grafos",
        horas_estimadas=3.5,
        dificuldade=4,
        prazo="2026-12-04",
    )
    assert mat.carga == "alta"
    assert mat.prazo == date(2026, 12, 4)


def test_buscar_evidencias_com_filtros_e_porteiro():
    docs_fakes = [
        (
            Document(
                page_content="TÍTULO: Deep Work\nAUTORES: Cal Newport",
                metadata={"source": "../api/data/artigo_06_deep_work_newport.txt", "chunk_id": 10},
            ),
            0.35,
        ),
        (
            Document(
                page_content="O trabalho profundo consiste em atividades realizadas em foco ininterrupto de 2 a 4 horas.",
                metadata={"source": "../api/data/artigo_06_deep_work_newport.txt", "chunk_id": 11},
            ),
            0.40,
        ),
        (
            Document(
                page_content="A prática distribuída (repetição espaçada) supera o estudo de última hora.",
                metadata={"source": "../api/data/artigo_02_spaced_repetition_cepeda.txt", "chunk_id": 3},
            ),
            0.45,
        ),
    ]

    # Filtrando apenas conteúdo denso e carga 'alta'
    ev_alta = buscar_evidencias(
        "foco profundo",
        k=3,
        carga_filtro="alta",
        apenas_conteudo=True,
        aplicar_porteiro=False,
        buscador=lambda q, k: docs_fakes,
    )
    assert len(ev_alta) == 1
    assert ev_alta[0].source == "artigo_06_deep_work_newport.txt"
    assert ev_alta[0].chunk_id == 11
    assert ev_alta[0].tecnica_principal == "Deep Work"
