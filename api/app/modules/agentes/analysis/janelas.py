"""Aritmética de intervalos em minutos do dia, [ini, fim). Funções puras, sem LLM."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from typing import Iterable, Literal

from app.modules.agentes.contratos import ContextoEstudante, Janela

Tipo = Literal["pico", "vale", "neutro"]
Intervalo = tuple[int, int]


def minutos(t: time) -> int:
    return t.hour * 60 + t.minute


def hora(m: int) -> time:
    return time(m // 60, m % 60)


def por_dia(janelas: Iterable[Janela]) -> dict[date, list[Intervalo]]:
    dias: dict[date, list[Intervalo]] = defaultdict(list)
    for j in janelas:
        dias[j.dia].append((minutos(j.inicio), minutos(j.fim)))
    return {d: unir(v) for d, v in dias.items()}


def unir(intervalos: Iterable[Intervalo]) -> list[Intervalo]:
    """Ordena e junta intervalos que se tocam ou se sobrepõem."""
    out: list[Intervalo] = []
    for a, b in sorted(intervalos):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def subtrair(base: list[Intervalo], cortes: list[Intervalo]) -> list[Intervalo]:
    out = []
    for a, b in base:
        pedacos = [(a, b)]
        for c, d in cortes:
            pedacos = [p for x, y in pedacos for p in ((x, min(y, c)), (max(x, d), y)) if p[0] < p[1]]
        out += pedacos
    return unir(out)


def intersecao(base: list[Intervalo], outros: list[Intervalo]) -> list[Intervalo]:
    return unir((max(a, c), min(b, d)) for a, b in base for c, d in outros if max(a, c) < min(b, d))


def contido(intervalo: Intervalo, em: list[Intervalo]) -> bool:
    a, b = intervalo
    return any(x <= a and b <= y for x, y in em)


def sobrepoe(intervalo: Intervalo, outros: list[Intervalo]) -> bool:
    a, b = intervalo
    return any(max(a, c) < min(b, d) for c, d in outros)


def disponivel(ctx: ContextoEstudante) -> dict[date, list[Intervalo]]:
    """Livres menos ocupados, sono e refeições: onde de fato dá para estudar."""
    livres, bloqueios = por_dia(ctx.livres), por_dia([*ctx.ocupados, *ctx.sono, *ctx.refeicoes])
    return {d: v for d, iv in sorted(livres.items()) if (v := subtrair(iv, bloqueios.get(d, [])))}


@dataclass
class Fatia:
    dia: date
    ini: int
    fim: int
    tipo: Tipo

    @property
    def livre_min(self) -> int:
        return self.fim - self.ini


def fatias(ctx: ContextoEstudante) -> list[Fatia]:
    """Tempo disponível recortado nas bordas de pico e vale. Onde pico e vale se cruzam, vale prevalece
    (o conservador: alta carga nunca cai num vale)."""
    picos, vales = por_dia(ctx.picos), por_dia(ctx.vales)
    out: list[Fatia] = []
    for dia, livre in disponivel(ctx).items():
        v = intersecao(livre, vales.get(dia, []))
        p = subtrair(intersecao(livre, picos.get(dia, [])), v)
        n = subtrair(subtrair(livre, v), p)
        out += [Fatia(dia, a, b, t) for t, ivs in (("vale", v), ("pico", p), ("neutro", n)) for a, b in ivs]
    return sorted(out, key=lambda f: (f.dia, f.ini))


def recortar(base: list[Fatia], cortes: dict[date, list[Intervalo]]) -> list[Fatia]:
    """Fatias menos os intervalos já usados ou proibidos de cada dia, mantendo o tipo de cada pedaço."""
    out = [Fatia(f.dia, a, b, f.tipo) for f in base for a, b in subtrair([(f.ini, f.fim)], cortes.get(f.dia, []))]
    return sorted(out, key=lambda f: (f.dia, f.ini))
