from __future__ import annotations

import hashlib
import json
import io
import re
from PIL import Image, UnidentifiedImageError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from chronos_auth.integration import install_sso
from chronos_auth.scope import scoped_tenant
from chronos_auth.services import service_headers, forwarding_headers
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from chronos_storage.atomic import atomic_write_json
from pydantic import BaseModel


app = FastAPI(title="Chronos Media API", version="0.1.0")

install_sso(app, "media")
app.add_middleware(
    # CORS wraps SSO, including its 401/403 responses.
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


BASE_DIR = Path(__file__).resolve().parents[3] / ".local/media"
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
ORIGINALS_DIR = STORAGE_DIR / "originals"
CACHE_DIR = STORAGE_DIR / "cache"
MEDIA_DATA_PATH = DATA_DIR / "media_data.json"
DEFAULT_TENANT_ID = "demo"
MAX_UPLOAD_MB = 8
MediaType = Literal["art", "product", "shop", "zap", "document", "proof", "other"]
MediaStatus = Literal["local", "archived"]


CACHE_DIR.mkdir(parents=True, exist_ok=True)


def guard_media_resource(user, path, params):
    if path.startswith("/media/cache/") and path != "/media/cache/expired":
        if "\\" in path or any(part in {".", ".."} for part in path.split("/")):
            raise HTTPException(404, "Arquivo nao encontrado")
        scoped_tenant(path.split("/")[3], "media")


app.state.sso_resource_guard = guard_media_resource


class MediaUpdatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    client_id: str | None = None
    order_id: str | None = None
    media_type: MediaType | None = None
    title: str | None = None
    description: str | None = None
    status: MediaStatus | None = None
    tags: list[str] | None = None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat(timespec="seconds")


def safe_part(value: str | None, fallback: str) -> str:
    part = re.sub(r"[^a-zA-Z0-9_-]", "-", str(value or fallback)).strip("-")[:100]
    return part or fallback


def image_format(content: bytes) -> tuple[str, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"PNG", "JPEG"} or image.width * image.height > 16_000_000:
                raise HTTPException(415, "Use uma imagem PNG ou JPEG de até 16 megapixels.")
            image.load()
            return ("image/png", ".png") if image.format == "PNG" else ("image/jpeg", ".jpg")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(415, "Arquivo de imagem inválido.") from exc


def tenant_directory(base: Path, tenant: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", tenant):
        raise HTTPException(400, "Identificador de empresa inválido.")
    folder = (base / tenant).resolve()
    if folder.parent != base.resolve() or not base.resolve().is_relative_to(BASE_DIR.resolve()):
        raise HTTPException(400, "Pasta de mídia inválida.")
    return folder


def confined(base: Path, tenant: str, path: Path) -> Path:
    folder = tenant_directory(base, tenant)
    actual = path.resolve()
    if not actual.is_relative_to(folder) or actual == folder:
        raise HTTPException(400, "Arquivo fora da pasta da empresa.")
    return actual


def record_path(item, field):
    base = ORIGINALS_DIR if field == "original_local_path" else CACHE_DIR
    return confined(base, item["tenant_id"], base / item[field])


def empty_data() -> dict[str, Any]:
    return {"schema": "chronos_media_data_v1", "saved_at": now_iso(), "items": {}}


def load_data() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MEDIA_DATA_PATH.exists():
        data = empty_data()
        save_data(data)
        return data
    return json.loads(MEDIA_DATA_PATH.read_text(encoding="utf-8"))


def save_data(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = now_iso()
    atomic_write_json(MEDIA_DATA_PATH, data)


def tenant_items(data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return data.setdefault("items", {}).setdefault(tenant_id, {})


def get_item_or_404(data: dict[str, Any], tenant_id: str, media_id: str) -> dict[str, Any]:
    item = tenant_items(data, tenant_id).get(media_id)
    if not item:
        raise HTTPException(status_code=404, detail="Midia nao encontrada.")
    return item


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_cache_clone(original_path: Path, cache_path: Path, content_type: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original_path) as image:
        image.thumbnail((1600, 1600))
        mode = "RGBA" if content_type == "image/png" else "RGB"
        pixels = image.convert(mode)
        pixels.info.clear()
        pixels.save(cache_path, format="PNG" if mode == "RGBA" else "JPEG")


def cache_is_missing(item: dict[str, Any]) -> bool:
    cache_path = record_path(item, "cache_path")
    return not cache_path.exists()


def refresh_item_cache(item: dict[str, Any]) -> dict[str, Any]:
    original_path = record_path(item, "original_local_path")
    if not original_path.exists():
        raise HTTPException(status_code=409, detail="Original local ausente. Restaure o arquivo a partir do backup para recriar a prévia.")
    cache_path = record_path(item, "cache_path")
    make_cache_clone(original_path, cache_path, item.get("mime_type") or "")
    item["cache_status"] = "ready"
    item["cache_refreshed_at"] = now_iso()
    item["cache_expires_at"] = (now_utc() + timedelta(days=int(item.get("cache_ttl_days") or 15))).isoformat(timespec="seconds")
    return item


def delete_item_files(item: dict[str, Any]) -> None:
    paths = [record_path(item, key) for key in ("cache_path", "original_local_path")]
    for path in paths:
        if path.is_file():
            path.unlink()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "Chronos Media API",
        "provider": "local",
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@app.get("/media/storage-status")
def storage_status() -> dict[str, Any]:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "provider": "local", "originals_persistent": True}


@app.post("/media/upload")
async def upload_media(
    tenant_id: str | None = Form(default=None),
    client_id: str = Form(default=""),
    order_id: str = Form(default=""),
    media_type: MediaType = Form(default="other"),
    title: str = Form(default=""),
    description: str = Form(default=""),
    tags: str = Form(default=""),
    cache_ttl_days: int = Form(default=15),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    tenant_id = scoped_tenant(tenant_id, "media")
    content = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima do limite de {MAX_UPLOAD_MB} MB.")

    media_id = f"media-{uuid4().hex[:12]}"
    content_type, extension = image_format(content)
    tenant_part = tenant_id
    type_part = safe_part(media_type, "other")
    owner_part = safe_part(client_id or order_id or "geral", "geral")
    original_dir = ORIGINALS_DIR / tenant_part / type_part / owner_part / media_id
    cache_dir = CACHE_DIR / tenant_part / type_part / owner_part / media_id
    original_path = confined(ORIGINALS_DIR, tenant_part, original_dir / f"original{extension}")
    cache_path = confined(CACHE_DIR, tenant_part, cache_dir / f"preview{extension}")

    original_dir.mkdir(parents=True, exist_ok=True)
    original_path.write_bytes(content)
    make_cache_clone(original_path, cache_path, content_type)

    data = load_data()
    item = {
        "id": media_id,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "order_id": order_id,
        "media_type": media_type,
        "title": title or file.filename or media_id,
        "description": description,
        "file_name": file.filename or f"{media_id}{extension}",
        "mime_type": content_type,
        "size_bytes": len(content),
        "sha256": checksum(original_path),
        "status": "local",
        "storage_provider": "local",
        "download_url": f"/media/items/{media_id}/download",
        "original_local_path": original_path.relative_to(ORIGINALS_DIR).as_posix(),
        "cache_path": cache_path.relative_to(CACHE_DIR).as_posix(),
        "cache_url": "/media/cache/" + str(cache_path.relative_to(CACHE_DIR)).replace("\\", "/"),
        "cache_status": "ready",
        "cache_ttl_days": max(1, min(cache_ttl_days, 365)),
        "cache_refreshed_at": now_iso(),
        "cache_expires_at": (now_utc() + timedelta(days=max(1, min(cache_ttl_days, 365)))).isoformat(timespec="seconds"),
        "last_accessed_at": now_iso(),
        "access_count": 0,
        "tags": [tag.strip().lower() for tag in tags.split(",") if tag.strip()],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tenant_items(data, tenant_id)[media_id] = item
    save_data(data)
    return {"ok": True, "media": item}


@app.get("/media/items")
def list_media(
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
    client_id: str = "",
    order_id: str = "",
    media_type: str = "",
    q: str = "",
) -> dict[str, Any]:
    data = load_data()
    items = list(tenant_items(data, tenant_id).values())
    if client_id:
        items = [item for item in items if item.get("client_id") == client_id]
    if order_id:
        items = [item for item in items if item.get("order_id") == order_id]
    if media_type:
        items = [item for item in items if item.get("media_type") == media_type]
    if q:
        query = q.lower()
        items = [
            item
            for item in items
            if query in " ".join([item.get("title", ""), item.get("description", ""), item.get("file_name", ""), " ".join(item.get("tags") or [])]).lower()
        ]
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"ok": True, "items": items}


@app.get("/media/summary")
def media_summary(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    items = list(tenant_items(data, tenant_id).values())
    originals_ready = [item for item in items if record_path(item, "original_local_path").is_file()]
    cache_ready = [item for item in items if item.get("cache_status") == "ready" and record_path(item, "cache_path").exists()]
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "total": len(items),
        "storage_provider": "local",
        "originals_ready": len(originals_ready),
        "originals_missing": len(items) - len(originals_ready),
        "cache_ready": len(cache_ready),
    }


@app.get("/media/items/{media_id}")
def get_media(media_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    return {"ok": True, "media": get_item_or_404(data, tenant_id, media_id)}


@app.patch("/media/items/{media_id}")
def update_media(media_id: str, payload: MediaUpdatePayload) -> dict[str, Any]:
    data = load_data()
    item = get_item_or_404(data, payload.tenant_id, media_id)
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("tenant_id", None)
    item.update({key: value for key, value in updates.items() if value is not None})
    item["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "media": item}


@app.delete("/media/items/{media_id}")
def delete_media(
    media_id: str,
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
) -> dict[str, Any]:
    data = load_data()
    items = tenant_items(data, tenant_id)
    item = get_item_or_404(data, tenant_id, media_id)
    delete_item_files(item)
    items.pop(media_id, None)
    save_data(data)
    return {"ok": True, "deleted": media_id}


@app.post("/media/items/{media_id}/access")
def access_media(media_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    item = get_item_or_404(data, tenant_id, media_id)
    if cache_is_missing(item):
        refresh_item_cache(item)
    item["last_accessed_at"] = now_iso()
    item["access_count"] = int(item.get("access_count") or 0) + 1
    save_data(data)
    return {"ok": True, "media": item, "cache_url": item.get("cache_url")}


@app.post("/media/items/{media_id}/refresh-cache")
def refresh_cache(media_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    item = refresh_item_cache(get_item_or_404(data, tenant_id, media_id))
    save_data(data)
    return {"ok": True, "media": item}


@app.get("/media/items/{media_id}/download")
def download_media(media_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    tenant_id = scoped_tenant(tenant_id, "media")
    item = get_item_or_404(load_data(), tenant_id, media_id)
    original = record_path(item, "original_local_path").resolve()
    if not original.is_relative_to(ORIGINALS_DIR.resolve()) or not original.is_file():
        raise HTTPException(404, "Original local não encontrado.")
    return FileResponse(original, media_type=item.get("mime_type") or "application/octet-stream",
                        filename=item.get("file_name") or original.name)


@app.delete("/media/cache/expired")
def delete_expired_cache(tenant_id: str = Query(default=DEFAULT_TENANT_ID), older_than_days: int = Query(default=15, ge=1, le=365)) -> dict[str, Any]:
    data = load_data()
    cutoff = now_utc() - timedelta(days=older_than_days)
    removed = 0
    for item in tenant_items(data, tenant_id).values():
        last_access = datetime.fromisoformat(item.get("last_accessed_at") or item.get("created_at"))
        cache_path = record_path(item, "cache_path")
        if cache_path.is_file() and last_access < cutoff and record_path(item, "original_local_path").is_file():
            cache_path.unlink()
            item["cache_status"] = "expired"
            item["updated_at"] = now_iso()
            removed += 1
    save_data(data)
    return {"ok": True, "removed": removed}


# Register after the cleanup route so the static mount does not intercept DELETE.
app.mount("/media/cache", StaticFiles(directory=CACHE_DIR), name="media-cache")
