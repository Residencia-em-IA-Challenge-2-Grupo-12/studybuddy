"""Agente Research ([2.5] Issue #16): o agente bibliotecário e montador de contexto do estudante.

Responsabilidades no sistema multiagente:
  1. `montar_contexto`: cruza os dados do Banco do Estudante ([2.1]), o motor circadiano e de
     check-in ([2.2]), o acervo de materiais ([2.3]) e a integração com o Google Calendar ([2.4])
     para construir um `ContextoEstudante` 100% validado no contrato Pydantic da [0.1].
  2. `pesquisar_evidencias`: formula consultas semânticas orientadas ao cronotipo, estado do
     check-in (`alta_energia`, `normal`, `fadiga`) e carga cognitiva dos materiais, recuperando
     trechos curados no ChromaDB respeitando o porteiro de distância L2 (`tau = 1.026`).
  3. `curar_recomendacao`: sintetiza a orientação bibliotecária via LLM local (Ollama, JSON Schema
     estrito `SaidaResearchLLM`) com citação obrigatória de fontes verificadas por
     `api/app/modules/rag/verificador.py`, ou aciona fallback determinístico sem alucinação caso o
     LLM esteja indisponível.
  4. `sincronizar_agenda`: grava os blocos de estudo aprovados pelo Validation no Google Calendar.
"""

from __future__ import annotations

import logging
import re
import time as time_mod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

from langchain_core.documents import Document
from pydantic import Field, ValidationError

from app.modules.agentes.contratos import (
    BlocoEstudo,
    CheckIn,
    ContextoEstudante,
    Contrato,
    Cronotipo,
    Janela,
    Material,
    ProvedorAgenda,
    esquema,
)
from app.modules.rag import repository as rag_repo
from app.modules.rag.fontes import formatar_trechos, nome_fonte
from app.modules.rag.verificador import verificar

from .acervo import EvidenciaRecuperada, buscar_evidencias, metadados_do_artigo
from .agenda import AgendaFake
from .banco import HorarioSono, HorariosRefeicoes, PerfilEstudante, RegistroCheckIn, RepositorioEstudante
from .circadiano import (
    EscalasCheckIn,
    calcular_indice_capacidade,
    classificar_estado_capacidade,
    derivar_picos_e_vales,
    dias_da_semana,
    expandir_janelas_refeicoes,
    expandir_janelas_sono,
    mapear_escalas_para_checkin,
)

logger = logging.getLogger("studybuddy.research")

K_TRECHOS_RESEARCH = 4
_ARTIGO = re.compile(r"artigo_(\d{2})")


class SaidaResearchLLM(Contrato):
    """Saída estruturada do LLM no Research Agent (validada com extra='forbid')."""

    foco_recomendado: str = Field(min_length=1)
    orientacao_circadiana: str = Field(min_length=1)
    sintese_evidencias: str = Field(min_length=1)


ESQUEMA_RESEARCH = esquema(SaidaResearchLLM)

PROMPT_RESEARCH = """Você é o Research Agent (bibliotecário científico) de um mentor de estudos.
Sua tarefa é sintetizar evidências científicas dos trechos abaixo para orientar o planejamento semanal do estudante, respeitando o cronotipo, o estado do check-in e a carga cognitiva dos materiais.

PERFIL E ESTADO DO ESTUDANTE:
- Cronotipo: {cronotipo} (picos de atenção: {faixa_pico}; vales de energia: {faixa_vale})
- Check-in de hoje: energia {energia}/5, sono {horas_sono:g}h, estresse {estresse}/5
- Índice de capacidade cognitiva: {indice_capacidade:.2f} (estado: {estado_capacidade})
- Materiais prioritários: {resumo_materiais}

TRECHOS DA BASE CIENTÍFICA:
{trechos}

Responda APENAS com um objeto JSON com as três chaves abaixo:
- "foco_recomendado": diretriz curta sobre o ritmo de foco/pausa e priorização de carga para o estado '{estado_capacidade}'.
- "orientacao_circadiana": como distribuir materiais de alta e baixa carga nos picos ({faixa_pico}) e vales ({faixa_vale}) do cronotipo '{cronotipo}' preservando o sono ({horas_sono:g}h).
- "sintese_evidencias": de 2 a 3 frases justificando cientificamente a recomendação APENAS com o que os trechos acima dizem, citando ao menos uma fonte recebida no formato [Fonte: artigo_XX_nome.txt]. Não invente autores, números ou fontes fora dos trechos."""


