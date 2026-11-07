from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import csv
import hashlib
import io
import json
import math
import logging
from pathlib import Path
import re
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi import Request
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from chronos_auth.integration import install_sso
from chronos_auth.scope import scoped_tenant, current_user
from chronos_auth.services import service_headers, forwarding_headers
from Chronos_stock.demo_items import demo_items
from chronos_storage import atomic_write_json
from chronos_storage.atomic import FileLockTimeout, async_file_lock
from chronos_storage.runtime_sync import postgres_enabled, postgres_mode, run as run_postgres
from chronos_storage.stock_runtime import load_stock_payload
from chronos_storage.stock_shop_exchange import SHOP_COLUMNS, read_shop_prices, parse_shop_columns, commit_stock_shop
from chronos_storage.stock_catalog_csv import COLUMNS as CATALOG_COLUMNS, read_catalog_details, auxiliary_rows, parse_auxiliary
from pydantic import BaseModel, Field


class StockRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()
        if not self.path.startswith("/stock/"):
            return handle

        async def handle_current_state(request: Request):
            # O arquivo de transação é distinto do lock usado para a substituição atômica do JSON.
            try:
                async with async_file_lock(DATA_DIR / "operations"):
                    load_stock_data()
                    return await handle(request)
            except FileLockTimeout as exc:
                raise HTTPException(503, "Estoque ocupado. Tente novamente.") from exc

        return handle_current_state


app = FastAPI(title="Chronos Stock API", version="0.1.0")
app.router.route_class = StockRoute

install_sso(app, "stock")
app.add_middleware(
    # CORS wraps SSO, including its 401/403 responses.
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


StockKind = Literal["sale", "internal"]
ServiceResourceStatus = Literal["active", "maintenance", "disabled"]
AttributeType = Literal["text", "number", "select", "boolean"]
AttributeRole = Literal["information", "variant", "pricing_input", "promotion_tag"]
DEFAULT_TENANT_ID = "demo"
DATA_DIR = Path(__file__).resolve().parents[3] / ".local" / "stock"
AI_SNAPSHOT_DIR = DATA_DIR / "ai_snapshots"
STOCK_DATA_PATH = DATA_DIR / "stock_data.json"


class StockItem(BaseModel):
    id: str
    tenant_id: str = DEFAULT_TENANT_ID
    kind: StockKind
    name: str
    sku: str = ""
    description: str = ""
    category: str = ""
    family: str = ""
    size: str = ""
    color: str = ""
    colors: list[str] = Field(default_factory=list)
    finishes: list[str] = Field(default_factory=list)
    display_name: str = ""
    unit: str = "UN"
    quantity: float = 0
    min_quantity: float = 0
    cost_price: float = 0
    supplier: str = ""
    location: str = ""
    art_lead_days: int = Field(default=0, ge=0, le=365)
    production_lead_days: int = Field(default=0, ge=0, le=365)
    status: str = "active"
    # Values are keyed by the stable custom column key defined on the category.
    attributes: dict[str, Any] = Field(default_factory=dict)


class CreateStockItemRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    kind: StockKind
    name: str = ""
    sku: str = ""
    description: str = ""
    category: str = ""
    family: str = ""
    size: str = ""
    color: str = ""
    colors: list[str] = Field(default_factory=list)
    finishes: list[str] = Field(default_factory=list)
    unit: str = "UN"
    quantity: float = Field(default=0, ge=0)
    min_quantity: float = Field(default=0, ge=0)
    cost_price: float = Field(default=0, ge=0)
    supplier: str = ""
    location: str = ""
    art_lead_days: int = Field(default=0, ge=0, le=365)
    production_lead_days: int = Field(default=0, ge=0, le=365)
    attributes: dict[str, Any] = Field(default_factory=dict)


class UpdateStockItemRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    family: str | None = None
    size: str | None = None
    color: str | None = None
    colors: list[str] | None = None
    finishes: list[str] | None = None
    unit: str | None = None
    quantity: float | None = Field(default=None, ge=0)
    min_quantity: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    supplier: str | None = None
    location: str | None = None
    art_lead_days: int | None = Field(default=None, ge=0, le=365)
    production_lead_days: int | None = Field(default=None, ge=0, le=365)
    attributes: dict[str, Any] | None = None


class MovementRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    quantity: float = Field(gt=0)
    reason: str = ""
    requested_by: str = ""


class CreateCategoryRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)


class CreateFamilyRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)


class CreateColorRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)


class CreateCategoryAttributeRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)
    key: str = ""
    type: AttributeType = "text"
    role: AttributeRole = "information"
    options: list[str] = Field(default_factory=list)
    required: bool = False


class UpdateCategoryAttributeRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str | None = Field(default=None, min_length=1)
    type: AttributeType | None = None
    role: AttributeRole | None = None
    options: list[str] | None = None
    required: bool | None = None
    active: bool | None = None


class ImportCommitRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    preview_id: str = Field(min_length=1)
    duplicate_strategy: Literal["skip", "update"] = "skip"


class CreateSupplierRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)
    document: str = ""
    contact_name: str = ""
    phone: str = ""
    email: str = ""
    cep: str = ""
    address: str = ""
    city: str = ""
    state: str = ""


class ServiceResourceRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str = Field(min_length=1)
    kind: str = "equipment"
    quantity: int = Field(default=1, ge=1)
    status: ServiceResourceStatus = "active"
    unavailable_until: str = ""
    notes: str = ""


class ServiceResourceUpdateRequest(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    name: str | None = None
    kind: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    status: ServiceResourceStatus | None = None
    unavailable_until: str | None = None
    notes: str | None = None


SALE_ITEMS: list[StockItem] = []

INTERNAL_ITEMS: list[StockItem] = []

STOCK_CATEGORIES: list[dict[str, Any]] = []

STOCK_SUPPLIERS: list[dict[str, Any]] = []

SERVICE_RESOURCES: list[dict[str, Any]] = []
MOVEMENTS: list[dict[str, Any]] = []
# CSV previews are intentionally short lived. Nothing is written until the user
# confirms the preview token through the commit endpoint.
IMPORT_PREVIEWS: dict[str, dict[str, Any]] = {}


def save_stock_data() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "chronos_stock_data_v2",
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "sale_items": [item.model_dump() for item in SALE_ITEMS],
        "internal_items": [item.model_dump() for item in INTERNAL_ITEMS],
        "categories": STOCK_CATEGORIES,
        "suppliers": STOCK_SUPPLIERS,
        "service_resources": SERVICE_RESOURCES,
        "movements": MOVEMENTS,
    }
    atomic_write_json(STOCK_DATA_PATH, payload)


