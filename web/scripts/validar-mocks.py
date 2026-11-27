#!/usr/bin/env python3
"""Valida cada mock de web/src/mocks contra o modelo pydantic do contrato correspondente.

O mock é cópia das fixtures da [0.2]. Validar a cópia — e não a origem — prova que o dado que a
tela vai importar respeita api/app/modules/agentes/contratos.py.

    .venv/bin/python web/scripts/validar-mocks.py

`communication/` é outra família: são saídas do agente Communication, não do Maestro. Não são
validadas contra os modelos (o modelo errado reprovaria por motivo errado); o script mostra a
divergência, em vez de escondê-la.
"""

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # web/
REPO = RAIZ.parent

ap = argparse.ArgumentParser(description=__doc__)
# --mocks existe para testar a própria validação numa cópia adulterada, sem tocar no repositório.
ap.add_argument("--mocks", default=str(RAIZ / "src" / "mocks"), help="diretório do índice de mocks")
MOCKS = Path(ap.parse_args().mocks)

sys.path.insert(0, str(REPO / "api"))
from app.modules.agentes.contratos import (  # noqa: E402
    CheckIn,
    ContextoEstudante,
    PropostaGrade,
    ResultadoValidacao,
)

GRUPOS = [
    ("contexto", ContextoEstudante),
    ("proposta", PropostaGrade),
    ("resultado", ResultadoValidacao),
]

falhas = 0
total = 0

for pasta, modelo in GRUPOS:
    arquivos = sorted((MOCKS / pasta).glob("*.json"))
    if not arquivos:
        print(f"FALHA  {pasta}/: nenhum mock encontrado")
        falhas += 1
        continue
    for arquivo in arquivos:
        total += 1
        try:
            modelo.model_validate(json.loads(arquivo.read_text()))
            print(f"ok     {pasta}/{arquivo.name} -> {modelo.__name__}")
        except Exception as exc:  # pydantic.ValidationError, JSON inválido
            falhas += 1
            print(f"FALHA  {pasta}/{arquivo.name}: {str(exc).splitlines()[0]}")

# --- família distinta: comunicação ---------------------------------------------------------
comunicacao = sorted((MOCKS / "communication").glob("*.json"))
if not comunicacao:
    print("FALHA  communication/: nenhum mock encontrado")
    falhas += 1
else:
    total += len(comunicacao)
    for arquivo in comunicacao:
        json.loads(arquivo.read_text())  # é JSON válido; o formato é que não é o do Maestro
        print(f"nota   communication/{arquivo.name}: família distinta, JSON válido, não validada pelo contrato")

checkins = MOCKS / "communication" / "checkins.json"
if checkins.exists():
    amostra = next(iter(json.loads(checkins.read_text()).values()))
    campos = set(amostra)
    contrato = set(CheckIn.model_fields)
    print(
        "nota   divergência conhecida: checkins.json traz "
        f"{sorted(campos)}; CheckIn espera {sorted(contrato)}"
        f" (faltam: {sorted(contrato - campos) or '—'}; sobram: {sorted(campos - contrato) or '—'})"
    )

indice = MOCKS / "index.ts"
if not indice.exists():
    print("FALHA  src/mocks/index.ts não existe — rode scripts/sincronizar-mocks.mjs")
    falhas += 1

if falhas:
    print(f"\n{falhas} falha(s) em {total} mocks")
    sys.exit(1)

print(f"\n{total} mocks conferidos, 0 falhas")