@dataclass
class RelatoCuradoria:
    """Relato de execução e auditoria da curadoria bibliotecária do Research Agent."""

    estudante_id: str
    estado_capacidade: str
    consultas: list[str] = field(default_factory=list)
    evidencias: list[EvidenciaRecuperada] = field(default_factory=list)
    foco_recomendado: str = ""
    orientacao_circadiana: str = ""
    sintese_evidencias: str = ""
    fontes_citadas: list[str] = field(default_factory=list)
    citacoes_removidas: list[str] = field(default_factory=list)
    usou_llm: bool = False
    motivo_fallback: str = ""
    segundos: float = 0.0
    bruto: str = ""


def _faixa_horaria(janelas: list[Janela]) -> str:
    if not janelas:
        return "não definida"
    primeiro_dia = janelas[0].dia
    do_dia = [f"{j.inicio:%H:%M}–{j.fim:%H:%M}" for j in janelas if j.dia == primeiro_dia]
    return ", ".join(do_dia)


def _resumo_materiais(materiais: list[Material]) -> str:
    if not materiais:
        return "nenhum material cadastrado"
    partes = []
    for m in materiais[:4]:
        prazo_txt = f", prazo {m.prazo.isoformat()}" if m.prazo else ""
        partes.append(f"{m.disciplina} ({m.titulo}, carga {m.carga}, {m.horas_estimadas:g}h{prazo_txt})")
    return "; ".join(partes)


def consultas_do_contexto(ctx: ContextoEstudante) -> list[str]:
    """Gera de 2 a 3 consultas semânticas estratégicas a partir do `ContextoEstudante`."""
    estado = classificar_estado_capacidade(ctx.indice_capacidade)
    consultas: list[str] = []

    if estado == "fadiga" or ctx.checkin.horas_sono < 6.0 or ctx.checkin.estresse >= 4:
        consultas.append(
            "sono consolidacao da memoria privacao de sono fadiga decisoria esgotamento do autocontrole"
        )
    elif estado == "alta_energia":
        consultas.append(
            "trabalho profundo deep work foco ininterrupto active recall pratica intercalada"
        )
    else:
        consultas.append(
            "tecnica pomodoro intervalos de foco ciclos de estudo timeboxing"
        )

    cargas = {m.carga for m in ctx.materiais}
    tem_prazo = any(m.prazo is not None for m in ctx.materiais)
    if tem_prazo or "alta" in cargas:
        consultas.append(
            "principio de pareto 80 20 priorizacao de edital pratica de recuperacao active recall"
        )
    if "baixa" in cargas:
        consultas.append(
            "repeticao espacada pratica distribuida revisao flashcards consolidacao"
        )

    return consultas[:3]


def montar_prompt_research(ctx: ContextoEstudante, trechos: list[Document]) -> str:
    """Monta o prompt exato enviado ao LLM do Research Agent (também usado na harness [2.0])."""
    estado = classificar_estado_capacidade(ctx.indice_capacidade)
    return PROMPT_RESEARCH.format(
        cronotipo=ctx.cronotipo,
        faixa_pico=_faixa_horaria(ctx.picos),
        faixa_vale=_faixa_horaria(ctx.vales),
        energia=ctx.checkin.energia,
        horas_sono=ctx.checkin.horas_sono,
        estresse=ctx.checkin.estresse,
        indice_capacidade=ctx.indice_capacidade,
        estado_capacidade=estado,
        resumo_materiais=_resumo_materiais(ctx.materiais),
        trechos=formatar_trechos(trechos),
    )


def _fontes_resolvidas(citadas: list[str], trechos: list[Document]) -> list[str]:
    por_numero = {
        m_.group(1): nome_fonte(d.metadata.get("source", ""))
        for d in trechos
        if (m_ := _ARTIGO.search(nome_fonte(d.metadata.get("source", ""))))
    }
    return [por_numero[c.removeprefix("artigo_")] for c in citadas if c.removeprefix("artigo_") in por_numero]