def load_stock_data() -> None:
    if postgres_mode("stock") == "primary":
        data = run_postgres(load_stock_payload())
    elif not STOCK_DATA_PATH.exists():
        if (DATA_DIR / ".demo-on-first-start").is_file():
            examples = [StockItem(**fields) for fields in demo_items()]
            SALE_ITEMS[:] = [item for item in examples if item.kind == "sale"]
            INTERNAL_ITEMS[:] = [item for item in examples if item.kind == "internal"]
        save_stock_data()
        return
    else:
        data = json.loads(STOCK_DATA_PATH.read_text(encoding="utf-8"))
    SALE_ITEMS.clear()
    SALE_ITEMS.extend(StockItem(**item) for item in data.get("sale_items", []))
    INTERNAL_ITEMS.clear()
    INTERNAL_ITEMS.extend(StockItem(**item) for item in data.get("internal_items", []))
    STOCK_CATEGORIES.clear()
    STOCK_CATEGORIES.extend(data.get("categories", []))
    STOCK_SUPPLIERS.clear()
    STOCK_SUPPLIERS.extend(data.get("suppliers", []))
    SERVICE_RESOURCES.clear()
    SERVICE_RESOURCES.extend(data.get("service_resources", []))
    MOVEMENTS.clear()
    MOVEMENTS.extend(data.get("movements", []))


def snapshot_file(tenant_id: str) -> Path:
    if (not tenant_id or tenant_id != tenant_id.strip() or tenant_id in {".", ".."}
            or not tenant_id.isprintable() or re.search(r'[<>:"/\\|?*]', tenant_id)):
        raise HTTPException(400, "Identificador de empresa inválido.")
    # Nomes distintos, inclusive por caixa, nunca compartilham uma pasta por normalização.
    key = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()
    target = AI_SNAPSHOT_DIR / key / "stock_snapshot.json"
    lock = target.with_name(target.name + ".lock")
    try:
        if target.resolve() != target or lock.resolve() != lock:
            raise HTTPException(400, "Destino de snapshot redirecionado.")
    except (OSError, RuntimeError) as exc:
        raise HTTPException(400, "Destino de snapshot inválido.") from exc
    return target


def normalize_tenant_id(tenant_id: str | None) -> str:
    value = DEFAULT_TENANT_ID if tenant_id is None else tenant_id
    snapshot_file(value)
    return value


def all_items_for_tenant(tenant_id: str) -> list[StockItem]:
    return [item for item in SALE_ITEMS + INTERNAL_ITEMS if item.tenant_id == tenant_id]


def find_item(item_id: str, tenant_id: str) -> StockItem | None:
    return next((stock_item for stock_item in SALE_ITEMS + INTERNAL_ITEMS if stock_item.id == item_id and stock_item.tenant_id == tenant_id), None)


def find_item_by_sku(sku: str, tenant_id: str) -> StockItem | None:
    normalized_sku = normalize_text(sku)
    if not normalized_sku:
        return None
    return next((item for item in all_items_for_tenant(tenant_id) if normalize_text(item.sku) == normalized_sku), None)


def assert_available_sku(sku: str, tenant_id: str, item_id: str = "") -> None:
    existing = find_item_by_sku(sku, tenant_id)
    if existing and existing.id != item_id:
        raise HTTPException(status_code=409, detail=f"O SKU {sku.strip()} ja esta cadastrado.")


def find_internal_item(item_id: str, tenant_id: str) -> StockItem | None:
    return next((stock_item for stock_item in INTERNAL_ITEMS if stock_item.id == item_id and stock_item.tenant_id == tenant_id), None)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def make_item_id(kind: StockKind, name: str, tenant_id: str) -> str:
    prefix = "sale" if kind == "sale" else "int"
    base_id = f"{prefix}-{slugify(name)}"
    existing_ids = {item.id for item in SALE_ITEMS + INTERNAL_ITEMS if item.tenant_id == tenant_id}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def build_display_name(family: str, size: str, fallback_name: str) -> str:
    display_name = " ".join(part for part in [family.strip(), size.strip()] if part)
    return display_name or fallback_name.strip()


def make_category_id(name: str, tenant_id: str) -> str:
    base_id = f"cat-{slugify(name)}"
    existing_ids = {category["id"] for category in STOCK_CATEGORIES if category["tenant_id"] == tenant_id}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def make_supplier_id(name: str, tenant_id: str) -> str:
    base_id = f"sup-{slugify(name)}"
    existing_ids = {supplier["id"] for supplier in STOCK_SUPPLIERS if supplier["tenant_id"] == tenant_id}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def make_service_resource_id(name: str, tenant_id: str) -> str:
    base_id = f"resource-{slugify(name)}"
    existing_ids = {resource["id"] for resource in SERVICE_RESOURCES if resource["tenant_id"] == tenant_id}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def make_family_id(name: str, category: dict[str, Any]) -> str:
    base_id = f"fam-{slugify(name)}"
    existing_ids = {family["id"] for family in category["families"]}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def find_category(category_id: str, tenant_id: str) -> dict[str, Any] | None:
    return next((category for category in STOCK_CATEGORIES if category["id"] == category_id and category["tenant_id"] == tenant_id), None)


def find_category_by_name(name: str, tenant_id: str) -> dict[str, Any] | None:
    normalized_name = normalize_text(name)
    return next(
        (
            category
            for category in STOCK_CATEGORIES
            if category["tenant_id"] == tenant_id and normalize_text(category["name"]) == normalized_name
        ),
        None,
    )


def find_supplier(supplier_id: str, tenant_id: str) -> dict[str, Any] | None:
    return next((supplier for supplier in STOCK_SUPPLIERS if supplier["id"] == supplier_id and supplier["tenant_id"] == tenant_id), None)


def find_service_resource(resource_id: str, tenant_id: str) -> dict[str, Any] | None:
    return next((resource for resource in SERVICE_RESOURCES if resource["id"] == resource_id and resource["tenant_id"] == tenant_id), None)


