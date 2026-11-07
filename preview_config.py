"""Configuração exclusiva desta cópia. Nenhuma variável comercial é herdada."""
from pathlib import Path
import re

SOURCE = Path(__file__).resolve().parent
# O checkout e os pilotos usam a própria raiz. Wheels usam a pasta de execução.
ROOT = SOURCE if (SOURCE / ".env.example").is_file() else Path.cwd().resolve()
ENV_PATH = ROOT / ".env"
FIELDS = ("PREVIEW_SSO_SECRET", "PREVIEW_ADM_SECRET",
          "PREVIEW_DEMO_PASSWORD", "PREVIEW_INITIAL_ADMIN_PASSWORD")


def require_secret(name: str) -> str:
    if not ENV_PATH.is_file():
        raise RuntimeError("Execute python init_preview.py na raiz da prévia.")
    values = {}
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in FIELDS or key in values:
            raise ValueError("Campo inesperado ou duplicado no .env da prévia.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,64}", value):
            raise ValueError(f"Valor de desenvolvimento inválido para {key}.")
        values[key] = value
    if values.keys() != set(FIELDS) or len(set(values.values())) != len(FIELDS):
        raise ValueError("O .env requer quatro valores exclusivos de desenvolvimento.")
    return values[name]