def _sintese_deterministica(
    ctx: ContextoEstudante,
    evidencias: list[EvidenciaRecuperada],
) -> tuple[str, str, str, list[str]]:
    """Fallback determinístico fundamentado nas evidências recuperadas quando o LLM não é usado."""
    estado = classificar_estado_capacidade(ctx.indice_capacidade)
    faixa_pico = _faixa_horaria(ctx.picos)
    faixa_vale = _faixa_horaria(ctx.vales)

    if estado == "fadiga":
        foco = "Priorizar blocos curtos de 25 min com pausas de 10 a 15 min e reduzir carga cognitiva."
    elif estado == "alta_energia":
        foco = "Aproveitar a alta capacidade com blocos estendidos de 50 min de foco e 10 min de pausa."
    else:
        foco = "Manter ritmo sustentável em blocos de 25 min de foco e 5 min de pausa."

    orientacao = (
        f"Alocar matérias de alta carga nas janelas de pico do cronotipo {ctx.cronotipo} ({faixa_pico}) "
        f"e reservar os vales ({faixa_vale}) apenas para tarefas de baixa carga, protegendo {ctx.checkin.horas_sono:g}h de sono."
    )

    if evidencias:
        ev0 = evidencias[0]
        fontes = list(dict.fromkeys(e.source for e in evidencias[:2]))
        citacoes_str = " ".join(f"[Fonte: {f}]" for f in fontes)
        resumo_ev = ev0.texto.split(". ")[0].strip().rstrip(".")
        sintese = (
            f"De acordo com a literatura recuperada ({ev0.tecnica_principal}), {resumo_ev.lower()}. "
            f"Essa diretriz sustenta a distribuição da grade conforme o estado {estado} {citacoes_str}."
        )
    else:
        fontes = []
        sintese = "Nenhuma evidência dentro do limiar do porteiro foi encontrada na base para esta consulta."

    return foco, orientacao, sintese, fontes


def _chat_padrao():
    from app.modules.rag import llm

    return llm.research()


def _buscar_padrao(consulta: str, k: int = K_TRECHOS_RESEARCH) -> list[tuple[Document, float]]:
    return rag_repo.buscar(consulta, k=k)