def ensure_family_colors(category: dict[str, Any]) -> dict[str, Any]:
    for family in category.get("families", []):
        family.setdefault("colors", [])
    category.setdefault("attributes", [])
    for attribute in category["attributes"]:
        attribute.setdefault("id", f"attr-{slugify(attribute.get('key') or attribute.get('name', 'campo'))}")
        attribute.setdefault("key", slugify(attribute.get("name", "campo")).replace("-", "_"))
        attribute.setdefault("type", "text")
        attribute.setdefault("role", "information")
        attribute.setdefault("options", [])
        attribute.setdefault("required", False)
        attribute.setdefault("active", True)
    return category


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_attribute_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", value.casefold()).strip("_")
    return key or "atributo"


def make_attribute_key(name: str, category: dict[str, Any], reserved_key: str = "") -> str:
    existing_keys = {attribute.get("key", "") for attribute in ensure_family_colors(category)["attributes"]}
    base_key = normalize_attribute_key(reserved_key or name)
    if base_key not in existing_keys:
        return base_key
    counter = 2
    while f"{base_key}_{counter}" in existing_keys:
        counter += 1
    return f"{base_key}_{counter}"


def make_attribute_id(key: str, category: dict[str, Any]) -> str:
    existing_ids = {attribute.get("id", "") for attribute in ensure_family_colors(category)["attributes"]}
    base_id = f"attr-{slugify(key)}"
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def active_category_attributes(category_name: str, tenant_id: str) -> list[dict[str, Any]]:
    category = find_category_by_name(category_name, tenant_id)
    if not category:
        return []
    return [attribute for attribute in ensure_family_colors(category)["attributes"] if attribute.get("active", True)]


def normalize_attribute_value(attribute: dict[str, Any], raw_value: Any) -> Any:
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return None
    attribute_type = attribute.get("type", "text")
    if attribute_type == "number":
        try:
            return parse_decimal(raw_value)
        except ValueError as error:
            raise ValueError(f'"{attribute["name"]}" precisa ser um numero.') from error
    if attribute_type == "boolean":
        normalized_value = normalize_text(raw_value)
        if normalized_value in {"1", "true", "sim", "yes", "y"}:
            return True
        if normalized_value in {"0", "false", "nao", "não", "no", "n"}:
            return False
        raise ValueError(f'"{attribute["name"]}" aceita sim/nao.')
    value = str(raw_value).strip()
    if attribute_type == "select":
        option = next((option for option in attribute.get("options", []) if normalize_text(option) == normalize_text(value)), None)
        if option is None:
            raise ValueError(f'"{attribute["name"]}" precisa usar uma das opcoes cadastradas.')
        return option
    return value


def normalize_product_attributes(category_name: str, tenant_id: str, attributes: dict[str, Any], current: dict[str, Any] | None = None) -> dict[str, Any]:
    category = find_category_by_name(category_name, tenant_id)
    provided = attributes or {}
    if not category:
        if any(value not in (None, "") for value in provided.values()):
            raise HTTPException(status_code=422, detail="Selecione uma categoria antes de preencher colunas personalizadas.")
        return {}

    definitions = active_category_attributes(category_name, tenant_id)
    definitions_by_key = {attribute["key"]: attribute for attribute in definitions}
    unknown = [key for key, value in provided.items() if key not in definitions_by_key and value not in (None, "")]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Coluna(s) nao pertencem a categoria: {', '.join(unknown)}.")

    normalized = dict(current or {})
    for key, raw_value in provided.items():
        if key not in definitions_by_key:
            continue
        try:
            value = normalize_attribute_value(definitions_by_key[key], raw_value)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if value is None:
            normalized.pop(key, None)
        else:
            normalized[key] = value

    missing = [attribute["name"] for attribute in definitions if attribute.get("required") and attribute["key"] not in normalized]
    if missing:
        raise HTTPException(status_code=422, detail=f"Preencha as colunas obrigatorias: {', '.join(missing)}.")
    return {key: value for key, value in normalized.items() if key in definitions_by_key}


def parse_decimal(value: Any) -> float:
    raw = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def find_family(category: dict[str, Any], family_id: str) -> dict[str, Any] | None:
    ensure_family_colors(category)
    return next((family for family in category["families"] if family["id"] == family_id), None)


def make_color_id(name: str, family: dict[str, Any]) -> str:
    family.setdefault("colors", [])
    base_id = f"color-{slugify(name)}"
    existing_ids = {color["id"] for color in family["colors"]}
    if base_id not in existing_ids:
        return base_id
    counter = 2
    while f"{base_id}-{counter}" in existing_ids:
        counter += 1
    return f"{base_id}-{counter}"


def register_movement(item: StockItem, movement_type: Literal["add", "withdraw"], payload: MovementRequest) -> dict[str, Any]:
    movement = {
        "id": f"movement-{len(MOVEMENTS) + 1}",
        "type": movement_type,
        "tenant_id": item.tenant_id,
        "item_id": item.id,
        "item_name": item.name,
        "unit": item.unit,
        "quantity": payload.quantity,
        "reason": payload.reason.strip(),
        "requested_by": payload.requested_by.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    MOVEMENTS.append(movement)
    return movement


def build_ai_snapshot(tenant_id: str) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    items = all_items_for_tenant(tenant_id)
    sale_items = [item for item in items if item.kind == "sale"]
    low_stock = [item for item in sale_items if item.quantity <= item.min_quantity]
    sale_item_ids = {item.id for item in sale_items}
    movements = [movement for movement in MOVEMENTS if movement["tenant_id"] == tenant_id and movement["item_id"] in sale_item_ids]
    categories = [ensure_family_colors(category) for category in STOCK_CATEGORIES if category["tenant_id"] == tenant_id]
    suppliers = [supplier for supplier in STOCK_SUPPLIERS if supplier["tenant_id"] == tenant_id]
    return {
        "schema": "chronos_stock_ai_snapshot_v1",
        "tenant_id": tenant_id,
        "scope": "sale_stock_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_items": len(sale_items),
            "sale_items": len(sale_items),
            "low_stock_items": len(low_stock),
        },
        "alerts": {
            "low_stock": [item.model_dump() for item in low_stock],
        },
        "taxonomy": {
            "categories": categories,
            "suppliers": suppliers,
        },
        "stock": {
            "sale": [item.model_dump() for item in sale_items],
        },
        "recent_movements": movements[-50:],
    }


