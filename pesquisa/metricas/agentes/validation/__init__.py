"""Métricas e conjunto de avaliação do Validation Agent e Guardrails."""

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[4] / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