class AgenteResearch:
    """Agente Bibliotecário e Montador de Contexto (`ContextoEstudante` + Curadoria RAG + Agenda)."""

    nome = "Research"

    def __init__(
        self,
        *,
        repositorio: RepositorioEstudante | None = None,
        provedor_agenda: ProvedorAgenda | None = None,
    ) -> None:
        self.repositorio = repositorio or RepositorioEstudante(":memory:")
        self.provedor_agenda = provedor_agenda

    def montar_contexto(
        self,
        estudante_id: str,
        semana_inicio: date,
        *,
        cronotipo: Cronotipo | None = None,
        sono_horario: tuple[time, time] | None = None,
        refeicoes_horario: tuple[time, time] | None = None,
        checkin: CheckIn | EscalasCheckIn | None = None,
        materiais: list[Material] | None = None,
        provedor_agenda: ProvedorAgenda | None = None,
        livres_override: list[Janela] | None = None,
        ocupados_override: list[Janela] | None = None,
        num_dias: int = 5,
        persistir: bool = True,
    ) -> ContextoEstudante:
        """Constrói e valida o contrato `ContextoEstudante` a partir do banco, check-in e agenda."""
        perfil = self.repositorio.obter_perfil(estudante_id)
        if perfil is None:
            perfil = PerfilEstudante(
                estudante_id=estudante_id,
                cronotipo=cronotipo or "matutino",
                sono=HorarioSono(
                    inicio=sono_horario[0] if sono_horario else time(22, 0),
                    fim=sono_horario[1] if sono_horario else time(6, 0),
                ),
                refeicoes=HorariosRefeicoes(
                    almoco=refeicoes_horario[0] if refeicoes_horario else time(12, 0),
                    jantar=refeicoes_horario[1] if refeicoes_horario else time(19, 0),
                ),
            )
            if persistir:
                self.repositorio.salvar_perfil(perfil)
        elif cronotipo is not None or sono_horario is not None or refeicoes_horario is not None:
            perfil = perfil.model_copy(
                update={
                    "cronotipo": cronotipo or perfil.cronotipo,
                    "sono": HorarioSono(
                        inicio=sono_horario[0] if sono_horario else perfil.sono.inicio,
                        fim=sono_horario[1] if sono_horario else perfil.sono.fim,
                    ),
                    "refeicoes": HorariosRefeicoes(
                        cafe=perfil.refeicoes.cafe,
                        almoco=refeicoes_horario[0] if refeicoes_horario else perfil.refeicoes.almoco,
                        jantar=refeicoes_horario[1] if refeicoes_horario else perfil.refeicoes.jantar,
                        duracao_min=perfil.refeicoes.duracao_min,
                        incluir_cafe=perfil.refeicoes.incluir_cafe,
                    ),
                }
            )
            if persistir:
                self.repositorio.salvar_perfil(perfil)

        # 1. Check-in e Índice de Capacidade
        if isinstance(checkin, EscalasCheckIn):
            checkin_obj = mapear_escalas_para_checkin(checkin)
        elif isinstance(checkin, CheckIn):
            checkin_obj = checkin
        else:
            ultimo = self.repositorio.obter_ultimo_checkin(estudante_id)
            checkin_obj = ultimo.checkin if ultimo else CheckIn(energia=3, horas_sono=7.0, estresse=2)

        indice = calcular_indice_capacidade(checkin_obj)

        # 2. Materiais acadêmicos
        if materiais is not None:
            materiais_lista = list(materiais)
            if persistir:
                self.repositorio.salvar_materiais(estudante_id, materiais_lista)
        else:
            materiais_lista = self.repositorio.listar_materiais(estudante_id)

        # 3. Janelas de sono e refeições para os dias da semana
        dias = dias_da_semana(semana_inicio, num_dias=num_dias)
        janelas_sono = expandir_janelas_sono(dias, perfil.sono.inicio, perfil.sono.fim)
        janelas_refeicoes = expandir_janelas_refeicoes(
            dias,
            almoco=perfil.refeicoes.almoco,
            jantar=perfil.refeicoes.jantar,
            cafe=perfil.refeicoes.cafe if perfil.refeicoes.incluir_cafe else None,
            duracao_min=perfil.refeicoes.duracao_min,
        )

        # 4. Leitura da Agenda (Google Calendar / ProvedorAgenda)
        agenda = provedor_agenda or self.provedor_agenda
        if livres_override is not None:
            janelas_livres = list(livres_override)
            janelas_ocupadas = list(ocupados_override or [])
        elif agenda is not None:
            janelas_livres, janelas_ocupadas = agenda.ler_janelas(dias[0], dias[-1])
            if ocupados_override is not None:
                janelas_ocupadas = list(ocupados_override)
        else:
            agenda_padrao = AgendaFake(
                ocupados=list(ocupados_override or []),
                sono=janelas_sono,
                refeicoes=janelas_refeicoes,
                expediente_estudo=(perfil.expediente_inicio, perfil.expediente_fim),
            )
            janelas_livres, janelas_ocupadas = agenda_padrao.ler_janelas(dias[0], dias[-1])

        # 5. Picos e vales circadianos
        janelas_picos, janelas_vales = derivar_picos_e_vales(
            perfil.cronotipo,
            dias,
            livres=janelas_livres,
            ocupados=janelas_ocupadas,
        )

        contexto = ContextoEstudante(
            estudante_id=estudante_id,
            cronotipo=perfil.cronotipo,
            semana_inicio=semana_inicio,
            livres=janelas_livres,
            ocupados=janelas_ocupadas,
            picos=janelas_picos,
            vales=janelas_vales,
            sono=janelas_sono,
            refeicoes=janelas_refeicoes,
            materiais=materiais_lista,
            checkin=checkin_obj,
            indice_capacidade=indice,
        )

        if persistir:
            self.repositorio.salvar_contexto(contexto)

        return contexto

    def pesquisar_evidencias(
        self,
        ctx: ContextoEstudante,
        *,
        k_por_consulta: int = 3,
        k_final: int = K_TRECHOS_RESEARCH,
        buscador: Callable[[str, int], list[tuple[Document, float]]] | None = None,
    ) -> tuple[list[str], list[EvidenciaRecuperada]]:
        """Executa buscas semânticas calibradas para o contexto do estudante e deduplica por (source, chunk_id)."""
        consultas = consultas_do_contexto(ctx)
        vistas: set[tuple[str, str]] = set()
        coletadas: list[EvidenciaRecuperada] = []

        for q in consultas:
            parciais = buscar_evidencias(
                q,
                k=k_por_consulta,
                apenas_conteudo=True,
                aplicar_porteiro=True,
                buscador=buscador,
            )
            for ev in parciais:
                chave = (ev.source, str(ev.chunk_id))
                if chave not in vistas:
                    vistas.add(chave)
                    coletadas.append(ev)

        coletadas.sort(key=lambda e: e.score_l2)
        return consultas, coletadas[:k_final]

    def curar_recomendacao(
        self,
        ctx: ContextoEstudante,
        *,
        chat: Any = None,
        buscador: Callable[[str, int], list[tuple[Document, float]]] | None = None,
    ) -> RelatoCuradoria:
        """Gera a curadoria bibliotecária do Research Agent com verificação determinística de citações."""
        inicio = time_mod.perf_counter()
        estado = classificar_estado_capacidade(ctx.indice_capacidade)
        consultas, evidencias = self.pesquisar_evidencias(ctx, buscador=buscador)

        relato = RelatoCuradoria(
            estudante_id=ctx.estudante_id,
            estado_capacidade=estado,
            consultas=consultas,
            evidencias=evidencias,
        )

        if not evidencias:
            foco, orient, sint, fontes = _sintese_deterministica(ctx, evidencias)
            relato.foco_recomendado = foco
            relato.orientacao_circadiana = orient
            relato.sintese_evidencias = sint
            relato.fontes_citadas = fontes
            relato.motivo_fallback = "nenhum trecho aprovado pelo porteiro"
            relato.segundos = round(time_mod.perf_counter() - inicio, 2)
            return relato

        trechos_docs = [
            Document(
                page_content=e.texto,
                metadata={"source": f"../api/data/{e.source}", "chunk_id": e.chunk_id},
            )
            for e in evidencias
        ]

        try:
            modelo_chat = chat or _chat_padrao()
            prompt = montar_prompt_research(ctx, trechos_docs)
            relato.bruto = modelo_chat.invoke(prompt).content
            saida = SaidaResearchLLM.model_validate_json(relato.bruto)
        except ValidationError as exc:
            foco, orient, sint, fontes = _sintese_deterministica(ctx, evidencias)
            relato.foco_recomendado, relato.orientacao_circadiana, relato.sintese_evidencias = foco, orient, sint
            relato.fontes_citadas = fontes
            relato.motivo_fallback = f"JSON fora do esquema: {exc.error_count()} erro(s)"
            relato.segundos = round(time_mod.perf_counter() - inicio, 2)
            logger.warning("Research: saída fora do esquema para %s; usando síntese determinística", ctx.estudante_id)
            return relato
        except Exception as exc:
            foco, orient, sint, fontes = _sintese_deterministica(ctx, evidencias)
            relato.foco_recomendado, relato.orientacao_circadiana, relato.sintese_evidencias = foco, orient, sint
            relato.fontes_citadas = fontes
            relato.motivo_fallback = f"falha ao chamar o LLM: {type(exc).__name__}"
            relato.segundos = round(time_mod.perf_counter() - inicio, 2)
            logger.warning("Research: falha no LLM (%s); usando síntese determinística", exc)
            return relato

        texto_verificado, ver = verificar(saida.sintese_evidencias, trechos_docs)
        relato.citacoes_removidas = ver.fora_do_contexto
        if not ver.citadas:
            foco, orient, sint, fontes = _sintese_deterministica(ctx, evidencias)
            relato.foco_recomendado = saida.foco_recomendado.strip() or foco
            relato.orientacao_circadiana = saida.orientacao_circadiana.strip() or orient
            relato.sintese_evidencias = sint
            relato.fontes_citadas = fontes
            relato.motivo_fallback = "nenhuma citação válida mantida pelo verificador"
            relato.segundos = round(time_mod.perf_counter() - inicio, 2)
            return relato

        relato.usou_llm = True
        relato.foco_recomendado = saida.foco_recomendado.strip()
        relato.orientacao_circadiana = saida.orientacao_circadiana.strip()
        relato.sintese_evidencias = texto_verificado
        relato.fontes_citadas = _fontes_resolvidas(ver.citadas, trechos_docs)
        relato.segundos = round(time_mod.perf_counter() - inicio, 2)
        return relato

    def sincronizar_agenda(
        self,
        blocos: list[BlocoEstudo],
        *,
        provedor_agenda: ProvedorAgenda | None = None,
    ) -> list[str]:
        """Grava os blocos de estudo aprovados pelo Validation no Google Calendar (`ProvedorAgenda`)."""
        agenda = provedor_agenda or self.provedor_agenda
        if agenda is None:
            raise ValueError("Nenhum ProvedorAgenda configurado para sincronizar os blocos de estudo.")
        return agenda.gravar_blocos(blocos)