def write_ai_snapshot(tenant_id: str, *, persist_stock: bool = True) -> dict[str, Any]:
    snapshot_path = snapshot_file(tenant_id)
    snapshot = build_ai_snapshot(tenant_id)
    if persist_stock:
        save_stock_data()
    try:
        atomic_write_json(snapshot_path, snapshot)
    except OSError as exc:
        if not persist_stock:
            raise HTTPException(503, "Snapshot indisponível. Tente novamente.") from exc
        logging.getLogger(__name__).warning("Saldo gravado. Snapshot pendente de regeneração.")
    return snapshot


CSV_FIXED_COLUMNS = [
    "sku",
    "tamanho", "cor", "cores", "acabamentos", "status", "atributos_json",
    "nome",
    "tipo",
    "categoria",
    "familia",
    "descricao",
    "unidade",
    "quantidade",
    "estoque_minimo",
    "custo",
    "fornecedor",
    "localizacao",
    "prazo_arte_dias_uteis",
    "prazo_producao_dias_uteis",
]


def csv_custom_columns(tenant_id: str) -> list[str]:
    keys: set[str] = set()
    for category in STOCK_CATEGORIES:
        if category["tenant_id"] != tenant_id:
            continue
        keys.update(attribute["key"] for attribute in active_category_attributes(category["name"], tenant_id))
    return [f"custom.{key}" for key in sorted(keys)]


def csv_columns(tenant_id: str) -> list[str]:
    return [*CSV_FIXED_COLUMNS, *SHOP_COLUMNS, *CATALOG_COLUMNS, *csv_custom_columns(tenant_id)]


def csv_response(filename: str, columns: list[str], rows: list[dict[str, Any]]) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    content = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def stock_item_to_csv_row(item: StockItem, columns: list[str]) -> dict[str, Any]:
    finishes = item.finishes or item.attributes.get("acabamentos") or item.attributes.get("acabamento") or []
    if isinstance(finishes, str): finishes = [part.strip() for part in finishes.split("|") if part.strip()]
    row: dict[str, Any] = {
        "sku": item.sku, "stock_item_id": item.id, "registro": "PRODUTO", "promocional": "nao",
        "tamanho": item.size, "cor": item.color, "cores": " | ".join(item.colors),
        "acabamentos": " | ".join(str(value) for value in finishes), "status": item.status,
        "atributos_json": json.dumps(item.attributes, ensure_ascii=False),
        "nome": item.name,
        "tipo": "VENDA" if item.kind == "sale" else "INTERNO",
        "categoria": item.category,
        "familia": item.family,
        "descricao": item.description,
        "unidade": item.unit,
        "quantidade": item.quantity,
        "estoque_minimo": item.min_quantity,
        "custo": item.cost_price,
        "fornecedor": item.supplier,
        "localizacao": item.location,
        "prazo_arte_dias_uteis": item.art_lead_days,
        "prazo_producao_dias_uteis": item.production_lead_days,
    }
    for column in columns:
        if column.startswith("custom."):
            value = item.attributes.get(column.removeprefix("custom."), "")
            row[column] = "sim" if value is True else "nao" if value is False else value
    return row


def normalize_import_headers(row: dict[str | None, Any]) -> dict[str, Any]:
    return {str(key or "").strip().casefold(): value for key, value in row.items()}


def import_kind(raw_value: Any) -> StockKind:
    normalized_value = normalize_text(raw_value or "venda")
    if normalized_value in {"venda", "sale", "produto", "comercial"}:
        return "sale"
    if normalized_value in {"interno", "internal", "insumo"}:
        return "internal"
    raise ValueError('"tipo" precisa ser VENDA ou INTERNO.')


def parse_import_row(row: dict[str | None, Any], row_number: int, tenant_id: str) -> dict[str, Any]:
    values = normalize_import_headers(row)
    sku = str(values.get("sku") or "").strip()
    name = str(values.get("nome") or values.get("name") or "").strip()
    category = str(values.get("categoria") or "").strip()
    if not sku:
        raise ValueError("SKU obrigatorio.")
    if not name:
        raise ValueError("Nome obrigatorio.")
    if not category:
        raise ValueError("Categoria obrigatoria para validar as colunas personalizadas.")
    if not find_category_by_name(category, tenant_id):
        raise ValueError(f'Categoria "{category}" nao esta cadastrada.')

    attributes = {
        key.removeprefix("custom."): value
        for key, value in values.items()
        if key.startswith("custom.") and str(value or "").strip()
    }
    try:
        normalized_attributes = normalize_product_attributes(category, tenant_id, attributes)
        quantity = parse_decimal(values.get("quantidade"))
        min_quantity = parse_decimal(values.get("estoque_minimo"))
        cost_price = parse_decimal(values.get("custo"))
        art_lead_days = parse_decimal(values.get("prazo_arte_dias_uteis"))
        production_lead_days = parse_decimal(values.get("prazo_producao_dias_uteis"))
    except (ValueError, HTTPException) as error:
        detail = error.detail if isinstance(error, HTTPException) else str(error)
        raise ValueError(detail) from error
    if not all(math.isfinite(value) for value in [quantity, min_quantity, cost_price, art_lead_days, production_lead_days]):
        raise ValueError("Valores numéricos precisam ser finitos.")
    if art_lead_days > 365 or production_lead_days > 365:
        raise ValueError("Prazos não podem ultrapassar 365 dias úteis.")
    if quantity < 0 or min_quantity < 0 or cost_price < 0 or art_lead_days < 0 or production_lead_days < 0:
        raise ValueError("Quantidade, minimo, custo e prazos nao podem ser negativos.")
    if not art_lead_days.is_integer() or not production_lead_days.is_integer():
        raise ValueError("Os prazos de arte e producao devem ser dias uteis inteiros.")
    extra = {}
    for column, field in [("tamanho", "size"), ("cor", "color"), ("status", "status")]:
        if column in values: extra[field] = str(values.get(column) or "").strip()
    for column, field in [("cores", "colors"), ("acabamentos", "finishes")]:
        if column in values: extra[field] = list(dict.fromkeys(v.strip() for v in str(values.get(column) or "").split("|") if v.strip()))
    raw_attributes = values.get("atributos_json")
    if raw_attributes:
        try:
            saved_attributes = json.loads(raw_attributes)
            if not isinstance(saved_attributes, dict): raise ValueError()
        except (ValueError, TypeError): raise ValueError("atributos_json precisa conter um objeto JSON válido.") from None
        for key in values:
            if key.startswith("custom."): saved_attributes.pop(key[7:], None)
        normalized_attributes = {**saved_attributes, **normalized_attributes}
    shop_prices = parse_shop_columns(values)
    if shop_prices and import_kind(values.get("tipo")) != "sale":
        raise ValueError("Preços de venda só podem ser vinculados a itens do tipo VENDA.")
    return {
        **extra,
        "shop_prices": shop_prices,
        "row": row_number,
        "sku": sku,
        "name": name,
        "kind": import_kind(values.get("tipo")),
        "category": category,
        "family": str(values.get("familia") or "").strip(),
        "description": str(values.get("descricao") or "").strip(),
        "unit": str(values.get("unidade") or "UN").strip().upper() or "UN",
        "quantity": quantity,
        "min_quantity": min_quantity,
        "cost_price": cost_price,
        "supplier": str(values.get("fornecedor") or "").strip(),
        "location": str(values.get("localizacao") or "").strip(),
        "art_lead_days": int(art_lead_days),
        "production_lead_days": int(production_lead_days),
        "attributes": normalized_attributes,
    }


