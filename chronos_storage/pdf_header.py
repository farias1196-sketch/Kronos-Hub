import json
from preview_config import ROOT
from threading import RLock
from typing import Annotated
from fastapi import HTTPException
from pydantic import BaseModel, Field, StringConstraints
from .postgres import transaction
from .runtime_sync import postgres_mode, run
from . import atomic_write_json

DEFAULT = {"lines": None}
PATH = ROOT / ".local/pdf_header.json"
LOCK = RLock()

class PdfHeaderPayload(BaseModel):
    lines: list[Annotated[str, StringConstraints(strip_whitespace=True, max_length=70, pattern=r"^[^\r\n]*$")]] = Field(min_length=3, max_length=3)


async def pg_settings(slug, values=None):
    async with transaction() as db:
        if values is None:
            row = await db.fetchrow("SELECT settings->'pdf_header' AS value FROM tenants WHERE slug=$1", slug)
            if not row: raise HTTPException(404, "Empresa não encontrada.")
            return row["value"] or dict(DEFAULT)
        result = await db.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{pdf_header}',$2::jsonb) WHERE slug=$1", slug, values)
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
