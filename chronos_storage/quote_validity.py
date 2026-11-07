import json
from pathlib import Path
from threading import RLock
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from .postgres import transaction
from .runtime_sync import postgres_mode, run
from . import atomic_write_json

DEFAULT = {"mode": "days", "days": 7, "text": ""}
PATH = Path(__file__).resolve().parents[1] / ".local/quote_validity.json"
LOCK = RLock()

class QuoteValidityPayload(BaseModel):
    mode: Literal["days", "text"] = "days"
    days: int = Field(default=7, strict=True, ge=1, le=365)
    text: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def validate_text(self):
        self.text = self.text.strip()
        if self.mode == "text" and not self.text:
            raise ValueError("Informe o texto da validade.")
        return self

async def pg_settings(slug, values=None):
    async with transaction() as db:
        if values is None:
            row = await db.fetchrow("SELECT settings->'quote_validity' AS value FROM tenants WHERE slug=$1", slug)
            if not row: raise HTTPException(404, "Empresa não encontrada.")
            return row["value"] or dict(DEFAULT)
        result = await db.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{quote_validity}',$2::jsonb) WHERE slug=$1", slug, values)
        if result == "UPDATE 0": raise HTTPException(404, "Empresa não encontrada.")
        return values

def settings(slug, values=None, module="loja"):
    if postgres_mode(module) == "primary": return run(pg_settings(slug, values))
    with LOCK:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        if values is None: return data.get(slug, dict(DEFAULT))
        data[slug] = values
        atomic_write_json(PATH, data)
        return values