def purge_expired_import_previews() -> None:
    now = datetime.now(timezone.utc)
    expired_ids = [preview_id for preview_id, preview in IMPORT_PREVIEWS.items() if preview["expires_at"] <= now]
    for preview_id in expired_ids:
        IMPORT_PREVIEWS.pop(preview_id, None)


@app.get("/health")
async def health() -> dict[str, Any]:
    mode = postgres_mode("stock")
    return {"ok": True, "service": "Chronos Stock API", "storage_mode": mode, "storage": "PostgreSQL" if mode == "primary" else str(STOCK_DATA_PATH)}


@app.get("/stock/items")
async def list_items(kind: StockKind | None = Query(default=None), tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    if postgres_mode("stock") == "primary":
        load_stock_data()
    items = all_items_for_tenant(tenant_id)
    if kind:
        items = [item for item in items if item.kind == kind]
    return {"ok": True, "items": [item.model_dump() for item in items]}


@app.post("/stock/items")
async def create_item(payload: CreateStockItemRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    if payload.sku.strip():
        assert_available_sku(payload.sku, tenant_id)
    display_name = build_display_name(payload.family, payload.size, payload.name)
    item_name = payload.name.strip() or display_name
    if not item_name:
        raise HTTPException(status_code=422, detail="Informe uma familia, tamanho ou nome do produto.")
    item = StockItem(
        id=make_item_id(payload.kind, item_name, tenant_id),
        tenant_id=tenant_id,
        kind=payload.kind,
        name=item_name,
        sku=payload.sku.strip(),
        description=payload.description.strip(),
        category=payload.category.strip(),
        family=payload.family.strip(),
        size=payload.size.strip(),
        color=payload.color.strip(),
        finishes=[value.strip() for value in payload.finishes if value.strip()],
        colors=[color.strip() for color in payload.colors if color.strip()] or ([payload.color.strip()] if payload.color.strip() else []),
        display_name=display_name or item_name,
        unit=payload.unit.strip().upper() or "UN",
        quantity=payload.quantity,
        min_quantity=payload.min_quantity,
        cost_price=payload.cost_price,
        supplier=payload.supplier.strip() if payload.kind == "sale" else "",
        location=payload.location.strip(),
        art_lead_days=payload.art_lead_days if payload.kind == "sale" else 0,
        production_lead_days=payload.production_lead_days if payload.kind == "sale" else 0,
        attributes=normalize_product_attributes(payload.category.strip(), tenant_id, payload.attributes),
    )
    target = SALE_ITEMS if item.kind == "sale" else INTERNAL_ITEMS
    target.append(item)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "item": item.model_dump()}


@app.delete("/stock/items/{item_id}")
async def delete_item(item_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    for collection in (SALE_ITEMS, INTERNAL_ITEMS):
        item = next((stock_item for stock_item in collection if stock_item.id == item_id and stock_item.tenant_id == tenant_id), None)
        if item:
            collection.remove(item)
            write_ai_snapshot(tenant_id)
            return {"ok": True, "item": item.model_dump()}
    raise HTTPException(status_code=404, detail="Item nao encontrado.")


@app.patch("/stock/items/{item_id}")
async def update_item(item_id: str, payload: UpdateStockItemRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    item = find_item(item_id, tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")

    if payload.sku is not None:
        if payload.sku.strip():
            assert_available_sku(payload.sku, tenant_id, item.id)
        item.sku = payload.sku.strip()
    if payload.description is not None:
        item.description = payload.description.strip()
    if payload.category is not None:
        item.category = payload.category.strip()
    if payload.family is not None:
        item.family = payload.family.strip()
    if payload.size is not None:
        item.size = payload.size.strip()
    if payload.color is not None:
        item.color = payload.color.strip()
    if payload.finishes is not None:
        item.finishes = [value.strip() for value in payload.finishes if value.strip()]
    if payload.colors is not None:
        item.colors = [color.strip() for color in payload.colors if color.strip()]
    if payload.unit is not None:
        item.unit = payload.unit.strip().upper() or "UN"
    if payload.quantity is not None:
        item.quantity = payload.quantity
    if payload.min_quantity is not None:
        item.min_quantity = payload.min_quantity
    if payload.cost_price is not None:
        item.cost_price = payload.cost_price
    if payload.supplier is not None:
        item.supplier = payload.supplier.strip() if item.kind == "sale" else ""
    if payload.location is not None:
        item.location = payload.location.strip()
    if payload.art_lead_days is not None:
        item.art_lead_days = payload.art_lead_days if item.kind == "sale" else 0
    if payload.production_lead_days is not None:
        item.production_lead_days = payload.production_lead_days if item.kind == "sale" else 0

    if payload.attributes is not None or payload.category is not None:
        item.attributes = normalize_product_attributes(
            item.category,
            tenant_id,
            payload.attributes or {},
            current=item.attributes,
        )

    display_name = build_display_name(item.family, item.size, payload.name or item.name)
    if payload.name is not None:
        item.name = payload.name.strip() or display_name or item.name
    elif display_name:
        item.name = display_name
    item.display_name = display_name or item.name
    if item.color and item.color not in item.colors:
        item.colors = [item.color]

    write_ai_snapshot(tenant_id)
    return {"ok": True, "item": item.model_dump()}


@app.get("/stock/import-export/template")
async def download_import_template(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> StreamingResponse:
    tenant_id = normalize_tenant_id(tenant_id)
    columns = csv_columns(tenant_id)
    return csv_response("chronos-stock-modelo.csv", columns, [])


@app.get("/stock/import-export/products")
async def export_products_csv(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> StreamingResponse:
    tenant_id = normalize_tenant_id(tenant_id)
    columns = csv_columns(tenant_id)
    user = current_user.get()
    if not user: raise HTTPException(401, "Autenticação necessária.")
    user.require_permission("loja.store.manage")
    if postgres_mode("stock") != "primary":
        raise HTTPException(409, "A exportação unificada requer o armazenamento integrado Stock/Loja.")
    prices = await asyncio.to_thread(run_postgres, read_shop_prices(tenant_id))
    rows = [{**stock_item_to_csv_row(item, columns), **prices.get(item.id, {})} for item in all_items_for_tenant(tenant_id)]
    details = await asyncio.to_thread(run_postgres, read_catalog_details(tenant_id))
    return csv_response("chronos-stock-produtos.csv", columns, auxiliary_rows(rows, details))


@app.post("/stock/import-export/preview")
async def preview_products_import(
    file: UploadFile = File(...),
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Envie um arquivo CSV.")
    try:
        raw_content = await file.read()
        decoded = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="O CSV precisa estar em UTF-8.") from error
    sample = decoded[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,").delimiter
    except csv.Error:
        delimiter = ";"
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)
    headers = [str(header or "").strip().casefold() for header in (reader.fieldnames or [])]
    missing_headers = [header for header in ("sku", "nome", "categoria") if header not in headers]
    if missing_headers:
        raise HTTPException(status_code=422, detail=f"CSV sem coluna(s) obrigatoria(s): {', '.join(missing_headers)}.")

    shop_prices = await asyncio.to_thread(run_postgres, read_shop_prices(tenant_id)) if "loja_produto_id" in headers and postgres_mode("stock") == "primary" else {}
    details = await asyncio.to_thread(run_postgres, read_catalog_details(tenant_id)) if "registro" in headers and postgres_mode("stock") == "primary" else {}
    auxiliary = []
    seen_records = set()
    valid_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    duplicate_rows: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in row.values()):
            continue
        try:
            values = normalize_import_headers(row)
            record = str(values.get("registro") or "PRODUTO").strip().upper()
            if record != "PRODUTO":
                user = current_user.get()
                if not user: raise HTTPException(401, "Autenticação necessária.")
                user.require_permission("loja.store.manage")
                existing = find_item_by_sku(str(values.get("sku") or "").strip(), tenant_id)
                linked = shop_prices.get(existing.id, {}).get("loja_produto_id") if existing else None
                parsed_aux = parse_auxiliary(values, existing, details, linked)
                identity = ("PROMOCAO", parsed_aux["id"]) if record == "PROMOCAO" else (parsed_aux["origin"], parsed_aux["product_id"], parsed_aux["stock_item_id"] if parsed_aux["origin"] == "CADASTRO" else "", parsed_aux["id"])
                if identity in seen_records: raise ValueError("Registro de promoção/adicional repetido no arquivo.")
                seen_records.add(identity)
                auxiliary.append(parsed_aux)
                continue
            parsed = parse_import_row(row, row_number, tenant_id)
            if values.get("stock_item_id"):
                target = find_item_by_sku(parsed["sku"], tenant_id)
                if not target or target.id != values["stock_item_id"]: raise ValueError("Preserve SKU e stock_item_id do produto exportado.")
            normalized_sku = normalize_text(parsed["sku"])
            if normalized_sku in seen_skus:
                raise ValueError(f'SKU "{parsed["sku"]}" aparece mais de uma vez no arquivo.')
            seen_skus.add(normalized_sku)
            existing = find_item_by_sku(parsed["sku"], tenant_id)
            if parsed.get("shop_prices"):
                user = current_user.get()
                if not user: raise HTTPException(401, "Autenticação necessária.")
                user.require_permission("loja.store.manage")
                if not existing or shop_prices.get(existing.id, {}).get("loja_produto_id") != parsed["shop_prices"]["product_id"]:
                    raise ValueError("Produto não vinculado à Loja ou vínculo diferente. Sincronize na Loja e exporte novamente.")
            if existing:
                parsed["existing_item_id"] = existing.id
                duplicate_rows.append({"row": row_number, "sku": parsed["sku"], "item": existing.display_name or existing.name})
            valid_rows.append(parsed)
        except ValueError as error:
            errors.append({"row": row_number, "message": str(error)})

    purge_expired_import_previews()
    preview_id = uuid4().hex
    IMPORT_PREVIEWS[preview_id] = {
        "tenant_id": tenant_id,
        "rows": valid_rows,
        "auxiliary": auxiliary,
        "errors": errors,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return {
        "ok": True,
        "preview_id": preview_id,
        "expires_in_minutes": 30,
        "summary": {
            "total_rows": len(valid_rows) + len(auxiliary) + len(errors),
            "ready": len(valid_rows) + len(auxiliary),
            "extra_updates": sum(row["record"] != "PROMOCAO" for row in auxiliary),
            "promotion_updates": sum(row["record"] == "PROMOCAO" for row in auxiliary),
            "errors": len(errors),
            "duplicates": len(duplicate_rows),
            "shop_updates": sum(bool(row.get("shop_prices")) for row in valid_rows),
        },
        "duplicates": duplicate_rows,
        "errors": errors,
        "rows": [
            {key: value for key, value in row.items() if key not in {"existing_item_id"}}
            for row in valid_rows[:50]
        ],
    }


@app.post("/stock/import-export/commit")
async def commit_products_import(payload: ImportCommitRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    purge_expired_import_previews()
    preview = IMPORT_PREVIEWS.get(payload.preview_id)
    if not preview or preview["tenant_id"] != tenant_id:
        raise HTTPException(status_code=404, detail="Previa expirada ou nao encontrada. Gere uma nova previa.")
    if preview["errors"]:
        raise HTTPException(status_code=422, detail="Corrija os erros da previa antes de importar.")

    if preview.get("auxiliary") or any(row.get("shop_prices") for row in preview["rows"]):
        user = current_user.get()
        if not user: raise HTTPException(401, "Autenticação necessária.")
        user.require_permission("loja.store.manage")
        if postgres_mode("stock") != "primary": raise HTTPException(409, "Importação conjunta requer armazenamento integrado.")
    created = updated = skipped = 0
    candidates, prices = [], []
    for row in preview["rows"]:
        existing = find_item_by_sku(row["sku"], tenant_id)
        if existing and payload.duplicate_strategy == "skip":
            skipped += 1
            continue
        fields = {key: value for key, value in row.items() if key in StockItem.model_fields}
        fields.update(tenant_id=tenant_id, id=existing.id if existing else make_item_id(row["kind"], row["name"], tenant_id))
        item = StockItem(**{**(existing.model_dump() if existing else {}), **fields})
        if item.kind == "internal": item.supplier, item.art_lead_days, item.production_lead_days = "", 0, 0
        item.display_name = build_display_name(item.family, item.size, item.name)
        candidates.append(item)
        if row.get("shop_prices"): prices.append((item.id, row["shop_prices"]))
        if existing: updated += 1
        else: created += 1
    auxiliary = preview.get("auxiliary", []) if payload.duplicate_strategy == "update" else []
    warning = None
    if postgres_mode("stock") == "primary":
        stock_payload = {
            "sale_items": [item.model_dump() for item in candidates if item.kind == "sale"],
            "internal_items": [item.model_dump() for item in candidates if item.kind == "internal"],
            "categories": [category for category in STOCK_CATEGORIES if category["tenant_id"] == tenant_id],
        }
        warning = await asyncio.to_thread(run_postgres, commit_stock_shop(tenant_id, stock_payload, prices, auxiliary)) if auxiliary else await asyncio.to_thread(run_postgres, commit_stock_shop(tenant_id, stock_payload, prices))
    # Only update the in-memory view after both modules commit successfully.
    changed_ids = {item.id for item in candidates}
    SALE_ITEMS[:] = [item for item in SALE_ITEMS if not (item.tenant_id == tenant_id and item.id in changed_ids)] + [item for item in candidates if item.kind == "sale"]
    INTERNAL_ITEMS[:] = [item for item in INTERNAL_ITEMS if not (item.tenant_id == tenant_id and item.id in changed_ids)] + [item for item in candidates if item.kind == "internal"]
    if postgres_mode("stock") != "primary": write_ai_snapshot(tenant_id)
    IMPORT_PREVIEWS.pop(payload.preview_id, None)
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "shop_updated": len(prices), "extras_updated": sum(row["record"] != "PROMOCAO" for row in auxiliary), "promotions_updated": sum(row["record"] == "PROMOCAO" for row in auxiliary), "total": created + updated + skipped, "warning": warning}


@app.get("/stock/categories")
async def list_categories(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    categories = [ensure_family_colors(category) for category in STOCK_CATEGORIES if category["tenant_id"] == tenant_id]
    return {"ok": True, "categories": categories}


@app.post("/stock/categories")
async def create_category(payload: CreateCategoryRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    category = {
        "id": make_category_id(payload.name, tenant_id),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "families": [],
        "attributes": [],
    }
    STOCK_CATEGORIES.append(category)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category}


@app.delete("/stock/categories/{category_id}")
async def delete_category(category_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    STOCK_CATEGORIES.remove(category)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category}


@app.post("/stock/categories/{category_id}/attributes")
async def create_category_attribute(category_id: str, payload: CreateCategoryAttributeRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    category = ensure_family_colors(category)
    key = make_attribute_key(payload.name, category, payload.key)
    options = list(dict.fromkeys(option.strip() for option in payload.options if option.strip()))
    if payload.type == "select" and not options:
        raise HTTPException(status_code=422, detail="Uma coluna de lista precisa ter ao menos uma opcao.")
    attribute = {
        "id": make_attribute_id(key, category),
        "name": payload.name.strip(),
        "key": key,
        "type": payload.type,
        "role": payload.role,
        "options": options,
        "required": payload.required,
        "active": True,
    }
    category["attributes"].append(attribute)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "attribute": attribute}


@app.patch("/stock/categories/{category_id}/attributes/{attribute_id}")
async def update_category_attribute(category_id: str, attribute_id: str, payload: UpdateCategoryAttributeRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    category = ensure_family_colors(category)
    attribute = next((item for item in category["attributes"] if item["id"] == attribute_id), None)
    if not attribute:
        raise HTTPException(status_code=404, detail="Coluna nao encontrada.")
    if payload.name is not None:
        attribute["name"] = payload.name.strip()
    if payload.type is not None:
        attribute["type"] = payload.type
    if payload.role is not None:
        attribute["role"] = payload.role
    if payload.options is not None:
        options = list(dict.fromkeys(option.strip() for option in payload.options if option.strip()))
        if attribute.get("type") == "select" and not options:
            raise HTTPException(status_code=422, detail="Uma coluna de lista precisa ter ao menos uma opcao.")
        attribute["options"] = options
    if payload.required is not None:
        attribute["required"] = payload.required
    if payload.active is not None:
        attribute["active"] = payload.active
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "attribute": attribute}


@app.delete("/stock/categories/{category_id}/attributes/{attribute_id}")
async def archive_category_attribute(category_id: str, attribute_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    category = ensure_family_colors(category)
    attribute = next((item for item in category["attributes"] if item["id"] == attribute_id), None)
    if not attribute:
        raise HTTPException(status_code=404, detail="Coluna nao encontrada.")
    attribute["active"] = False
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "attribute": attribute}


@app.post("/stock/categories/{category_id}/families")
async def create_family(category_id: str, payload: CreateFamilyRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    family = {"id": make_family_id(payload.name, category), "name": payload.name.strip(), "colors": []}
    category["families"].append(family)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "family": family}


@app.delete("/stock/categories/{category_id}/families/{family_id}")
async def delete_family(category_id: str, family_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    family = find_family(category, family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Familia nao encontrada.")
    category["families"].remove(family)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "family": family}


@app.post("/stock/categories/{category_id}/families/{family_id}/colors")
async def create_color(category_id: str, family_id: str, payload: CreateColorRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    family = find_family(category, family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Familia nao encontrada.")
    color = {"id": make_color_id(payload.name, family), "name": payload.name.strip()}
    family["colors"].append(color)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "family": family, "color": color}


@app.get("/stock/suppliers")
async def list_suppliers(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    suppliers = [supplier for supplier in STOCK_SUPPLIERS if supplier["tenant_id"] == tenant_id]
    return {"ok": True, "suppliers": suppliers}


@app.post("/stock/suppliers")
async def create_supplier(payload: CreateSupplierRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    supplier = {
        "id": make_supplier_id(payload.name, tenant_id),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "document": payload.document.strip(),
        "contact_name": payload.contact_name.strip(),
        "phone": payload.phone.strip(),
        "email": payload.email.strip(),
        "cep": payload.cep.strip(),
        "address": payload.address.strip(),
        "city": payload.city.strip(),
        "state": payload.state.strip(),
    }
    STOCK_SUPPLIERS.append(supplier)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "supplier": supplier}


@app.delete("/stock/suppliers/{supplier_id}")
async def delete_supplier(supplier_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    supplier = find_supplier(supplier_id, tenant_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornecedor nao encontrado.")
    STOCK_SUPPLIERS.remove(supplier)
    for item in SALE_ITEMS:
        if item.tenant_id == tenant_id and item.supplier == supplier["name"]:
            item.supplier = ""
    write_ai_snapshot(tenant_id)
    return {"ok": True, "supplier": supplier}


@app.delete("/stock/categories/{category_id}/families/{family_id}/colors/{color_id}")
async def delete_color(category_id: str, family_id: str, color_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    category = find_category(category_id, tenant_id)
    if not category:
        raise HTTPException(status_code=404, detail="Categoria nao encontrada.")
    family = find_family(category, family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Familia nao encontrada.")
    color = next((item for item in family["colors"] if item["id"] == color_id), None)
    if not color:
        raise HTTPException(status_code=404, detail="Cor nao encontrada.")
    family["colors"].remove(color)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "category": category, "family": family, "color": color}


@app.get("/stock/service-resources")
async def list_service_resources(
    tenant_id: str = Query(default=DEFAULT_TENANT_ID),
    q: str = "",
    include_disabled: bool = True,
) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    query = q.strip().lower()
    resources = [resource for resource in SERVICE_RESOURCES if resource["tenant_id"] == tenant_id]
    if not include_disabled:
        resources = [resource for resource in resources if resource.get("status") != "disabled"]
    if query:
        resources = [
            resource
            for resource in resources
            if query in " ".join(
                [
                    resource.get("name", ""),
                    resource.get("kind", ""),
                    resource.get("status", ""),
                    resource.get("notes", ""),
                ]
            ).lower()
        ]
    resources.sort(key=lambda item: (item.get("status") != "active", item.get("name", "")))
    return {"ok": True, "resources": resources}


@app.post("/stock/service-resources")
async def create_service_resource(payload: ServiceResourceRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    resource = {
        "id": make_service_resource_id(payload.name, tenant_id),
        "tenant_id": tenant_id,
        "name": payload.name.strip(),
        "kind": payload.kind.strip() or "equipment",
        "quantity": payload.quantity,
        "status": payload.status,
        "unavailable_until": payload.unavailable_until.strip(),
        "notes": payload.notes.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    SERVICE_RESOURCES.append(resource)
    save_stock_data()
    return {"ok": True, "resource": resource}


@app.patch("/stock/service-resources/{resource_id}")
async def update_service_resource(resource_id: str, payload: ServiceResourceUpdateRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    resource = find_service_resource(resource_id, tenant_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Recurso nao encontrado.")
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("tenant_id", None)
    for key, value in updates.items():
        resource[key] = value.strip() if isinstance(value, str) else value
    resource["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_stock_data()
    return {"ok": True, "resource": resource}


@app.delete("/stock/service-resources/{resource_id}")
async def delete_service_resource(resource_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    resource = find_service_resource(resource_id, tenant_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Recurso nao encontrado.")
    SERVICE_RESOURCES.remove(resource)
    save_stock_data()
    return {"ok": True, "resource": resource}


def add_stock_item_quantity(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    item = find_item(item_id, tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")

    item.quantity = round(item.quantity + payload.quantity, 3)
    movement = register_movement(item, "add", payload)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "item": item.model_dump(), "movement": movement}


def withdraw_stock_item_quantity(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    item = find_item(item_id, tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")
    if payload.quantity > item.quantity:
        raise HTTPException(status_code=409, detail="Quantidade solicitada maior que o saldo disponivel.")

    item.quantity = round(item.quantity - payload.quantity, 3)
    movement = register_movement(item, "withdraw", payload)
    write_ai_snapshot(tenant_id)
    return {"ok": True, "item": item.model_dump(), "movement": movement, "withdrawal": movement}


@app.post("/stock/items/{item_id}/add")
async def add_item(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    return add_stock_item_quantity(item_id, payload)


@app.post("/stock/items/{item_id}/withdraw")
async def withdraw_item(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    return withdraw_stock_item_quantity(item_id, payload)


@app.post("/stock/internal/{item_id}/add")
async def add_internal_item(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    item = find_internal_item(item_id, tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item interno nao encontrado.")
    return add_stock_item_quantity(item_id, payload)


@app.post("/stock/internal/{item_id}/withdraw")
async def withdraw_internal_item(item_id: str, payload: MovementRequest) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(payload.tenant_id)
    item = find_internal_item(item_id, tenant_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item interno nao encontrado.")
    return withdraw_stock_item_quantity(item_id, payload)


@app.get("/stock/ai/snapshot")
async def get_ai_snapshot(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    snapshot = write_ai_snapshot(normalize_tenant_id(tenant_id), persist_stock=False)
    return {"ok": True, "snapshot": snapshot}


@app.get("/stock/internal/movements")
async def list_internal_movements(item_id: str | None = Query(default=None), tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    movements = [movement for movement in MOVEMENTS if movement["tenant_id"] == tenant_id]
    if item_id:
        movements = [movement for movement in movements if movement["item_id"] == item_id]
    return {"ok": True, "movements": movements}


@app.get("/stock/internal/withdrawals")
async def list_internal_withdrawals(item_id: str | None = Query(default=None), tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    tenant_id = normalize_tenant_id(tenant_id)
    movements = [movement for movement in MOVEMENTS if movement["type"] == "withdraw" and movement["tenant_id"] == tenant_id]
    if item_id:
        movements = [movement for movement in movements if movement["item_id"] == item_id]
    return {"ok": True, "withdrawals": movements}
