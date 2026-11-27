"""Camada de persistência do Banco do Estudante ([2.1] Issue #40).

Armazena e consulta dados acadêmicos, perfil circadiano base (cronotipo, horários habituais de
sono e refeições), acervo de materiais/disciplinas com prazos e histórico de check-ins diários.

Utiliza SQLite nativo (`sqlite3`) com validação estrita via contratos Pydantic (`Contrato` com
`extra="forbid"`), suportando tanto persistência em arquivo (`api/data/estudantes.db`) quanto
banco em memória (`:memory:`) para testes determinísticos no CI.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.core.config import API_DIR
from app.modules.agentes.contratos import (
    CargaCognitiva,
    CheckIn,
    ContextoEstudante,
    Contrato,
    Cronotipo,
    Material,
)

DEFAULT_DB_PATH = API_DIR / "data" / "estudantes.db"


class HorarioSono(Contrato):
    """Horário habitual de sono diário informado no onboarding (pode cruzar a meia-noite)."""

    inicio: time = time(22, 0)
    fim: time = time(6, 0)


class HorariosRefeicoes(Contrato):
    """Horários habituais de início das refeições (cada refeição padrão dura 60 min)."""

    cafe: time | None = time(7, 0)
    almoco: time = time(12, 0)
    jantar: time = time(19, 0)
    duracao_min: int = Field(default=60, ge=15, le=180)
    incluir_cafe: bool = False


class PerfilEstudante(Contrato):
    """Dados cadastrais e perfil circadiano base do estudante."""

    estudante_id: str = Field(min_length=1)
    nome: str = "Estudante"
    cronotipo: Cronotipo = "matutino"
    sono: HorarioSono = Field(default_factory=HorarioSono)
    refeicoes: HorariosRefeicoes = Field(default_factory=HorariosRefeicoes)
    expediente_inicio: time = time(7, 0)
    expediente_fim: time = time(18, 0)
    agenda_conectada: bool = False


class MetaEstudo(Contrato):
    """Meta acadêmica ou edital vinculado ao estudante."""

    id: str = Field(min_length=1)
    estudante_id: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    horas_semanais_meta: float = Field(gt=0, le=80)
    prazo_final: date | None = None
    prioridade: int = Field(default=3, ge=1, le=5)
    concluida: bool = False


class RegistroCheckIn(Contrato):
    """Registro histórico de um check-in diário do estudante."""

    estudante_id: str = Field(min_length=1)
    data_referencia: date
    checkin: CheckIn
    indice_capacidade: float = Field(ge=0.0, le=1.0)
    humor: int | None = Field(default=None, ge=1, le=5)
    qualidade_sono: int | None = Field(default=None, ge=1, le=5)
    fadiga: int | None = Field(default=None, ge=1, le=5)


class RegistroHistoricoEstudo(Contrato):
    """Registro de sessão/bloco de estudo concluído pelo estudante."""

    id: str = Field(min_length=1)
    estudante_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)
    dia: date
    minutos_estudados: int = Field(gt=0)
    tecnica: str = ""
    concluido: bool = True


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS estudantes (
    estudante_id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    cronotipo TEXT NOT NULL,
    sono_inicio TEXT NOT NULL,
    sono_fim TEXT NOT NULL,
    refeicao_cafe TEXT,
    refeicao_almoco TEXT NOT NULL,
    refeicao_jantar TEXT NOT NULL,
    refeicao_duracao_min INTEGER NOT NULL DEFAULT 60,
    refeicao_incluir_cafe INTEGER NOT NULL DEFAULT 0,
    expediente_inicio TEXT NOT NULL DEFAULT '07:00',
    expediente_fim TEXT NOT NULL DEFAULT '18:00',
    agenda_conectada INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materiais (
    estudante_id TEXT NOT NULL,
    id TEXT NOT NULL,
    disciplina TEXT NOT NULL,
    titulo TEXT NOT NULL,
    carga TEXT NOT NULL,
    horas_estimadas REAL NOT NULL,
    dificuldade INTEGER NOT NULL,
    prazo TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (estudante_id, id),
    FOREIGN KEY (estudante_id) REFERENCES estudantes(estudante_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metas_estudo (
    estudante_id TEXT NOT NULL,
    id TEXT NOT NULL,
    titulo TEXT NOT NULL,
    horas_semanais_meta REAL NOT NULL,
    prazo_final TEXT,
    prioridade INTEGER NOT NULL DEFAULT 3,
    concluida INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (estudante_id, id),
    FOREIGN KEY (estudante_id) REFERENCES estudantes(estudante_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estudante_id TEXT NOT NULL,
    data_referencia TEXT NOT NULL,
    energia INTEGER NOT NULL,
    horas_sono REAL NOT NULL,
    estresse INTEGER NOT NULL,
    indice_capacidade REAL NOT NULL,
    humor INTEGER,
    qualidade_sono INTEGER,
    fadiga INTEGER,
    criado_em TEXT NOT NULL,
    FOREIGN KEY (estudante_id) REFERENCES estudantes(estudante_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS historico_estudo (
    estudante_id TEXT NOT NULL,
    id TEXT NOT NULL,
    material_id TEXT NOT NULL,
    dia TEXT NOT NULL,
    minutos_estudados INTEGER NOT NULL,
    tecnica TEXT NOT NULL DEFAULT '',
    concluido INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (estudante_id, id),
    FOREIGN KEY (estudante_id) REFERENCES estudantes(estudante_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS contextos_snapshot (
    estudante_id TEXT NOT NULL,
    semana_inicio TEXT NOT NULL,
    contexto_json TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (estudante_id, semana_inicio)
);
"""


