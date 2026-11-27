"""Integração com Google Calendar: leitura de disponibilidade e escrita de blocos ([2.4] Issue #15).

Implementa o protocolo `ProvedorAgenda` definido em `api/app/modules/agentes/contratos.py`:
  - `ler_janelas(inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]`
  - `gravar_blocos(blocos: list[BlocoEstudo]) -> list[str]`

Oferece duas implementações intercambiáveis:
  1. `GoogleCalendarProvedor`: cliente HTTP REST para a API v3 do Google Calendar
     (`https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events`), validando
     entradas e saídas com contratos Pydantic (`EventoGoogleCalendar`, `PayloadEventoCalendar`).
     Inclui divisão automática de eventos que cruzam a meia-noite e recorte do tempo disponível
     contra compromissos, sono e refeições.
  2. `AgendaFake`: implementação determinística em memória para testes unitários, CI e modo
     offline/demonstração.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta
from typing import Any

from pydantic import Field

from app.modules.agentes.analysis.janelas import hora, minutos, por_dia, subtrair, unir
from app.modules.agentes.contratos import BlocoEstudo, Contrato, Janela, ProvedorAgenda

logger = logging.getLogger("studybuddy.research.agenda")

FIM_DIA_MIN = 23 * 60 + 59


class DataHoraCalendar(Contrato):
    """Estrutura `start` / `end` da API v3 do Google Calendar."""

    dateTime: str | None = None
    date: str | None = None
    timeZone: str | None = None


class EventoGoogleCalendar(Contrato):
    """Representação validada de um evento retornado pela API do Google Calendar."""

    id: str = ""
    summary: str = ""
    description: str = ""
    status: str = "confirmed"
    start: DataHoraCalendar
    end: DataHoraCalendar


class PayloadEventoCalendar(Contrato):
    """Payload enviado no POST de criação de blocos de estudo no Google Calendar."""

    summary: str = Field(min_length=1)
    description: str = ""
    start: DataHoraCalendar
    end: DataHoraCalendar


def _iterar_dias(inicio: date, fim: date) -> list[date]:
    if fim < inicio:
        return []
    total = (fim - inicio).days + 1
    return [inicio + timedelta(days=i) for i in range(total)]


def quebrar_evento_em_janelas(
    dt_inicio: datetime,
    dt_fim: datetime,
    *,
    dia_min: date | None = None,
    dia_max: date | None = None,
) -> list[Janela]:
    """Converte um intervalo `[dt_inicio, dt_fim)` em uma ou mais `Janela`, sem cruzar a meia-noite."""
    if dt_fim <= dt_inicio:
        return []

    janelas: list[Janela] = []
    cursor = dt_inicio
    while cursor.date() < dt_fim.date():
        dia_atual = cursor.date()
        ini_t = time(cursor.hour, cursor.minute)
        if ini_t < time(23, 59):
            if (dia_min is None or dia_atual >= dia_min) and (dia_max is None or dia_atual <= dia_max):
                janelas.append(Janela(dia=dia_atual, inicio=ini_t, fim=time(23, 59)))
        cursor = datetime.combine(dia_atual + timedelta(days=1), time(0, 0), tzinfo=dt_inicio.tzinfo)

    dia_final = dt_fim.date()
    ini_final = time(cursor.hour, cursor.minute)
    fim_final = time(dt_fim.hour, dt_fim.minute)
    if ini_final < fim_final:
        if (dia_min is None or dia_final >= dia_min) and (dia_max is None or dia_final <= dia_max):
            janelas.append(Janela(dia=dia_final, inicio=ini_final, fim=fim_final))

    return janelas


def parse_evento_google(
    item: dict[str, Any],
    *,
    dia_min: date | None = None,
    dia_max: date | None = None,
) -> list[Janela]:
    """Valida um item bruto do Google Calendar e o transforma em objetos `Janela` (`ocupados`)."""
    ignorar_chaves = {
        k: v
        for k, v in item.items()
        if k in {"id", "summary", "description", "status", "start", "end"}
    }
    for campo in ("start", "end"):
        if isinstance(ignorar_chaves.get(campo), dict):
            ignorar_chaves[campo] = {
                k: v for k, v in ignorar_chaves[campo].items() if k in {"dateTime", "date", "timeZone"}
            }

    ev = EventoGoogleCalendar.model_validate(ignorar_chaves)
    if ev.status == "cancelled":
        return []

    if ev.start.dateTime and ev.end.dateTime:
        dt_ini = datetime.fromisoformat(ev.start.dateTime.replace("Z", "+00:00"))
        dt_fim = datetime.fromisoformat(ev.end.dateTime.replace("Z", "+00:00"))
        return quebrar_evento_em_janelas(dt_ini, dt_fim, dia_min=dia_min, dia_max=dia_max)

    if ev.start.date and ev.end.date:
        d_ini = date.fromisoformat(ev.start.date)
        d_fim = date.fromisoformat(ev.end.date)
        janelas: list[Janela] = []
        cursor = d_ini
        while cursor < d_fim:
            if (dia_min is None or cursor >= dia_min) and (dia_max is None or cursor <= dia_max):
                janelas.append(Janela(dia=cursor, inicio=time(0, 0), fim=time(23, 59)))
            cursor += timedelta(days=1)
        return janelas

    return []


def derivar_janelas_livres(
    dias: Iterable[date],
    *,
    ocupados: Iterable[Janela] = (),
    sono: Iterable[Janela] = (),
    refeicoes: Iterable[Janela] = (),
    expediente_estudo: tuple[time, time] = (time(7, 0), time(18, 0)),
) -> list[Janela]:
    """Deriva as janelas `livres` do dia recortando o horário ativo contra sono, refeições e opcionalmente ocupados.

    Nota de compatibilidade com os contratos de `Analysis` e `Validation`:
      Em `api/app/modules/agentes/analysis/janelas.py` (`disponivel(ctx)`), o Analysis subtrai
      `ocupados`, `sono` e `refeicoes` de `ctx.livres`. Nas fixtures da [0.2], `livres` representa as
      faixas de estudo do dia já recortadas pelas refeições e sono, enquanto `ocupados` guarda os
      compromissos pontuais do Google Calendar.
    """
    ini_base = minutos(expediente_estudo[0])
    fim_base = minutos(expediente_estudo[1])
    if ini_base >= fim_base:
        ini_base, fim_base = 7 * 60, 18 * 60

    cortes_por_dia = por_dia([*sono, *refeicoes])
    ocupados_por_dia = por_dia(ocupados)

    livres: list[Janela] = []
    for dia in dias:
        base_dia = [(ini_base, fim_base)]
        cortes = unir([*cortes_por_dia.get(dia, []), *ocupados_por_dia.get(dia, [])])
        for a, b in subtrair(base_dia, cortes):
            if a < b:
                livres.append(Janela(dia=dia, inicio=hora(a), fim=hora(b)))
    return livres


def montar_payload_bloco(
    bloco: BlocoEstudo,
    *,
    fuso_horario: str = "America/Sao_Paulo",
    offset_iso: str = "-03:00",
) -> PayloadEventoCalendar:
    """Converte um `BlocoEstudo` aprovado em um `PayloadEventoCalendar` validado por Pydantic."""
    dt_ini = f"{bloco.dia.isoformat()}T{bloco.inicio.strftime('%H:%M:%S')}{offset_iso}"
    dt_fim = f"{bloco.dia.isoformat()}T{bloco.fim.strftime('%H:%M:%S')}{offset_iso}"

    fontes_txt = ", ".join(bloco.fontes) if bloco.fontes else "Base científica StudyBuddy"
    descricao = (
        f"Material: {bloco.material_id} ({bloco.disciplina})\n"
        f"Carga cognitiva: {bloco.carga} | Técnica: {bloco.tecnica}\n"
        f"Ritmo: {bloco.foco_min} min foco + {bloco.pausa_min} min pausa\n"
        f"Justificativa: {bloco.justificativa or 'Alocação otimizada pelo perfil circadiano.'}\n"
        f"Fontes: {fontes_txt}"
    )

    return PayloadEventoCalendar(
        summary=f"[StudyBuddy] {bloco.disciplina} — {bloco.tecnica}",
        description=descricao,
        start=DataHoraCalendar(dateTime=dt_ini, timeZone=fuso_horario),
        end=DataHoraCalendar(dateTime=dt_fim, timeZone=fuso_horario),
    )


class AgendaFake(ProvedorAgenda):
    """Implementação determinística em memória do protocolo `ProvedorAgenda` para testes e modo offline."""

    def __init__(
        self,
        *,
        livres: list[Janela] | None = None,
        ocupados: list[Janela] | None = None,
        sono: list[Janela] | None = None,
        refeicoes: list[Janela] | None = None,
        expediente_estudo: tuple[time, time] = (time(7, 0), time(18, 0)),
    ) -> None:
        self._livres_fixos = list(livres) if livres is not None else None
        self._ocupados = list(ocupados or [])
        self._sono = list(sono or [])
        self._refeicoes = list(refeicoes or [])
        self._expediente = expediente_estudo
        self.blocos_gravados: list[BlocoEstudo] = []
        self.payloads_gravados: list[PayloadEventoCalendar] = []

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        ocupados_periodo = [j for j in self._ocupados if inicio <= j.dia <= fim]
        if self._livres_fixos is not None:
            livres_periodo = [j for j in self._livres_fixos if inicio <= j.dia <= fim]
            return livres_periodo, ocupados_periodo

        dias = _iterar_dias(inicio, fim)
        livres_derivados = derivar_janelas_livres(
            dias,
            ocupados=ocupados_periodo,
            sono=self._sono,
            refeicoes=self._refeicoes,
            expediente_estudo=self._expediente,
        )
        return livres_derivados, ocupados_periodo

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        ids: list[str] = []
        for idx, bloco in enumerate(blocos, start=len(self.blocos_gravados) + 1):
            payload = montar_payload_bloco(bloco)
            self.blocos_gravados.append(bloco)
            self.payloads_gravados.append(payload)
            ids.append(f"gcal-evt-{idx:03d}-{bloco.id}")
        return ids


class GoogleCalendarProvedor(ProvedorAgenda):
    """Cliente da API v3 do Google Calendar compatível com o contrato `ProvedorAgenda`."""

    BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        *,
        calendar_id: str = "primary",
        access_token: str | None = None,
        fuso_horario: str = "America/Sao_Paulo",
        offset_iso: str = "-03:00",
        expediente_estudo: tuple[time, time] = (time(7, 0), time(18, 0)),
        sono: list[Janela] | None = None,
        refeicoes: list[Janela] | None = None,
        http_client: Callable[[str, str, dict[str, Any] | None, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.calendar_id = calendar_id
        self.access_token = access_token or ""
        self.fuso_horario = fuso_horario
        self.offset_iso = offset_iso
        self.expediente_estudo = expediente_estudo
        self._sono = list(sono or [])
        self._refeicoes = list(refeicoes or [])
        self._http_client = http_client or self._requisicao_padrao

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    @staticmethod
    def _requisicao_padrao(
        metodo: str,
        url: str,
        corpo: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
        with urllib.request.urlopen(req, timeout=15) as resp:
            conteudo = resp.read().decode("utf-8")
            return json.loads(conteudo) if conteudo else {}

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        """Consulta eventos no Google Calendar entre `inicio` e `fim` e devolve `(livres, ocupados)`."""
        time_min = f"{inicio.isoformat()}T00:00:00{self.offset_iso}"
        time_max = f"{fim.isoformat()}T23:59:59{self.offset_iso}"
        params = urllib.parse.urlencode(
            {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
            }
        )
        cal_encoded = urllib.parse.quote(self.calendar_id, safe="")
        url = f"{self.BASE_URL}/calendars/{cal_encoded}/events?{params}"

        resposta = self._http_client("GET", url, None, self._headers())
        itens = resposta.get("items", [])

        ocupados: list[Janela] = []
        for item in itens:
            ocupados.extend(parse_evento_google(item, dia_min=inicio, dia_max=fim))

        dias = _iterar_dias(inicio, fim)
        livres = derivar_janelas_livres(
            dias,
            ocupados=ocupados,
            sono=self._sono,
            refeicoes=self._refeicoes,
            expediente_estudo=self.expediente_estudo,
        )
        return livres, ocupados

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        """Cria um evento no Google Calendar para cada `BlocoEstudo` e devolve os IDs gerados."""
        cal_encoded = urllib.parse.quote(self.calendar_id, safe="")
        url = f"{self.BASE_URL}/calendars/{cal_encoded}/events"
        ids_criados: list[str] = []

        for bloco in blocos:
            payload = montar_payload_bloco(
                bloco,
                fuso_horario=self.fuso_horario,
                offset_iso=self.offset_iso,
            )
            resposta = self._http_client(
                "POST",
                url,
                payload.model_dump(exclude_none=True),
                self._headers(),
            )
            evento_id = str(resposta.get("id") or f"gcal-{bloco.id}")
            ids_criados.append(evento_id)

        return ids_criados
