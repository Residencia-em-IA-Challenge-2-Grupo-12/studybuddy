"""Acervo de materiais do estudante e base científica curada no ChromaDB ([2.3] Issue #14).

Responsabilidades:
  1. Ingestão e segmentação (`chunk_size=500`, `chunk_overlap=50`) dos 20 artigos científicos de
     `api/data/` com enriquecimento de metadados (`source`, `chunk_id`, `bloco_tematico`,
     `carga_recomendada`, `tecnica_principal`, `autor_ano`).
  2. Indexação e recuperação semântica no ChromaDB (`residencia_ia_semana2`) com filtro por
     metadados e validação pelo porteiro de distância L2 (`api/app/modules/rag/repository.py`).
  3. Classificação e normalização de materiais acadêmicos do estudante (`Material`), inferindo
     `carga` cognitiva (`"alta"` vs. `"baixa"`) e consultas científicas associadas.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from langchain_core.documents import Document

from app.core.config import API_DIR, settings
from app.modules.agentes.contratos import CargaCognitiva, Contrato, Material
from app.modules.rag import repository as rag_repo
from app.modules.rag.fontes import nome_fonte

logger = logging.getLogger("studybuddy.research.acervo")

BlocoTematico = Literal[
    "retencao_neurociencia",
    "foco_produtividade",
    "comportamento_procrastinacao",
    "planejamento_editais",
]

# Catálogo de metadados ricos dos 20 artigos científicos da base curada
CATALOGO_ARTIGOS: dict[str, dict[str, str]] = {
    "artigo_01_active_recall_karpicke.txt": {
        "bloco_tematico": "retencao_neurociencia",
        "carga_recomendada": "alta",
        "tecnica_principal": "Active Recall",
        "autor_ano": "Karpicke & Roediger (2008)",
    },
    "artigo_02_spaced_repetition_cepeda.txt": {
        "bloco_tematico": "retencao_neurociencia",
        "carga_recomendada": "baixa",
        "tecnica_principal": "Repetição Espaçada",
        "autor_ano": "Cepeda et al. (2006)",
    },
    "artigo_03_interleaving_rohwer.txt": {
        "bloco_tematico": "retencao_neurociencia",
        "carga_recomendada": "alta",
        "tecnica_principal": "Prática Intercalada",
        "autor_ano": "Rohrer & Taylor (2007)",
    },
    "artigo_04_cognitive_load_sweller.txt": {
        "bloco_tematico": "retencao_neurociencia",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Gestão da Carga Cognitiva",
        "autor_ano": "Sweller (2005)",
    },
    "artigo_05_sleep_consolidation_walker.txt": {
        "bloco_tematico": "retencao_neurociencia",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Consolidação no Sono",
        "autor_ano": "Walker (2009)",
    },
    "artigo_06_deep_work_newport.txt": {
        "bloco_tematico": "foco_produtividade",
        "carga_recomendada": "alta",
        "tecnica_principal": "Deep Work",
        "autor_ano": "Newport (2016)",
    },
    "artigo_07_attention_residue_leroy.txt": {
        "bloco_tematico": "foco_produtividade",
        "carga_recomendada": "alta",
        "tecnica_principal": "Mitigação de Resíduo de Atenção",
        "autor_ano": "Leroy (2009)",
    },
    "artigo_08_implementation_intentions_gollwitzer.txt": {
        "bloco_tematico": "foco_produtividade",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Intenções de Implementação (Se-Então)",
        "autor_ano": "Gollwitzer (1999)",
    },
    "artigo_09_timeboxing_allen.txt": {
        "bloco_tematico": "foco_produtividade",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Timeboxing",
        "autor_ano": "Allen & Pozen (2012)",
    },
    "artigo_10_pomodoro_cirillo.txt": {
        "bloco_tematico": "foco_produtividade",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Pomodoro",
        "autor_ano": "Cirillo (2006)",
    },
    "artigo_11_temporal_motivation_steel.txt": {
        "bloco_tematico": "comportamento_procrastinacao",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Decomposição de Metas (TMT)",
        "autor_ano": "Steel (2007)",
    },
    "artigo_12_perfectionism_flett.txt": {
        "bloco_tematico": "comportamento_procrastinacao",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Combate ao Overplanning",
        "autor_ano": "Flett & Hewitt (2002)",
    },
    "artigo_13_habit_loop_wood.txt": {
        "bloco_tematico": "comportamento_procrastinacao",
        "carga_recomendada": "baixa",
        "tecnica_principal": "Loop do Hábito",
        "autor_ano": "Wood & Rünger (2016)",
    },
    "artigo_14_willpower_depletion_baumeister.txt": {
        "bloco_tematico": "comportamento_procrastinacao",
        "carga_recomendada": "alta",
        "tecnica_principal": "Preservação Volitiva Matinal",
        "autor_ano": "Baumeister et al. (1998)",
    },
    "artigo_15_self_efficacy_bandura.txt": {
        "bloco_tematico": "comportamento_procrastinacao",
        "carga_recomendada": "baixa",
        "tecnica_principal": "Microtarefas de Autoeficácia",
        "autor_ano": "Bandura (1977)",
    },
    "artigo_16_pareto_engineering_box.txt": {
        "bloco_tematico": "planejamento_editais",
        "carga_recomendada": "alta",
        "tecnica_principal": "Princípio de Pareto 80/20",
        "autor_ano": "Box et al. (1987)",
    },
    "artigo_17_study_cycle_perez.txt": {
        "bloco_tematico": "planejamento_editais",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Ciclo de Estudos Flexível",
        "autor_ano": "Meirelles & Perez (2015)",
    },
    "artigo_18_project_based_learning_thomas.txt": {
        "bloco_tematico": "planejamento_editais",
        "carga_recomendada": "alta",
        "tecnica_principal": "Project-Based Learning (PBL)",
        "autor_ano": "Thomas (2000)",
    },
    "artigo_19_dual_burden_clt_martins.txt": {
        "bloco_tematico": "planejamento_editais",
        "carga_recomendada": "ambas",
        "tecnica_principal": "Micro-blocos CLT",
        "autor_ano": "Martins & Silveira (2020)",
    },
    "artigo_20_feynman_technique_gleick.txt": {
        "bloco_tematico": "planejamento_editais",
        "carga_recomendada": "alta",
        "tecnica_principal": "Técnica Feynman",
        "autor_ano": "Gleick & Goodstein (1992)",
    },
}

_TERMOS_ALTA_CARGA = (
    "calculo", "cálculo", "algebra", "álgebra", "fisica", "física", "quimica", "química",
    "programacao", "programação", "algoritmo", "estrutura de dados", "machine learning",
    "estatistica", "estatística", "exercicios", "exercícios", "lista", "resolucao", "resolução",
    "projeto", "codigo", "código", "matematica", "matemática", "derivada", "integral", "recursao", "recursão",
)

_TERMOS_BAIXA_CARGA = (
    "flashcard", "leitura", "resumo", "revisao", "revisão", "vocabulario", "vocabulário",
    "historia", "história", "ingles", "inglês", "mapa mental", "fichamento", "videoaula",
)


class EvidenciaRecuperada(Contrato):
    """Um trecho recuperado do ChromaDB com metadados enriquecidos e distância L2."""

    source: str
    chunk_id: int | str
    score_l2: float
    texto: str
    bloco_tematico: str = "geral"
    carga_recomendada: str = "ambas"
    tecnica_principal: str = ""
    autor_ano: str = ""


def metadados_do_artigo(source: str) -> dict[str, str]:
    """Retorna os metadados catalogados para o nome do arquivo de origem."""
    arquivo = nome_fonte(source)
    return dict(
        CATALOGO_ARTIGOS.get(
            arquivo,
            {
                "bloco_tematico": "geral",
                "carga_recomendada": "ambas",
                "tecnica_principal": "Estudo Estruturado",
                "autor_ano": "Base Curada",
            },
        )
    )


def _dividir_texto(
    texto: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[tuple[str, int]]:
    """Segmentação hierárquica idêntica ao RecursiveCharacterTextSplitter (separadores ['\\n\\n', '\\n', '. ', ' ', ''])."""
    texto = texto.strip()
    if len(texto) <= chunk_size:
        return [(texto, 0)] if texto else []

    # Primeiro separa cabeçalho bibliográfico (TÍTULO/AUTORES/TEMA) do corpo do artigo quando houver '\n\n'
    if "\n\n" in texto:
        cabecalho, corpo = texto.split("\n\n", 1)
        if len(cabecalho) <= chunk_size:
            offset_corpo = texto.find(corpo)
            fatias_corpo = _dividir_bloco_continuo(corpo, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            return [(cabecalho.strip(), 0)] + [(trecho, offset_corpo + ini) for trecho, ini in fatias_corpo]

    return _dividir_bloco_continuo(texto, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _dividir_bloco_continuo(
    bloco: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[tuple[str, int]]:
    if len(bloco) <= chunk_size:
        return [(bloco.strip(), 0)] if bloco.strip() else []

    resultado: list[tuple[str, int]] = []
    pos = 0
    n = len(bloco)
    while pos < n:
        fim = min(n, pos + chunk_size)
        if fim < n:
            janela = bloco[pos:fim]
            corte = max(janela.rfind(". "), janela.rfind("\n"), janela.rfind(" "))
            if corte > chunk_size // 3:
                fim = pos + corte + (1 if bloco[pos + corte] == "." else 0)
        trecho = bloco[pos:fim].strip()
        if trecho:
            resultado.append((trecho, pos))
        if fim >= n:
            break
        pos = max(pos + 1, fim - chunk_overlap)
    return resultado


def carregar_e_segmentar_acervo(
    data_dir: Path | None = None,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    """Carrega os 20 artigos científicos de `api/data/` e gera os chunks com metadados ricos."""
    diretorio = data_dir or (API_DIR / "data")
    if not diretorio.exists():
        raise FileNotFoundError(f"Diretório de artigos científicos não encontrado: {diretorio}")

    arquivos = sorted(diretorio.glob("*.txt"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum arquivo .txt encontrado em {diretorio}")

    chunks: list[Document] = []
    chunk_id = 0
    for caminho in arquivos:
        conteudo = caminho.read_text(encoding="utf-8")
        meta_artigo = metadados_do_artigo(caminho.name)
        fatias = _dividir_texto(conteudo, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for texto_fatia, start_index in fatias:
            eh_cabecalho = texto_fatia.startswith("TÍTULO:") and len(texto_fatia) <= 235
            chunks.append(
                Document(
                    page_content=texto_fatia,
                    metadata={
                        "source": f"../api/data/{caminho.name}",
                        "arquivo": caminho.name,
                        "chunk_id": chunk_id,
                        "start_index": start_index,
                        "tipo_chunk": "cabecalho" if eh_cabecalho else "conteudo",
                        **meta_artigo,
                    },
                )
            )
            chunk_id += 1
    return chunks


def inferir_carga_cognitiva(
    disciplina: str,
    titulo: str,
    dificuldade: int = 3,
) -> CargaCognitiva:
    """Classifica deterministicamente a carga cognitiva (`alta` ou `baixa`) de um material."""
    texto = f"{disciplina} {titulo}".lower()
    pontos_alta = sum(1 for termo in _TERMOS_ALTA_CARGA if termo in texto)
    pontos_baixa = sum(1 for termo in _TERMOS_BAIXA_CARGA if termo in texto)

    if pontos_alta > pontos_baixa:
        return "alta"
    if pontos_baixa > pontos_alta:
        return "baixa"
    return "alta" if dificuldade >= 3 else "baixa"


def criar_material(
    *,
    id: str,
    disciplina: str,
    titulo: str,
    horas_estimadas: float,
    dificuldade: int = 3,
    carga: CargaCognitiva | None = None,
    prazo: date | str | None = None,
) -> Material:
    """Cria e valida um objeto `Material` do contrato, inferindo a carga cognitiva se omitida."""
    carga_final = carga or inferir_carga_cognitiva(disciplina, titulo, dificuldade)
    if isinstance(prazo, str):
        prazo_final = date.fromisoformat(prazo) if prazo.strip() else None
    else:
        prazo_final = prazo
    return Material(
        id=id.strip(),
        disciplina=disciplina.strip(),
        titulo=titulo.strip(),
        carga=carga_final,
        horas_estimadas=horas_estimadas,
        dificuldade=dificuldade,
        prazo=prazo_final,
    )


def buscar_evidencias(
    consulta: str,
    *,
    k: int = 5,
    carga_filtro: CargaCognitiva | None = None,
    bloco_tematico: BlocoTematico | None = None,
    apenas_conteudo: bool = False,
    aplicar_porteiro: bool = True,
    buscador: Callable[[str, int], list[tuple[Document, float]]] | None = None,
) -> list[EvidenciaRecuperada]:
    """Recupera evidências científicas do ChromaDB com enriquecimento de metadados e filtragem opcional.

    Respeita o porteiro de distância L2 de `api/app/modules/rag/repository.py` quando `aplicar_porteiro=True`.
    Aceita um `buscador` injetável para testes unitários sem depender de servidor Ollama/Chroma ativo.
    """
    fn_busca = buscador or (lambda q, top_k: rag_repo.buscar(q, k=top_k))
    # Busca uma janela um pouco maior quando há filtros pós-busca para manter até k resultados
    k_busca = k * 2 if (carga_filtro or bloco_tematico or apenas_conteudo) else k
    brutos = fn_busca(consulta, k_busca)

    if aplicar_porteiro and brutos:
        d1 = float(brutos[0][1])
        if rag_repo.barrada(d1):
            return []

    evidencias: list[EvidenciaRecuperada] = []
    for doc, score in brutos:
        dist = float(score)
        if aplicar_porteiro and rag_repo.barrada(dist):
            continue

        source_raw = str(doc.metadata.get("source", "desconhecida"))
        arquivo = nome_fonte(source_raw)
        meta_cat = metadados_do_artigo(arquivo)

        bloco_doc = str(doc.metadata.get("bloco_tematico") or meta_cat["bloco_tematico"])
        carga_doc = str(doc.metadata.get("carga_recomendada") or meta_cat["carga_recomendada"])
        tecnica_doc = str(doc.metadata.get("tecnica_principal") or meta_cat["tecnica_principal"])
        autor_doc = str(doc.metadata.get("autor_ano") or meta_cat["autor_ano"])

        texto = doc.page_content.strip()
        eh_cabecalho = texto.startswith("TÍTULO:") and len(texto) <= 235

        if apenas_conteudo and eh_cabecalho:
            continue
        if bloco_tematico and bloco_doc != bloco_tematico:
            continue
        if carga_filtro and carga_doc not in (carga_filtro, "ambas"):
            continue

        evidencias.append(
            EvidenciaRecuperada(
                source=arquivo,
                chunk_id=doc.metadata.get("chunk_id", "N/A"),
                score_l2=round(dist, 4),
                texto=texto,
                bloco_tematico=bloco_doc,
                carga_recomendada=carga_doc,
                tecnica_principal=tecnica_doc,
                autor_ano=autor_doc,
            )
        )
        if len(evidencias) >= k:
            break

    return evidencias