def _fmt_time(t: time | None) -> str | None:
    if t is None:
        return None
    return t.strftime("%H:%M")


def _parse_time(valor: str | None) -> time | None:
    if not valor:
        return None
    return time.fromisoformat(valor)


class RepositorioEstudante:
    """Repositório SQLite para persistência dos dados do estudante, materiais, metas e check-ins."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._memoria_conn: sqlite3.Connection | None = None
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        else:
            self._memoria_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memoria_conn.row_factory = sqlite3.Row
            self._memoria_conn.execute("PRAGMA foreign_keys = ON;")
        self._inicializar_banco()

    def _conectar(self) -> sqlite3.Connection:
        if self._memoria_conn is not None:
            return self._memoria_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _fechar_se_arquivo(self, conn: sqlite3.Connection) -> None:
        if self._memoria_conn is None:
            conn.close()

    def _inicializar_banco(self) -> None:
        conn = self._conectar()
        try:
            with conn:
                conn.executescript(_SCHEMA_SQL)
        finally:
            self._fechar_se_arquivo(conn)

    # ---------------------------------------------------------------- Perfil do Estudante
    def salvar_perfil(self, perfil: PerfilEstudante) -> PerfilEstudante:
        agora = datetime.now(timezone.utc).isoformat()
        conn = self._conectar()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO estudantes (
                        estudante_id, nome, cronotipo, sono_inicio, sono_fim,
                        refeicao_cafe, refeicao_almoco, refeicao_jantar,
                        refeicao_duracao_min, refeicao_incluir_cafe,
                        expediente_inicio, expediente_fim, agenda_conectada, atualizado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(estudante_id) DO UPDATE SET
                        nome = excluded.nome,
                        cronotipo = excluded.cronotipo,
                        sono_inicio = excluded.sono_inicio,
                        sono_fim = excluded.sono_fim,
                        refeicao_cafe = excluded.refeicao_cafe,
                        refeicao_almoco = excluded.refeicao_almoco,
                        refeicao_jantar = excluded.refeicao_jantar,
                        refeicao_duracao_min = excluded.refeicao_duracao_min,
                        refeicao_incluir_cafe = excluded.refeicao_incluir_cafe,
                        expediente_inicio = excluded.expediente_inicio,
                        expediente_fim = excluded.expediente_fim,
                        agenda_conectada = excluded.agenda_conectada,
                        atualizado_em = excluded.atualizado_em
                    """,
                    (
                        perfil.estudante_id,
                        perfil.nome,
                        perfil.cronotipo,
                        _fmt_time(perfil.sono.inicio),
                        _fmt_time(perfil.sono.fim),
                        _fmt_time(perfil.refeicoes.cafe),
                        _fmt_time(perfil.refeicoes.almoco),
                        _fmt_time(perfil.refeicoes.jantar),
                        perfil.refeicoes.duracao_min,
                        int(perfil.refeicoes.incluir_cafe),
                        _fmt_time(perfil.expediente_inicio),
                        _fmt_time(perfil.expediente_fim),
                        int(perfil.agenda_conectada),
                        agora,
                    ),
                )
            return perfil
        finally:
            self._fechar_se_arquivo(conn)

    def obter_perfil(self, estudante_id: str) -> PerfilEstudante | None:
        conn = self._conectar()
        try:
            row = conn.execute(
                "SELECT * FROM estudantes WHERE estudante_id = ?",
                (estudante_id,),
            ).fetchone()
            if row is None:
                return None
            return PerfilEstudante(
                estudante_id=row["estudante_id"],
                nome=row["nome"],
                cronotipo=row["cronotipo"],
                sono=HorarioSono(
                    inicio=_parse_time(row["sono_inicio"]) or time(22, 0),
                    fim=_parse_time(row["sono_fim"]) or time(6, 0),
                ),
                refeicoes=HorariosRefeicoes(
                    cafe=_parse_time(row["refeicao_cafe"]),
                    almoco=_parse_time(row["refeicao_almoco"]) or time(12, 0),
                    jantar=_parse_time(row["refeicao_jantar"]) or time(19, 0),
                    duracao_min=int(row["refeicao_duracao_min"]),
                    incluir_cafe=bool(row["refeicao_incluir_cafe"]),
                ),
                expediente_inicio=_parse_time(row["expediente_inicio"]) or time(7, 0),
                expediente_fim=_parse_time(row["expediente_fim"]) or time(18, 0),
                agenda_conectada=bool(row["agenda_conectada"]),
            )
        finally:
            self._fechar_se_arquivo(conn)

    def listar_perfis(self) -> list[PerfilEstudante]:
        conn = self._conectar()
        try:
            rows = conn.execute("SELECT estudante_id FROM estudantes ORDER BY estudante_id").fetchall()
            ids = [r["estudante_id"] for r in rows]
        finally:
            self._fechar_se_arquivo(conn)
        return [p for eid in ids if (p := self.obter_perfil(eid)) is not None]

    # ---------------------------------------------------------------- Materiais Acadêmicos
    def salvar_materiais(
        self,
        estudante_id: str,
        materiais: list[Material],
        *,
        substituir: bool = True,
    ) -> list[Material]:
        """Persiste a lista de materiais do estudante mantendo a ordem de inserção."""
        if self.obter_perfil(estudante_id) is None:
            self.salvar_perfil(PerfilEstudante(estudante_id=estudante_id))

        conn = self._conectar()
        try:
            with conn:
                if substituir:
                    conn.execute("DELETE FROM materiais WHERE estudante_id = ?", (estudante_id,))
                for idx, m in enumerate(materiais):
                    conn.execute(
                        """
                        INSERT INTO materiais (
                            estudante_id, id, disciplina, titulo, carga,
                            horas_estimadas, dificuldade, prazo, ordem
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(estudante_id, id) DO UPDATE SET
                            disciplina = excluded.disciplina,
                            titulo = excluded.titulo,
                            carga = excluded.carga,
                            horas_estimadas = excluded.horas_estimadas,
                            dificuldade = excluded.dificuldade,
                            prazo = excluded.prazo,
                            ordem = excluded.ordem
                        """,
                        (
                            estudante_id,
                            m.id,
                            m.disciplina,
                            m.titulo,
                            m.carga,
                            float(m.horas_estimadas),
                            int(m.dificuldade),
                            m.prazo.isoformat() if m.prazo else None,
                            idx,
                        ),
                    )
            return list(materiais)
        finally:
            self._fechar_se_arquivo(conn)

    def listar_materiais(self, estudante_id: str) -> list[Material]:
        conn = self._conectar()
        try:
            rows = conn.execute(
                "SELECT * FROM materiais WHERE estudante_id = ? ORDER BY ordem ASC, id ASC",
                (estudante_id,),
            ).fetchall()
            return [
                Material(
                    id=r["id"],
                    disciplina=r["disciplina"],
                    titulo=r["titulo"],
                    carga=r["carga"],
                    horas_estimadas=float(r["horas_estimadas"]),
                    dificuldade=int(r["dificuldade"]),
                    prazo=date.fromisoformat(r["prazo"]) if r["prazo"] else None,
                )
                for r in rows
            ]
        finally:
            self._fechar_se_arquivo(conn)

    def remover_material(self, estudante_id: str, material_id: str) -> bool:
        conn = self._conectar()
        try:
            with conn:
                cur = conn.execute(
                    "DELETE FROM materiais WHERE estudante_id = ? AND id = ?",
                    (estudante_id, material_id),
                )
                return cur.rowcount > 0
        finally:
            self._fechar_se_arquivo(conn)

    # ---------------------------------------------------------------- Metas de Estudo
    def salvar_meta(self, meta: MetaEstudo) -> MetaEstudo:
        if self.obter_perfil(meta.estudante_id) is None:
            self.salvar_perfil(PerfilEstudante(estudante_id=meta.estudante_id))

        conn = self._conectar()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO metas_estudo (
                        estudante_id, id, titulo, horas_semanais_meta,
                        prazo_final, prioridade, concluida
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(estudante_id, id) DO UPDATE SET
                        titulo = excluded.titulo,
                        horas_semanais_meta = excluded.horas_semanais_meta,
                        prazo_final = excluded.prazo_final,
                        prioridade = excluded.prioridade,
                        concluida = excluded.concluida
                    """,
                    (
                        meta.estudante_id,
                        meta.id,
                        meta.titulo,
                        float(meta.horas_semanais_meta),
                        meta.prazo_final.isoformat() if meta.prazo_final else None,
                        int(meta.prioridade),
                        int(meta.concluida),
                    ),
                )
            return meta
        finally:
            self._fechar_se_arquivo(conn)

    def listar_metas(self, estudante_id: str) -> list[MetaEstudo]:
        conn = self._conectar()
        try:
            rows = conn.execute(
                "SELECT * FROM metas_estudo WHERE estudante_id = ? ORDER BY prioridade DESC, id ASC",
                (estudante_id,),
            ).fetchall()
            return [
                MetaEstudo(
                    id=r["id"],
                    estudante_id=r["estudante_id"],
                    titulo=r["titulo"],
                    horas_semanais_meta=float(r["horas_semanais_meta"]),
                    prazo_final=date.fromisoformat(r["prazo_final"]) if r["prazo_final"] else None,
                    prioridade=int(r["prioridade"]),
                    concluida=bool(r["concluida"]),
                )
                for r in rows
            ]
        finally:
            self._fechar_se_arquivo(conn)

    # ---------------------------------------------------------------- Check-ins e Histórico
    def registrar_checkin(self, registro: RegistroCheckIn) -> RegistroCheckIn:
        if self.obter_perfil(registro.estudante_id) is None:
            self.salvar_perfil(PerfilEstudante(estudante_id=registro.estudante_id))

        agora = datetime.now(timezone.utc).isoformat()
        conn = self._conectar()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO checkins (
                        estudante_id, data_referencia, energia, horas_sono, estresse,
                        indice_capacidade, humor, qualidade_sono, fadiga, criado_em
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        registro.estudante_id,
                        registro.data_referencia.isoformat(),
                        int(registro.checkin.energia),
                        float(registro.checkin.horas_sono),
                        int(registro.checkin.estresse),
                        float(registro.indice_capacidade),
                        registro.humor,
                        registro.qualidade_sono,
                        registro.fadiga,
                        agora,
                    ),
                )
            return registro
        finally:
            self._fechar_se_arquivo(conn)

    def obter_ultimo_checkin(self, estudante_id: str) -> RegistroCheckIn | None:
        conn = self._conectar()
        try:
            row = conn.execute(
                """
                SELECT * FROM checkins
                WHERE estudante_id = ?
                ORDER BY data_referencia DESC, id DESC
                LIMIT 1
                """,
                (estudante_id,),
            ).fetchone()
            if row is None:
                return None
            return RegistroCheckIn(
                estudante_id=row["estudante_id"],
                data_referencia=date.fromisoformat(row["data_referencia"]),
                checkin=CheckIn(
                    energia=int(row["energia"]),
                    horas_sono=float(row["horas_sono"]),
                    estresse=int(row["estresse"]),
                ),
                indice_capacidade=float(row["indice_capacidade"]),
                humor=row["humor"],
                qualidade_sono=row["qualidade_sono"],
                fadiga=row["fadiga"],
            )
        finally:
            self._fechar_se_arquivo(conn)

    def listar_checkins(self, estudante_id: str, limite: int = 30) -> list[RegistroCheckIn]:
        conn = self._conectar()
        try:
            rows = conn.execute(
                """
                SELECT * FROM checkins
                WHERE estudante_id = ?
                ORDER BY data_referencia DESC, id DESC
                LIMIT ?
                """,
                (estudante_id, limite),
            ).fetchall()
            return [
                RegistroCheckIn(
                    estudante_id=r["estudante_id"],
                    data_referencia=date.fromisoformat(r["data_referencia"]),
                    checkin=CheckIn(
                        energia=int(r["energia"]),
                        horas_sono=float(r["horas_sono"]),
                        estresse=int(r["estresse"]),
                    ),
                    indice_capacidade=float(r["indice_capacidade"]),
                    humor=r["humor"],
                    qualidade_sono=r["qualidade_sono"],
                    fadiga=r["fadiga"],
                )
                for r in rows
            ]
        finally:
            self._fechar_se_arquivo(conn)

    def registrar_sessao_estudo(self, sessao: RegistroHistoricoEstudo) -> RegistroHistoricoEstudo:
        if self.obter_perfil(sessao.estudante_id) is None:
            self.salvar_perfil(PerfilEstudante(estudante_id=sessao.estudante_id))

        conn = self._conectar()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO historico_estudo (
                        estudante_id, id, material_id, dia, minutos_estudados, tecnica, concluido
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(estudante_id, id) DO UPDATE SET
                        material_id = excluded.material_id,
                        dia = excluded.dia,
                        minutos_estudados = excluded.minutos_estudados,
                        tecnica = excluded.tecnica,
                        concluido = excluded.concluido
                    """,
                    (
                        sessao.estudante_id,
                        sessao.id,
                        sessao.material_id,
                        sessao.dia.isoformat(),
                        int(sessao.minutos_estudados),
                        sessao.tecnica,
                        int(sessao.concluido),
                    ),
                )
            return sessao
        finally:
            self._fechar_se_arquivo(conn)

    def listar_historico_estudo(self, estudante_id: str) -> list[RegistroHistoricoEstudo]:
        conn = self._conectar()
        try:
            rows = conn.execute(
                "SELECT * FROM historico_estudo WHERE estudante_id = ? ORDER BY dia DESC, id ASC",
                (estudante_id,),
            ).fetchall()
            return [
                RegistroHistoricoEstudo(
                    id=r["id"],
                    estudante_id=r["estudante_id"],
                    material_id=r["material_id"],
                    dia=date.fromisoformat(r["dia"]),
                    minutos_estudados=int(r["minutos_estudados"]),
                    tecnica=r["tecnica"],
                    concluido=bool(r["concluido"]),
                )
                for r in rows
            ]
        finally:
            self._fechar_se_arquivo(conn)

    # ---------------------------------------------------------------- Snapshots de ContextoEstudante
    def salvar_contexto(self, contexto: ContextoEstudante) -> ContextoEstudante:
        """Salva um ContextoEstudante completo e sincroniza materiais e check-in no banco."""
        if self.obter_perfil(contexto.estudante_id) is None:
            self.salvar_perfil(
                PerfilEstudante(
                    estudante_id=contexto.estudante_id,
                    cronotipo=contexto.cronotipo,
                )
            )
        self.salvar_materiais(contexto.estudante_id, contexto.materiais, substituir=True)
        self.registrar_checkin(
            RegistroCheckIn(
                estudante_id=contexto.estudante_id,
                data_referencia=contexto.semana_inicio,
                checkin=contexto.checkin,
                indice_capacidade=contexto.indice_capacidade,
            )
        )

        agora = datetime.now(timezone.utc).isoformat()
        conn = self._conectar()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO contextos_snapshot (
                        estudante_id, semana_inicio, contexto_json, atualizado_em
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(estudante_id, semana_inicio) DO UPDATE SET
                        contexto_json = excluded.contexto_json,
                        atualizado_em = excluded.atualizado_em
                    """,
                    (
                        contexto.estudante_id,
                        contexto.semana_inicio.isoformat(),
                        contexto.model_dump_json(),
                        agora,
                    ),
                )
            return contexto
        finally:
            self._fechar_se_arquivo(conn)

    def obter_contexto(self, estudante_id: str, semana_inicio: date) -> ContextoEstudante | None:
        conn = self._conectar()
        try:
            row = conn.execute(
                """
                SELECT contexto_json FROM contextos_snapshot
                WHERE estudante_id = ? AND semana_inicio = ?
                """,
                (estudante_id, semana_inicio.isoformat()),
            ).fetchone()
            if row is None:
                return None
            return ContextoEstudante.model_validate_json(row["contexto_json"])
        finally:
            self._fechar_se_arquivo(conn)
