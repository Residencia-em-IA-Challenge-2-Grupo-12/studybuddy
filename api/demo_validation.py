"""Demonstração interativa e visual do Validation determinístico (sem LLM).

Uso (a partir de api/, com o ambiente virtual ativo — Windows, macOS ou Linux):
    python demo_validation.py      # executa os 5 cenários automáticos
    python demo_validation.py -i   # modo interativo para testar horários livres
"""

import argparse
import sys
from datetime import date, time
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.modules.agentes.contratos import (  # noqa: E402
    BlocoEstudo,
    ContextoEstudante,
    Janela,
    PropostaGrade,
    ResultadoValidacao,
)
from app.modules.agentes.validation import AgenteValidation, formatar_relatorio, validar  # noqa: E402

FIXTURES = API_DIR / "tests" / "fixtures"


class AgendaGoogleDemo:
    """Simula um evento recém-adicionado no Google Agenda."""

    def __init__(self, ocupados: list[Janela]) -> None:
        self.ocupados = ocupados

    def ler_janelas(self, inicio: date, fim: date) -> tuple[list[Janela], list[Janela]]:
        return [], [j for j in self.ocupados if inicio <= j.dia <= fim]

    def gravar_blocos(self, blocos: list[BlocoEstudo]) -> list[str]:
        return [f"gcal-{b.id}" for b in blocos]


def carregar_contexto(nome: str) -> ContextoEstudante:
    return ContextoEstudante.model_validate_json((FIXTURES / "contexto" / f"{nome}.json").read_text(encoding="utf-8"))


def carregar_proposta(nome: str) -> PropostaGrade:
    return PropostaGrade.model_validate_json((FIXTURES / "proposta" / f"{nome}.json").read_text(encoding="utf-8"))


def bloco(bloco_id: str, dia: date, ini: time, fim: time, carga: str = "alta", disc: str = "Cálculo I") -> BlocoEstudo:
    foco = max(1, (fim.hour * 60 + fim.minute) - (ini.hour * 60 + ini.minute))
    return BlocoEstudo(
        id=bloco_id,
        dia=dia,
        inicio=ini,
        fim=fim,
        disciplina=disc,
        material_id="demo-01",
        carga=carga,
        tecnica="Pomodoro",
        foco_min=foco,
        pausa_min=5,
    )


def imprimir_resultado(titulo: str, res: ResultadoValidacao) -> None:
    icone = "[APROVADO]" if res.status == "APROVADO" else "[REPROVADO]"
    print(f"\n{'=' * 72}")
    print(f"{icone} {titulo}")
    print("-" * 72)
    print(formatar_relatorio(res))
    print("\nJSON retornado:")
    print(res.model_dump_json(indent=2))


def rodar_cenarios() -> None:
    ctx_mat = carregar_contexto("matutino")
    ctx_fad = carregar_contexto("fadiga")

    imprimir_resultado(
        "1) Fixture proposta/valida.json + contexto/matutino.json",
        validar(carregar_proposta("valida"), ctx_mat),
    )

    imprimir_resultado(
        "2) Fixture proposta/reducao_danos.json + contexto/fadiga.json",
        validar(carregar_proposta("reducao_danos"), ctx_fad),
    )

    imprimir_resultado(
        "3) Fixture proposta/violacoes.json + contexto/matutino.json (agenda + vale + sono)",
        validar(carregar_proposta("violacoes"), ctx_mat),
    )

    proposta_circadiana = PropostaGrade(
        estudante_id=ctx_mat.estudante_id,
        semana_inicio=ctx_mat.semana_inicio,
        blocos=[
            bloco("higiene_alta", date(2026, 11, 30), time(21, 15), time(21, 40), carga="alta"),
            bloco("higiene_baixa", date(2026, 11, 30), time(21, 15), time(21, 40), carga="baixa", disc="Inglês"),
            bloco("almoco", date(2026, 11, 30), time(12, 15), time(12, 40), carga="alta", disc="Programação"),
            bloco("adjacente_ok", date(2026, 11, 30), time(10, 0), time(10, 25), carga="alta"),
        ],
    )
    imprimir_resultado(
        "4) Higiene do sono (alta bloqueada / baixa liberada), refeição e bloco adjacente à agenda",
        validar(proposta_circadiana, ctx_mat),
    )

    agenda = AgendaGoogleDemo([Janela(dia=date(2026, 11, 30), inicio=time(8, 0), fim=time(8, 30))])
    imprimir_resultado(
        "5) Compromisso novo no Google Agenda (08:00-08:30) bloqueando proposta/valida.json",
        AgenteValidation(provedor_agenda=agenda).validar(carregar_proposta("valida"), ctx_mat),
    )

    # Corte automático de 30% na fixture de estresse alto / privação de sono (fadiga.json)
    imprimir_resultado(
        "6) Fixture proposta/sobrecarga_fadiga.json + contexto/fadiga.json (teto cai de 240 para 168 min)",
        validar(carregar_proposta("sobrecarga_fadiga"), ctx_fad),
    )

    # Dia com 6h seguidas de estudo noturno (reprovado por SOBRECARGA)
    imprimir_resultado(
        "7) Fixture proposta/sobrecarga_noturna.json + contexto/noturno.json (6h noturnas ininterruptas)",
        validar(carregar_proposta("sobrecarga_noturna"), carregar_contexto("noturno")),
    )

    print(f"\n{'=' * 72}")
    print("Concluído: 7 cenários validados de forma 100% determinística (0 chamadas a LLM).")


def _ler_hora(texto: str) -> time:
    h, m = texto.strip().split(":")
    return time(int(h), int(m))


def modo_interativo() -> None:
    ctx = carregar_contexto("matutino")
    print("\nModo interativo — Contexto: matutino (segunda 2026-11-30)")
    print("  Ocupado:   09:00-10:00")
    print("  Refeições: 12:00-13:00 e 19:00-20:00")
    print("  Vale:      13:00-15:00")
    print("  Higiene:   21:00-22:00 (1h antes do sono)")
    print("  Sono:      22:00-23:59 e 00:00-06:00")
    print("Digite um bloco para testar (ou 'sair' para encerrar).\n")

    while True:
        try:
            ini_txt = input("Início (ex.: 21:15) ou 'sair': ").strip()
            if ini_txt.lower() in ("sair", "exit", "q"):
                return
            fim_txt = input("Fim    (ex.: 21:40): ").strip()
            carga = input("Carga  (alta/baixa) [alta]: ").strip().lower() or "alta"
            if carga not in ("alta", "baixa"):
                print("Carga inválida. Use 'alta' ou 'baixa'.\n")
                continue
            b = bloco("teste", date(2026, 11, 30), _ler_hora(ini_txt), _ler_hora(fim_txt), carga=carga)
        except (ValueError, EOFError, KeyboardInterrupt) as exc:
            if isinstance(exc, (EOFError, KeyboardInterrupt)):
                print()
                return
            print(f"Entrada inválida ({exc}). Tente no formato HH:MM com fim > início.\n")
            continue

        p = PropostaGrade(estudante_id=ctx.estudante_id, semana_inicio=ctx.semana_inicio, blocos=[b])
        imprimir_resultado(f"Bloco {ini_txt}-{fim_txt} ({carga})", validar(p, ctx))
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--interativo", action="store_true", help="Testar horários digitados no terminal")
    args = ap.parse_args()
    if args.interativo:
        modo_interativo()
    else:
        rodar_cenarios()


if __name__ == "__main__":
    main()

