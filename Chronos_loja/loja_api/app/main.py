from __future__ import annotations

import json
import hashlib
from threading import RLock
import secrets
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from os import getenv
from typing import Any, Literal
from urllib.parse import quote, urljoin
from urllib.request import Request
from preview_http import open_local as urlopen
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from preview_config import ROOT
from chronos_auth.integration import install_sso
from chronos_auth.scope import scoped_tenant, current_user
from chronos_auth.services import service_headers, forwarding_headers
from chronos_auth.assets import public_image_url
from chronos_storage import atomic_write_json
from chronos_storage.runtime_sync import postgres_enabled, postgres_mode, run as run_postgres
from chronos_storage.loja_runtime import load_order_payment_document, load_loja_payload, record_manual_receipt, delete_quote as delete_quote_postgres, delete_order as delete_order_postgres
from chronos_storage.product_extras import product_extras as pg_product_extras, append_extra
from chronos_storage.pdf_header import PdfHeaderPayload, settings as pdf_header_settings
from chronos_storage.client_display import settings as client_display_settings, display_name
from chronos_storage.product_variants import create_variant as pg_create_variant
from chronos_storage.stock_runtime import load_stock_payload
from chronos_storage.nexus_runtime import get_client as pg_get_client, list_clients as pg_list_clients
from chronos_storage.order_numbering import configure as configure_order_numbering, checked_config
from pydantic import BaseModel, Field
from .quote_pdf import build_quote_pdf
from .order_pdf import build_order_pdf
from . import promotions
from chronos_storage.quote_validity import QuoteValidityPayload, settings as quote_validity_settings
from .easy_sales import calculate_totals, discount_amount, money as sale_money, apply_receipt


app = FastAPI(title="Chronos Loja API", version="0.1.0")

install_sso(app, "loja")
app.add_middleware(
    # CORS wraps SSO, including its 401/403 responses.
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:18800", "http://localhost:18800"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DATA_DIR = ROOT / ".local" / "loja"
SHOP_DATA_PATH = DATA_DIR / "loja_data.json"
STOCK_API_URL = "http://127.0.0.1:18815"
CORE_API_URL = "http://127.0.0.1:18802"
NEXUS_API_URL = "http://127.0.0.1:18803"
DEFAULT_TENANT_ID = "demo"
QuoteStatus = Literal["draft", "sent", "approved", "refused", "expired"]
OrderStatus = Literal["new", "paid", "art", "production", "ready_delivery", "finished", "canceled"]
TransactionStatus = Literal["pending", "paid", "partial", "refunded"]


class OrderNumberingPayload(BaseModel):
    prefix: str = Field(default="", max_length=40)
    last_number: int = Field(strict=True, ge=0, le=2147483646)


class ShopConfigPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    store_name: str = ""
    chronos_slug: str = ""
    use_chronos_domain: bool = True
    custom_domain: str = ""
    custom_domain_status: str = "not_configured"
    whatsapp: str = ""
    theme: str = "default"
    banner_title: str = ""
    banner_subtitle: str = ""


class ShopProductUpdatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    published: bool | None = None
    public_name: str | None = None
    public_description: str | None = None
    highlight: bool | None = None
    order: int | None = None
    public_category: str | None = None
    image_url: str | None = None
    visible_stock: bool | None = None
    variant_prices: dict[str, dict[str, Any]] | None = None


class VariantTier(BaseModel):
    minimum_quantity: int = Field(ge=1, le=10000000)
    unit_price: float = Field(gt=0, allow_inf_nan=False, le=1000000000)


class ProductVariantPayload(BaseModel):
    sku: str = Field(default="", max_length=100)
    size: str = Field(default="", max_length=100)
    color: str = Field(default="", max_length=100)
    unit: str = Field(default="UN", min_length=1, max_length=12)
    finishes: list[str] = Field(default_factory=list, max_length=50)
    sale_price: float = Field(ge=0, allow_inf_nan=False, le=1000000000)
    quantity_prices: list[VariantTier] = Field(default_factory=list, max_length=50)


class PromotionPayload(BaseModel):
    product_id: str
    stock_item_id: str
    name: str = Field(min_length=1, max_length=200)
    package_quantity: int = Field(strict=True, ge=1, le=10000000)
    package_price: float = Field(gt=0, allow_inf_nan=False)


class PromotionRenewPayload(BaseModel):
    package_price: float = Field(gt=0, allow_inf_nan=False)


class CartCreatePayload(BaseModel):
    client_company_name: str = Field(default="", max_length=255)
    tenant_id: str = DEFAULT_TENANT_ID
    client_id: str = ""
    client_name: str = ""
    client_phone: str = ""
    source: str = "shop"


class CartItemExtra(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    unit_price: float = Field(gt=0, allow_inf_nan=False)


class ProductExtraPayload(CartItemExtra):
    stock_item_id: str = Field(min_length=1)
    apply_to_family: bool = False


class CartItemPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    product_id: str
    stock_item_id: str
    quantity: float = Field(default=1, gt=0)
    notes: str = ""
    finishes: list[str] | None = None
    extras: list[CartItemExtra] | None = Field(default=None, max_length=30)
    extra_ids: list[str] | None = Field(default=None, max_length=30)


class CartTotalsPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    discount: float = Field(default=0, ge=0, allow_inf_nan=False)
    discount_type: Literal["amount", "percent"] = "amount"
    discount_value: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    freight: float = Field(default=0, ge=0, allow_inf_nan=False)
    notes: str = ""


class ItemDiscountPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    discount_type: Literal["amount", "percent"] = "amount"
    discount_value: float = Field(default=0, ge=0, allow_inf_nan=False)


class ManualReceiptPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    amount: float = Field(gt=0, allow_inf_nan=False)
    method: Literal["pix", "cash", "card", "transfer", "other"]
    paid_on: date
    notes: str = Field(default="", max_length=2000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class QuoteCreatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    cart_id: str
    valid_days: int = Field(default=7, ge=1, le=90)


class QuoteStatusPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    status: QuoteStatus


class OrderCreatePayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    quote_id: str | None = None
    cart_id: str | None = None


class OrderStatusPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    status: OrderStatus


class TransactionPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    order_id: str
    amount: float = Field(gt=0)
    method: str = "manual"
    status: TransactionStatus = "paid"
    reference: str = ""
    notes: str = ""


class RefundPayload(BaseModel):
    tenant_id: str = DEFAULT_TENANT_ID
    order_id: str
    amount: float = Field(gt=0)
    reason: str = ""
    items: list[dict[str, Any]] = []


class PublicCartItemPayload(BaseModel):
    token: str
    product_id: str
    stock_item_id: str
    quantity: float = Field(default=1, gt=0)
    notes: str = ""


class PublicCheckoutPayload(BaseModel):
    token: str
    cart_id: str
    client_name: str = Field(min_length=2, max_length=160)
    client_phone: str = Field(min_length=8, max_length=40)
    email: str = Field(default="", max_length=200)
    company_name: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1200)
    valid_days: int = Field(default=7, ge=1, le=90)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "loja"


def empty_data() -> dict[str, Any]:
    return {
        "schema": "chronos_loja_data_v1",
        "saved_at": now_iso(),
        "configs": {},
        "products": {},
        "carts": {},
        "quotes": {},
        "orders": {},
        "transactions": {},
        "refunds": {},
    }


def load_data() -> dict[str, Any]:
    if postgres_mode("loja") == "primary":
        return run_postgres(load_loja_payload())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SHOP_DATA_PATH.exists():
        data = empty_data()
        save_data(data)
        return data
    return json.loads(SHOP_DATA_PATH.read_text(encoding="utf-8"))


def save_data(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["saved_at"] = now_iso()
    atomic_write_json(SHOP_DATA_PATH, data)


def tenant_bucket(data: dict[str, Any], bucket: str, tenant_id: str) -> dict[str, Any]:
    return data.setdefault(bucket, {}).setdefault(tenant_id, {})


def default_config(tenant_id: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "store_name": "Minha loja",
        "chronos_slug": tenant_id,
        "use_chronos_domain": True,
        "custom_domain": "",
        "custom_domain_status": "not_configured",
        "whatsapp": "",
        "theme": "default",
        "banner_title": "Catalogo online",
        "banner_subtitle": "Produtos selecionados para venda.",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def stock_items(tenant_id: str) -> list[dict[str, Any]]:
    if postgres_mode("stock") == "primary":
        return [item for item in run_postgres(load_stock_payload())["sale_items"] if item["tenant_id"] == tenant_id]
    url = f"{STOCK_API_URL}/stock/items?tenant_id={quote(tenant_id)}&kind=sale"
    try:
        with urlopen(Request(url, headers=service_headers("loja", tenant_id)), timeout=5) as response:
            data = json.load(response)
    except OSError as error:
        raise HTTPException(503, "Estoque indisponível. Tente novamente.") from error
    except (ValueError, UnicodeError) as error:
        raise HTTPException(502, "Resposta inválida do Estoque.") from error
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or any(
        not isinstance(item, dict) or item.get("tenant_id") != tenant_id or item.get("kind") != "sale"
        for item in items
    ):
        raise HTTPException(502, "Resposta inesperada do Estoque para esta empresa.")
    return items


def group_stock_families(tenant_id: str) -> list[dict[str, Any]]:
    families: dict[tuple[str, str], dict[str, Any]] = {}
    for item in stock_items(tenant_id):
        category = item.get("category") or "Sem categoria"
        family = item.get("family") or item.get("name") or "Produto"
        key = (category, family)
        if key not in families:
            families[key] = {
                "id": f"{tenant_id}:{slugify(category)}:{slugify(family)}",
                "tenant_id": tenant_id,
                "category": category,
                "family": family,
                "public_name": family,
                "public_description": item.get("description") or "",
                "published": False,
                "highlight": False,
                "order": 0,
                "public_category": category,
                "image_url": "",
                "visible_stock": True,
                "variants": [],
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        families[key]["variants"].append(
            {
                "stock_item_id": item.get("id"),
                "sku": item.get("sku"),
                "size": item.get("size"),
                "color": item.get("color") or (item.get("colors") or [""])[0],
                "finishes": item.get("finishes") or [],
                "unit": item.get("unit"),
                "quantity": item.get("quantity"),
                "min_quantity": item.get("min_quantity"),
                "art_lead_days": int(item.get("art_lead_days") or 0),
                "production_lead_days": int(item.get("production_lead_days") or 0),
                "sale_price": float(item.get("sale_price") or 0),
                "promotional_price": 0,
                "sellable": True,
                "available": float(item.get("quantity") or 0) > 0,
            }
        )
    return list(families.values())


def resolve_family_ids(families: list[dict], saved: dict) -> None:
    groups: dict[str, list[dict]] = {}
    for product in families:
        groups.setdefault(product["id"], []).append(product)
    for legacy_id, group in groups.items():
        legacy = saved.get(legacy_id)
        owner = None
        if legacy is not None:
            source = legacy.get("stock_family")
            if source:
                owner = next((p for p in group if [p["category"], p["family"]] == source), None)
            else:
                # Versões anteriores guardavam os IDs das variantes, mesmo com nome público editado.
                known = set(legacy.get("variant_prices") or {})
                matches = [p for p in group if any(str(v["stock_item_id"]) in known for v in p["variants"])]
                if len(matches) == 1:
                    owner = matches[0]
                elif len(group) == 1 and not known:
                    owner = group[0]
                elif len(matches) > 1 or not known:
                    raise HTTPException(409, "Catálogo antigo ambíguo. Diferencie as famílias no Estoque e reimporte.")
        for product in group:
            source = [product["category"], product["family"]]
            digest = hashlib.sha256(json.dumps(source, ensure_ascii=False).encode()).hexdigest()
            distinct_id = f"{legacy_id}~{digest}"
            if distinct_id in saved or (product is not owner and (legacy is not None or len(group) > 1)):
                product["id"] = distinct_id


def merge_product_config(base: dict[str, Any], saved: dict[str, Any] | None) -> dict[str, Any]:
    if not saved:
        return base
    saved_variant_prices = saved.get("variant_prices") or {}
    merged = {**base, **{key: value for key, value in saved.items() if key not in {"variants", "variant_prices"}}}
    merged["variant_prices"] = saved_variant_prices
    merged["variants"] = []
    for variant in base["variants"]:
        stock_item_id = str(variant.get("stock_item_id") or "")
        variant_config = saved_variant_prices.get(stock_item_id) or {}
        merged["variants"].append(
            {
                **variant,
                "sale_price": float(variant_config.get("sale_price") or 0),
                "promotional_price": float(variant_config.get("promotional_price") or 0),
                "quantity_prices": normalize_quantity_prices(variant_config.get("quantity_prices")),
                "registered_extras": variant_config.get("registered_extras") or [],
                "source_lot_totals": variant_config.get("source_lot_totals") or {},
                "sellable": bool(variant_config.get("sellable", True)),
            }
        )
    return merged


def list_shop_products(tenant_id: str) -> list[dict[str, Any]]:
    data = load_data()
    saved_products = data.get("products", {}).get(tenant_id, {})
    families = group_stock_families(tenant_id)
    resolve_family_ids(families, saved_products)
    return configured_products(tenant_id, families, saved_products)


def configured_products(tenant_id: str, families: list[dict], saved_products: dict) -> list[dict]:
    products = [merge_product_config(product, saved_products.get(product["id"])) for product in families]
    extras_by_product = saved_product_extras(tenant_id)
    for product in products:
        for variant in product.get("variants", []):
            variant["registered_extras"] = [*(variant.get("registered_extras") or []), *[extra for extra in extras_by_product.get(product["id"], []) if not extra.get("stock_item_id") or extra["stock_item_id"] == str(variant["stock_item_id"])]]
    products += promotions.products(products, promotions.store(tenant_id))
    return sorted(products, key=lambda item: (item.get("order") or 0, item.get("public_name") or item.get("family") or ""))


def find_product_variant(tenant_id: str, product_id: str, stock_item_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    product = next((item for item in list_shop_products(tenant_id) if item["id"] == product_id), None)
    if not product or not product.get("published", False):
        raise HTTPException(status_code=404, detail="Produto publicado nao encontrado.")
    variant = next((item for item in product.get("variants", []) if str(item.get("stock_item_id")) == str(stock_item_id)), None)
    if not variant or not variant.get("sellable", True):
        raise HTTPException(status_code=404, detail="Variacao vendavel nao encontrada.")
    return product, variant


def normalize_quantity_prices(raw_prices: Any) -> list[dict[str, float]]:
    if not isinstance(raw_prices, list):
        return []
    prices_by_minimum: dict[float, float] = {}
    for raw_price in raw_prices:
        if not isinstance(raw_price, dict):
            continue
        try:
            minimum_quantity = float(raw_price.get("minimum_quantity") or 0)
            unit_price = float(raw_price.get("unit_price") or 0)
        except (TypeError, ValueError):
            continue
        if minimum_quantity <= 0 or unit_price < 0:
            continue
        prices_by_minimum[minimum_quantity] = unit_price
    return [
        {"minimum_quantity": minimum_quantity, "unit_price": unit_price}
        for minimum_quantity, unit_price in sorted(prices_by_minimum.items())
    ]


def resolve_variant_price(variant: dict[str, Any], quantity: float) -> dict[str, Any]:
    if variant.get("promotion"):
        return promotions.price(variant, quantity)
    quantity_prices = normalize_quantity_prices(variant.get("quantity_prices"))
    if quantity_prices:
        first_tier = quantity_prices[0]
        if quantity < first_tier["minimum_quantity"]:
            raise HTTPException(
                status_code=409,
                detail=f"Quantidade minima para esta variacao: {first_tier['minimum_quantity']:g} {variant.get('unit') or 'UN'}.",
            )
        applied_tier = next(
            (tier for tier in reversed(quantity_prices) if quantity >= tier["minimum_quantity"]),
            first_tier,
        )
        promotional = float(variant.get("promotional_price") or 0)
        if promotional > 0:
            return {
                "unit_price": promotional,
                "price_source": "promotional",
                "minimum_quantity": applied_tier["minimum_quantity"],
            }
        source_total = (variant.get("source_lot_totals") or {}).get(str(int(applied_tier["minimum_quantity"])))
        exact_unit = float(source_total) / applied_tier["minimum_quantity"] if source_total else applied_tier["unit_price"]
        # Use the source lot only while its rounded unit price still matches the editable tier.
        use_source_lot = bool(source_total and round(exact_unit, 4) == round(applied_tier["unit_price"], 4))
        return {
            "unit_price": exact_unit if use_source_lot else applied_tier["unit_price"],
            "exact_lot_pricing": use_source_lot,
            "price_source": "quantity_tier",
            "minimum_quantity": applied_tier["minimum_quantity"],
        }

    promotional = float(variant.get("promotional_price") or 0)
    regular = float(variant.get("sale_price") or 0)
    return {
        "unit_price": promotional if promotional > 0 else regular,
        "price_source": "promotional" if promotional > 0 else "regular",
        "minimum_quantity": 0,
    }


def operation_requirements(items: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_items = [item for item in items if isinstance(item, dict)]
    art_lead_days = max((max(0, int(item.get("art_lead_days") or 0)) for item in normalized_items), default=0)
    production_lead_days = max((max(0, int(item.get("production_lead_days") or 0)) for item in normalized_items), default=0)
    requires_art = art_lead_days > 0
    requires_production = production_lead_days > 0
    profile = (
        "art_and_production" if requires_art and requires_production
        else "art" if requires_art
        else "production" if requires_production
        else "ready_delivery"
    )
    estimated_fulfillment_days = max(
        (max(0, int(item.get("art_lead_days") or 0)) + max(0, int(item.get("production_lead_days") or 0)) for item in normalized_items),
        default=0,
    )
    return {
        "profile": profile,
        "requires_art": requires_art,
        "requires_production": requires_production,
        "art_lead_days": art_lead_days,
        "production_lead_days": production_lead_days,
        "estimated_fulfillment_days": estimated_fulfillment_days,
    }


def status_after_payment(order: dict[str, Any]) -> OrderStatus:
    requirements = order.get("operation_requirements") or operation_requirements(order.get("items") or [])
    if requirements.get("requires_art"):
        return "art"
    if requirements.get("requires_production"):
        return "production"
    return "ready_delivery"


def business_day_due_date(days: int, start: date | None = None) -> str:
    current = start or datetime.now(timezone.utc).date()
    remaining = max(0, int(days))
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current.isoformat()


def apply_operational_timeline(order: dict[str, Any], status: OrderStatus) -> None:
    requirements = order.get("operation_requirements") or operation_requirements(order.get("items") or [])
    order["operation_requirements"] = requirements
    if status == "art" and not order.get("art_started_at"):
        order["art_started_at"] = now_iso()
        order["art_due_date"] = business_day_due_date(requirements.get("art_lead_days") or 0)
    if status == "production" and not order.get("production_started_at"):
        order["production_started_at"] = now_iso()
        order["production_due_date"] = business_day_due_date(requirements.get("production_lead_days") or 0)
    if status == "ready_delivery" and not order.get("ready_for_delivery_at"):
        order["ready_for_delivery_at"] = now_iso()


def calculate_cart(cart: dict[str, Any]) -> dict[str, Any]:
    calculate_totals(cart)
    subtotal, discount, freight, total = (cart[key] for key in ("subtotal", "discount", "freight", "total"))
    cart.update(
        {
            "subtotal": subtotal,
            "discount": discount,
            "freight": freight,
            "total": total,
            "items_count": len(cart.get("items", [])),
            "operation_requirements": operation_requirements(cart.get("items", [])),
            "updated_at": now_iso(),
        }
    )
    return cart


def cart_summary_text(cart: dict[str, Any]) -> str:
    lines = [f"Orcamento {cart.get('client_name') or cart.get('client_phone') or ''}".strip()]
    for item in cart.get("items", []):
        variant = " / ".join([value for value in [item.get("size"), item.get("color")] if value])
        suffix = f" ({variant})" if variant else ""
        lines.append(f"- {item.get('quantity')}x {item.get('product_name')}{suffix}: R$ {float(item.get('total') or 0):.2f}")
    lines.append(f"Subtotal: R$ {float(cart.get('subtotal') or 0):.2f}")
    if float(cart.get("discount") or 0):
        lines.append(f"Desconto: R$ {float(cart.get('discount') or 0):.2f}")
    if float(cart.get("freight") or 0):
        lines.append(f"Frete: R$ {float(cart.get('freight') or 0):.2f}")
    lines.append(f"Total: R$ {float(cart.get('total') or 0):.2f}")
    return "\n".join(lines)


def get_cart_or_404(data: dict[str, Any], tenant_id: str, cart_id: str) -> dict[str, Any]:
    cart = tenant_bucket(data, "carts", tenant_id).get(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho nao encontrado.")
    return cart


def get_public_store_or_404(data: dict[str, Any], store_slug: str) -> dict[str, Any]:
    config = next(
        (item for item in data.get("configs", {}).values() if slugify(item.get("chronos_slug")) == slugify(store_slug)),
        None,
    )
    if not config:
        raise HTTPException(status_code=404, detail="Loja nao encontrada.")
    return config


def get_public_cart_or_404(data: dict[str, Any], store_slug: str, cart_id: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    config = get_public_store_or_404(data, store_slug)
    cart = get_cart_or_404(data, config["tenant_id"], cart_id)
    expected_token = str(cart.get("public_token") or "")
    if not expected_token or not token or not secrets.compare_digest(expected_token, token):
        raise HTTPException(status_code=404, detail="Carrinho nao encontrado.")
    return config, cart


def create_or_update_public_client(tenant_id: str, payload: PublicCheckoutPayload) -> dict[str, Any]:
    body = json.dumps(
        {
            "name": payload.client_name.strip(),
            "phone": payload.client_phone.strip(),
            "email": payload.email.strip() or None,
            "company_name": payload.company_name.strip() or None,
            "notes": payload.notes.strip() or None,
            "source": "loja_publica",
            "conversation_status": "novo",
            "order_status": "orcamento",
            "tags": ["Loja publica"],
        }
    ).encode("utf-8")
    request = Request(
        f"{NEXUS_API_URL}/nexus/clients?empresa_id={quote(tenant_id)}",
        data=body,
        method="POST",
        headers={**service_headers("loja", tenant_id), "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Nao foi possivel registrar o cliente no Nexus: {exc}") from exc
    client = result.get("client") or {}
    if not client.get("id"):
        raise HTTPException(status_code=503, detail="O Nexus nao retornou o cliente cadastrado.")
    return client


def get_quote_or_404(data: dict[str, Any], tenant_id: str, quote_id: str) -> dict[str, Any]:
    quote = tenant_bucket(data, "quotes", tenant_id).get(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Orcamento nao encontrado.")
    return quote


def company_profile_for_quote(tenant_id: str) -> dict[str, Any]:
    header = pdf_header_settings(tenant_id)
    try:
        request = Request(
            f"{CORE_API_URL}/core/tenants/{quote(tenant_id)}",
            headers=service_headers("loja", tenant_id),
        )
        with urlopen(request, timeout=5) as response:
            company = json.loads(response.read().decode("utf-8")).get("tenant") or {}
        logo_url = str(company.get("logo_url") or "")
        if logo_url.split("?", 1)[0] == f"/core/assets/{quote(tenant_id, safe='')}/logo.png":
            try:
                logo_request = Request(urljoin(f"{CORE_API_URL}/", logo_url.lstrip("/")), headers=service_headers("loja", tenant_id))
                with urlopen(logo_request, timeout=5) as response:
                    company["logo_bytes"] = response.read(2 * 1024 * 1024 + 1)
            except Exception:
                pass
        return {**company, "pdf_header_lines": header["lines"]}
    except Exception:
        return {"pdf_header_lines": header["lines"]}


def get_order_or_404(data: dict[str, Any], tenant_id: str, order_id: str) -> dict[str, Any]:
    order = tenant_bucket(data, "orders", tenant_id).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido nao encontrado.")
    return order


def customer_name_projection(records, tenant_id):
    """Resolve names for display without rewriting historic business snapshots."""
    if not records:
        return records
    mode = client_display_settings(tenant_id)["mode"]
    clients = {}
    if postgres_mode("nexus") == "primary" and any((record.get("cart_snapshot") or record).get("client_id") for record in records):
        clients = {client["id"]: client for client in run_postgres(pg_list_clients(tenant_id))}
    result = []
    for record in records:
        snapshot = record.get("cart_snapshot") or record
        identity = clients.get(snapshot.get("client_id")) or {
            "name": snapshot.get("client_person_name") or snapshot.get("client_name"),
            "company_name": snapshot.get("client_company_name"),
        }
        name = display_name(identity, mode) or snapshot.get("client_name") or ""
        projected = {**record, "client_name": name, "client_person_name": identity.get("name") or "", "client_company_name": identity.get("company_name") or ""}
        if record.get("cart_snapshot"):
            projected["cart_snapshot"] = {**record["cart_snapshot"], "client_name": name}
        result.append(projected)
    return result


@app.get("/health")
def health() -> dict[str, Any]:
    mode = postgres_mode("loja")
    return {"ok": True, "service": "Chronos Loja API", "storage_mode": mode, "storage": "PostgreSQL" if mode == "primary" else str(SHOP_DATA_PATH)}


_numbering_lock = RLock()


def local_order_config(data, tenant_id):
    config = data.setdefault("order_numbering", {}).setdefault(tenant_id, {"prefix": "", "last_number": 0})
    config["last_number"] = max(config["last_number"], max((int(order.get("order_number", 0)) for order in tenant_bucket(data, "orders", tenant_id).values()), default=0))
    return config


@app.get("/shop/order-numbering")
def get_order_numbering(tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    if postgres_mode("loja") == "primary":
        return run_postgres(configure_order_numbering(tenant_id))
    with _numbering_lock:
        return local_order_config(load_data(), tenant_id)


@app.put("/shop/order-numbering")
def put_order_numbering(payload: OrderNumberingPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    updates = payload.model_dump()
    if postgres_mode("loja") == "primary":
        return run_postgres(configure_order_numbering(tenant_id, updates))
    with _numbering_lock:
        data = load_data()
        config = local_order_config(data, tenant_id)
        updates = checked_config(payload.prefix, payload.last_number, config["last_number"])
        data["order_numbering"][tenant_id] = updates
        save_data(data)
        return updates


_product_extras_lock = RLock()


def saved_product_extras(tenant_id, product_id=None, extra=None):
    if postgres_mode("loja") == "primary":
        return run_postgres(pg_product_extras(tenant_id, product_id, extra))
    with _product_extras_lock:
        path = DATA_DIR / "product_extras.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        catalog = data.setdefault(tenant_id, {})
        if extra is None:
            return catalog
        result = append_extra(catalog.setdefault(product_id, []), extra)
        atomic_write_json(path, data)
        return result


@app.post("/shop/products/{product_id}/variants")
def create_product_variant(product_id: str, payload: ProductVariantPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    tenant_id = scoped_tenant(tenant_id, "loja")
    products = list_shop_products(tenant_id)
    selected = next((item for item in products if item["id"] == product_id), None)
    if not selected:
        raise HTTPException(404, "Produto não encontrado.")
    base_id = (selected.get("promotion") or {}).get("product_id", product_id)
    product = next((item for item in products if item["id"] == base_id), None)
    if not product:
        raise HTTPException(404, "Produto original não encontrado.")
    values = payload.model_dump()
    values["sale_price"] = round(values["sale_price"], 4)
    values["unit"] = values["unit"].strip().upper()
    values["finishes"] = list(dict.fromkeys(value.strip() for value in values["finishes"] if value.strip()))
    for tier in values["quantity_prices"]:
        tier["unit_price"] = round(tier["unit_price"], 4)
    minima = [tier["minimum_quantity"] for tier in values["quantity_prices"]]
    if not values["unit"] or len(minima) != len(set(minima)) or any(tier["unit_price"] <= 0 for tier in values["quantity_prices"]) or (values["sale_price"] <= 0 and not minima):
        raise HTTPException(422, "Informe um preço de venda positivo ou faixas válidas, sem quantidades repetidas.")
    if postgres_mode("loja") != "primary" or postgres_mode("stock") != "primary":
        raise HTTPException(503, "O cadastro integrado de variações requer Stock e Loja no PostgreSQL.")
    stock_id = run_postgres(pg_create_variant(tenant_id, product, values))
    refreshed = next(item for item in list_shop_products(tenant_id) if item["id"] == base_id)
    return {"ok": True, "product": refreshed, "stock_item_id": stock_id}


@app.post("/shop/products/{product_id}/extras")
def create_product_extra(product_id: str, payload: ProductExtraPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    product = next((item for item in list_shop_products(tenant_id) if item["id"] == product_id), None)
    if not product:
        raise HTTPException(404, "Produto não encontrado.")
    if not any(str(variant["stock_item_id"]) == payload.stock_item_id for variant in product.get("variants", [])):
        raise HTTPException(404, "Variação não encontrada nesta família.")
    description = payload.description.strip()
    price = round(payload.unit_price, 4)
    if not description or price <= 0:
        raise HTTPException(422, "Informe a descrição e um valor maior que zero.")
    extra = {"id": "custom-" + uuid4().hex, "description": description, "group": "custom", "stock_item_id": "" if payload.apply_to_family else payload.stock_item_id, "quantity_prices": [{"minimum_quantity": 0.001, "unit_price": price}]}
    return {"ok": True, "extra": saved_product_extras(tenant_id, (product.get("promotion") or {}).get("product_id", product_id), extra)}


@app.post("/shop/promotions")
def create_promotion(payload: PromotionPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    product, variant = find_product_variant(tenant_id, payload.product_id, payload.stock_item_id)
    if product.get("promotion"):
        raise HTTPException(422, "Crie a promoção a partir do produto original.")
    values = payload.model_dump()
    values.update(name=payload.name.strip(), package_price=sale_money(payload.package_price))
    if not values["name"] or values["package_price"] <= 0:
        raise HTTPException(422, "Informe o nome e um valor de pelo menos R$ 0,01.")
    promotion = promotions.store(tenant_id, values)
    return {"ok": True, "product": promotions.products([product], {promotion["id"]: promotion})[0]}


@app.post("/shop/promotions/{promotion_id}/renew")
def renew_promotion(promotion_id: str, payload: PromotionRenewPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    value = sale_money(payload.package_price)
    if value <= 0:
        raise HTTPException(422, "Informe um valor de pelo menos R$ 0,01.")
    promotion = promotions.store(tenant_id, {"package_price": value}, promotion_id)
    product = next((p for p in list_shop_products(tenant_id) if p["id"] == promotion["id"]), None)
    return {"ok": True, "product": product}


@app.get("/shop/quote-validity")
def get_quote_validity(tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    return quote_validity_settings(tenant_id)


@app.put("/shop/quote-validity")
def put_quote_validity(payload: QuoteValidityPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    return quote_validity_settings(tenant_id, payload.model_dump())


def quote_validity_fields(tenant_id, cart):
    config = quote_validity_settings(tenant_id)
    deadline = (promotions.today() + timedelta(days=config["days"])).isoformat() if config["mode"] == "days" else "9999-12-31"
    deadline = promotions.validate_cart(tenant_id, cart, deadline)
    return {"validity_mode": config["mode"], "validity_text": config["text"] if config["mode"] == "text" else "", "valid_until": "" if deadline == "9999-12-31" else deadline}


@app.get("/shop/config")
def get_config(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    configs = data.setdefault("configs", {})
    config = configs.get(tenant_id)
    if not config:
        config = default_config(tenant_id)
        configs[tenant_id] = config
        save_data(data)
    return {"ok": True, "config": config}


@app.put("/shop/config")
def save_config(payload: ShopConfigPayload) -> dict[str, Any]:
    data = load_data()
    configs = data.setdefault("configs", {})
    next_config = configs.get(payload.tenant_id) or default_config(payload.tenant_id)
    updates = payload.model_dump()
    if updates.get("chronos_slug"):
        slug = slugify(updates["chronos_slug"])
        for tenant_id, config in configs.items():
            if tenant_id != payload.tenant_id and slugify(config.get("chronos_slug")) == slug:
                raise HTTPException(status_code=409, detail="Este slug ja esta em uso por outra loja.")
        updates["chronos_slug"] = slug
    next_config.update(updates)
    next_config["updated_at"] = now_iso()
    configs[payload.tenant_id] = next_config
    save_data(data)
    return {"ok": True, "config": next_config}


@app.get("/shop/products")
def get_products(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    return {"ok": True, "products": list_shop_products(tenant_id)}


@app.patch("/shop/products/{product_id}")
def update_product(product_id: str, payload: ShopProductUpdatePayload) -> dict[str, Any]:
    if product_id.startswith("promotion-"):
        raise HTTPException(409, "Use a opção de editar ou renovar a promoção.")
    data = load_data()
    products = data.setdefault("products", {}).setdefault(payload.tenant_id, {})
    families = group_stock_families(payload.tenant_id)
    resolve_family_ids(families, products)
    selected = next((p for p in families if p["id"] == product_id), None)
    if selected is None:
        raise HTTPException(404, "Produto não encontrado no Estoque.")
    current = products.get(product_id, {"id": product_id, "tenant_id": payload.tenant_id, "created_at": now_iso()})
    current["stock_family"] = [selected["category"], selected["family"]]
    updates = payload.model_dump(exclude_unset=True)
    updates.pop("tenant_id", None)
    current.update(updates)
    if "variant_prices" in updates:
        current["pricing_edited_at"] = now_iso()
    current["updated_at"] = now_iso()
    products[product_id] = current
    product = next(item for item in configured_products(payload.tenant_id, families, products) if item["id"] == product_id)
    save_data(data)
    return {"ok": True, "product": product}


@app.post("/shop/products/import-from-stock")
def import_from_stock(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    products = group_stock_families(tenant_id)
    data = load_data()
    bucket = data.setdefault("products", {}).setdefault(tenant_id, {})
    resolve_family_ids(products, bucket)
    imported = 0
    for product in products:
        variant_prices = {
            str(variant.get("stock_item_id")): {
                "sale_price": float(variant.get("sale_price") or 0),
                "promotional_price": float(variant.get("promotional_price") or 0),
                "quantity_prices": normalize_quantity_prices(variant.get("quantity_prices")),
                "sellable": bool(variant.get("sellable", True)),
            }
            for variant in product.get("variants", [])
            if variant.get("stock_item_id")
        }
        if product["id"] not in bucket:
            bucket[product["id"]] = {
                "id": product["id"],
                "tenant_id": tenant_id,
                "published": False,
                "public_name": product["family"],
                "public_description": product.get("public_description") or "",
                "public_category": product.get("category") or "",
                "highlight": False,
                "order": 0,
                "image_url": "",
                "visible_stock": True,
                "variant_prices": variant_prices,
                "pricing_initialized_at": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            imported += 1
        else:
            should_initialize_pricing = not bucket[product["id"]].get("pricing_initialized_at")
            can_migrate_legacy_price = not bucket[product["id"]].get("pricing_edited_at")
            saved_variant_prices = bucket[product["id"]].setdefault("variant_prices", {})
            for stock_item_id, price_config in variant_prices.items():
                if should_initialize_pricing:
                    saved_variant_prices[stock_item_id] = price_config
                else:
                    current_price = saved_variant_prices.setdefault(stock_item_id, price_config)
                    if can_migrate_legacy_price and not float(current_price.get("sale_price") or 0) and float(price_config.get("sale_price") or 0):
                        current_price["sale_price"] = price_config["sale_price"]
                    if can_migrate_legacy_price and not float(current_price.get("promotional_price") or 0) and float(price_config.get("promotional_price") or 0):
                        current_price["promotional_price"] = price_config["promotional_price"]
            bucket[product["id"]]["pricing_initialized_at"] = bucket[product["id"]].get("pricing_initialized_at") or now_iso()
        bucket[product["id"]]["stock_family"] = [product["category"], product["family"]]
    catalog = configured_products(tenant_id, products, bucket)
    save_data(data)
    return {"ok": True, "imported": imported, "products": catalog}


@app.get("/public/{store_slug}/catalog")
def public_catalog(store_slug: str) -> dict[str, Any]:
    data = load_data()
    config = get_public_store_or_404(data, store_slug)
    products = []
    for product in list_shop_products(config["tenant_id"]):
        if not product.get("published") or (product.get("promotion") and promotions.expired(product["promotion"])):
            continue
        public_product = {k: product[k] for k in (
            "id", "category", "family", "public_name", "public_description", "public_category",
            "highlight", "visible_stock", "order", "promotion",
        ) if k in product}
        variant_fields = ("stock_item_id", "sku", "size", "color", "finishes", "unit", "sale_price",
                          "promotional_price", "quantity_prices", "sellable", "promotion",
                          "art_lead_days", "production_lead_days")
        if product.get("visible_stock", True):
            variant_fields += ("quantity", "available")
        public_product["variants"] = [
            {k: variant[k] for k in variant_fields if k in variant}
            for variant in product.get("variants", []) if variant.get("sellable", True)
        ]
        public_product["image_url"] = public_image_url(product.get("image_url", ""), config["tenant_id"])
        products.append(public_product)
    return {"ok": True, "store": config, "products": products}


@app.get("/public/{store_slug}/product/{product_id}")
def public_product_detail(store_slug: str, product_id: str) -> dict[str, Any]:
    catalog = public_catalog(store_slug)
    product = next((item for item in catalog["products"] if item["id"] == product_id), None)
    if product is None:
        raise HTTPException(404, "Produto nao encontrado")
    return {"ok": True, "product": product}


@app.post("/public/{store_slug}/carts")
def create_public_cart(store_slug: str) -> dict[str, Any]:
    data = load_data()
    config = get_public_store_or_404(data, store_slug)
    tenant_id = config["tenant_id"]
    cart_id = f"cart-{uuid4().hex[:10]}"
    cart = {
        "id": cart_id,
        "tenant_id": tenant_id,
        "client_id": "",
        "client_name": "",
        "client_phone": "",
        "source": "public_store",
        "public_token": secrets.token_urlsafe(24),
        "status": "open",
        "items": [],
        "subtotal": 0,
        "discount": 0,
        "freight": 0,
        "total": 0,
        "notes": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tenant_bucket(data, "carts", tenant_id)[cart_id] = cart
    save_data(data)
    return {"ok": True, "cart": cart, "token": cart["public_token"]}


@app.get("/public/{store_slug}/carts/{cart_id}")
def get_public_cart(store_slug: str, cart_id: str, token: str = Query(..., min_length=12)) -> dict[str, Any]:
    data = load_data()
    _, cart = get_public_cart_or_404(data, store_slug, cart_id, token)
    return {"ok": True, "cart": calculate_cart(cart)}


@app.post("/public/{store_slug}/carts/{cart_id}/items")
def add_public_cart_item(store_slug: str, cart_id: str, payload: PublicCartItemPayload) -> dict[str, Any]:
    data = load_data()
    config, cart = get_public_cart_or_404(data, store_slug, cart_id, payload.token)
    if cart.get("status") != "open":
        raise HTTPException(status_code=409, detail="Este carrinho ja foi enviado para atendimento.")
    return add_cart_item(
        cart_id,
        CartItemPayload(
            tenant_id=config["tenant_id"], product_id=payload.product_id, stock_item_id=payload.stock_item_id,
            quantity=payload.quantity, notes=payload.notes,
        ),
    )


@app.patch("/public/{store_slug}/carts/{cart_id}/items/{item_id}")
def update_public_cart_item(store_slug: str, cart_id: str, item_id: str, payload: PublicCartItemPayload) -> dict[str, Any]:
    data = load_data()
    config, cart = get_public_cart_or_404(data, store_slug, cart_id, payload.token)
    if cart.get("status") != "open":
        raise HTTPException(status_code=409, detail="Este carrinho ja foi enviado para atendimento.")
    return update_cart_item(
        cart_id,
        item_id,
        CartItemPayload(
            tenant_id=config["tenant_id"], product_id=payload.product_id, stock_item_id=payload.stock_item_id,
            quantity=payload.quantity, notes=payload.notes,
        ),
    )


@app.delete("/public/{store_slug}/carts/{cart_id}/items/{item_id}")
def delete_public_cart_item(store_slug: str, cart_id: str, item_id: str, token: str = Query(..., min_length=12)) -> dict[str, Any]:
    data = load_data()
    config, cart = get_public_cart_or_404(data, store_slug, cart_id, token)
    if cart.get("status") != "open":
        raise HTTPException(status_code=409, detail="Este carrinho ja foi enviado para atendimento.")
    return delete_cart_item(cart_id, item_id, tenant_id=config["tenant_id"])


@app.post("/public/{store_slug}/checkout")
def checkout_public_cart(store_slug: str, payload: PublicCheckoutPayload) -> dict[str, Any]:
    data = load_data()
    config, cart = get_public_cart_or_404(data, store_slug, payload.cart_id, payload.token)
    if not cart.get("items"):
        raise HTTPException(status_code=409, detail="Adicione ao menos um item antes de solicitar o orcamento.")
    existing_quote_id = str(cart.get("public_quote_id") or "")
    if existing_quote_id:
        existing_quote = tenant_bucket(data, "quotes", config["tenant_id"]).get(existing_quote_id)
        if existing_quote:
            return {"ok": True, "quote": existing_quote, "existing": True}

    client = create_or_update_public_client(config["tenant_id"], payload)
    cart.update(
        {
            "client_id": client["id"],
            "client_name": display_name(client, client_display_settings(config["tenant_id"])["mode"]) if client.get("company_name") else (client.get("name") or payload.client_name.strip()),
            "client_person_name": client.get("name") or payload.client_name.strip(),
            "client_company_name": client.get("company_name") or payload.company_name.strip(),
            "client_phone": client.get("phone") or payload.client_phone.strip(),
            "notes": payload.notes.strip(),
        }
    )
    calculate_cart(cart)
    quote_id = f"quote-{uuid4().hex[:10]}"
    quote = {
        "id": quote_id,
        "tenant_id": config["tenant_id"],
        "cart_id": cart["id"],
        "status": "sent",
        **quote_validity_fields(cart["tenant_id"], cart),
        "cart_snapshot": json.loads(json.dumps(cart)),
        "message": cart_summary_text(cart),
        "source": "public_store",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tenant_bucket(data, "quotes", config["tenant_id"])[quote_id] = quote
    cart["status"] = "quoted"
    cart["public_quote_id"] = quote_id
    save_data(data)
    return {"ok": True, "quote": quote, "client": client}


@app.get("/shop/carts")
def list_carts(tenant_id: str = Query(default=DEFAULT_TENANT_ID), client_id: str = "") -> dict[str, Any]:
    data = load_data()
    carts = list(tenant_bucket(data, "carts", tenant_id).values())
    if client_id:
        carts = [cart for cart in carts if cart.get("client_id") == client_id]
    carts.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"ok": True, "carts": carts}


def seller_fields(source: dict[str, Any] | None = None, *, capture: bool = False) -> dict[str, str]:
    source = source or {}
    if source.get("seller_name"):
        return {key: str(source.get(key) or "") for key in ("seller_member_id", "seller_user_id", "seller_name")}
    user = current_user.get()
    if capture and user and user.kind == "member":
        return {"seller_member_id": user.member_id, "seller_user_id": user.user_id, "seller_name": user.user_name}
    return {}


@app.post("/shop/carts")
def create_cart(payload: CartCreatePayload) -> dict[str, Any]:
    data = load_data()
    carts = tenant_bucket(data, "carts", payload.tenant_id)
    cart_id = f"cart-{uuid4().hex[:10]}"
    cart = {
        "id": cart_id,
        **payload.model_dump(),
        "client_person_name": payload.client_name,
        "client_name": display_name({"name": payload.client_name, "company_name": payload.client_company_name}, client_display_settings(payload.tenant_id)["mode"]) if payload.client_company_name.strip() else payload.client_name,
        **seller_fields(capture=True),
        "status": "open",
        "items": [],
        "subtotal": 0,
        "discount": 0,
        "freight": 0,
        "total": 0,
        "notes": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    carts[cart_id] = cart
    save_data(data)
    return {"ok": True, "cart": cart}


@app.get("/shop/carts/{cart_id}")
def get_cart(cart_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    return {"ok": True, "cart": calculate_cart(get_cart_or_404(data, tenant_id, cart_id))}


def selected_finishes(variant: dict[str, Any], requested: list[str] | None) -> list[str]:
    choices = list(dict.fromkeys(requested or []))
    available = variant.get("finishes") or []
    if any(choice not in available for choice in choices):
        raise HTTPException(422, "Acabamento não disponível para esta variação. Atualize o produto.")
    return choices


def registered_extras(variant: dict[str, Any], ids: list[str], quantity: float) -> list[dict[str, Any]]:
    available = {option["id"]: option for option in variant.get("registered_extras") or []}
    result = []
    selected_colors = 0
    for key in dict.fromkeys(ids):
        option = available.get(key)
        if not option or option.get("on_request") or not option.get("quantity_prices"):
            raise HTTPException(422, "Adicional indisponível ou sob consulta. Atualize o catálogo.")
        selected_colors += option.get("group") == "color"
        if selected_colors > 1:
            raise HTTPException(422, "Selecione apenas uma opção de cores.")
        resolved = resolve_variant_price({"quantity_prices": option["quantity_prices"]}, quantity)
        result.append({"id": key, "description": option["description"], "unit_price": resolved["unit_price"], "minimum_quantity": resolved["minimum_quantity"]})
    return result


def selected_extras(extras: list[CartItemExtra] | None) -> list[dict[str, Any]]:
    result = []
    for extra in extras or []:
        description = extra.description.strip()
        if not description:
            raise HTTPException(422, "Informe a descrição do adicional.")
        result.append({"description": description, "unit_price": round(extra.unit_price, 4)})
    return result


@app.post("/shop/carts/{cart_id}/items")
def add_cart_item(cart_id: str, payload: CartItemPayload) -> dict[str, Any]:
    data = load_data()
    cart = get_cart_or_404(data, payload.tenant_id, cart_id)
    if cart.get("status") != "open":
        raise HTTPException(409, "Este carrinho já foi finalizado.")
    product, variant = find_product_variant(payload.tenant_id, payload.product_id, payload.stock_item_id)
    price_resolution = resolve_variant_price(variant, payload.quantity)
    unit_price = price_resolution["unit_price"]
    if unit_price <= 0:
        raise HTTPException(status_code=409, detail="Variacao sem preco de venda configurado.")
    extras = registered_extras(variant, payload.extra_ids, payload.quantity) if payload.extra_ids is not None else selected_extras(payload.extras)
    base_unit_price = unit_price
    unit_price = round(base_unit_price + sum(extra["unit_price"] for extra in extras), 10 if variant.get("promotion") or price_resolution.get("exact_lot_pricing") else 4)
    item_id = f"item-{uuid4().hex[:8]}"
    cart_item = {
        "id": item_id,
        "product_id": product["id"],
        "stock_item_id": str(variant.get("stock_item_id")),
        "product_name": product.get("public_name") or product.get("family"),
        "sku": variant.get("sku") or "",
        "size": variant.get("size") or "",
        "color": variant.get("color") or "",
        "unit": variant.get("unit") or "UN",
        "quantity": payload.quantity,
        "unit_price": unit_price,
        "base_unit_price": base_unit_price,
        "promotion": variant.get("promotion"),
        "extras": extras,
        "total": round(payload.quantity * unit_price, 2),
        "price_source": price_resolution["price_source"],
        "price_minimum_quantity": price_resolution["minimum_quantity"],
        "art_lead_days": int(variant.get("art_lead_days") or 0),
        "production_lead_days": int(variant.get("production_lead_days") or 0),
        "notes": payload.notes,
        "finishes": selected_finishes(variant, payload.finishes),
        "created_at": now_iso(),
    }
    cart.setdefault("items", []).append(cart_item)
    calculate_cart(cart)
    save_data(data)
    return {"ok": True, "cart": cart, "item": cart_item}


@app.patch("/shop/carts/{cart_id}/items/{item_id}")
def update_cart_item(cart_id: str, item_id: str, payload: CartItemPayload) -> dict[str, Any]:
    data = load_data()
    cart = get_cart_or_404(data, payload.tenant_id, cart_id)
    if cart.get("status") != "open":
        raise HTTPException(409, "Este carrinho já foi finalizado.")
    cart_item = next((item for item in cart.get("items", []) if item.get("id") == item_id), None)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Item do carrinho nao encontrado.")
    product, variant = find_product_variant(payload.tenant_id, payload.product_id, payload.stock_item_id)
    price_resolution = resolve_variant_price(variant, payload.quantity)
    unit_price = price_resolution["unit_price"]
    finishes = selected_finishes(variant, payload.finishes) if payload.finishes is not None else (cart_item.get("finishes") or [])
    if payload.extra_ids is not None:
        extras = registered_extras(variant, payload.extra_ids, payload.quantity)
    elif payload.extras is not None:
        extras = selected_extras(payload.extras)
    else:
        previous_extras = cart_item.get("extras") or []
        extras = [extra for extra in previous_extras if not extra.get("id")] + registered_extras(variant, [extra["id"] for extra in previous_extras if extra.get("id")], payload.quantity)
    base_unit_price = unit_price
    unit_price = round(base_unit_price + sum(extra["unit_price"] for extra in extras), 10 if variant.get("promotion") or price_resolution.get("exact_lot_pricing") else 4)
    cart_item.update(
        {
            "product_id": product["id"],
            "stock_item_id": str(variant.get("stock_item_id")),
            "product_name": product.get("public_name") or product.get("family"),
            "sku": variant.get("sku") or "",
            "size": variant.get("size") or "",
            "color": variant.get("color") or "",
            "finishes": finishes,
            "quantity": payload.quantity,
            "unit_price": unit_price,
            "base_unit_price": base_unit_price,
        "promotion": variant.get("promotion"),
            "extras": extras,
            "total": round(payload.quantity * unit_price, 2),
            "price_source": price_resolution["price_source"],
            "price_minimum_quantity": price_resolution["minimum_quantity"],
            "art_lead_days": int(variant.get("art_lead_days") or 0),
            "production_lead_days": int(variant.get("production_lead_days") or 0),
            "notes": payload.notes,
        }
    )
    calculate_cart(cart)
    save_data(data)
    return {"ok": True, "cart": cart, "item": cart_item}


@app.delete("/shop/carts/{cart_id}/items/{item_id}")
def delete_cart_item(cart_id: str, item_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    cart = get_cart_or_404(data, tenant_id, cart_id)
    if cart.get("status") != "open":
        raise HTTPException(409, "Este carrinho já foi finalizado.")
    before = len(cart.get("items", []))
    cart["items"] = [item for item in cart.get("items", []) if item.get("id") != item_id]
    if len(cart["items"]) == before:
        raise HTTPException(status_code=404, detail="Item do carrinho nao encontrado.")
    calculate_cart(cart)
    save_data(data)
    return {"ok": True, "cart": cart}


@app.patch("/shop/carts/{cart_id}/totals")
def update_cart_totals(cart_id: str, payload: CartTotalsPayload) -> dict[str, Any]:
    data = load_data()
    cart = get_cart_or_404(data, payload.tenant_id, cart_id)
    if cart.get("status") != "open":
        raise HTTPException(409, "Este carrinho já foi finalizado.")
    calculate_cart(cart)
    reduction = payload.discount if payload.discount_value is None else payload.discount_value
    discount_amount(cart["subtotal"], payload.discount_type, reduction, strict=True)
    cart["discount_type"] = payload.discount_type
    cart["discount_value"] = reduction
    cart["discount"] = payload.discount
    cart["freight"] = payload.freight
    cart["notes"] = payload.notes
    calculate_cart(cart)
    save_data(data)
    return {"ok": True, "cart": cart}


@app.patch("/shop/carts/{cart_id}/items/{item_id}/discount")
def update_item_discount(cart_id: str, item_id: str, payload: ItemDiscountPayload) -> dict[str, Any]:
    data = load_data()
    cart = get_cart_or_404(data, payload.tenant_id, cart_id)
    if cart.get("status") != "open":
        raise HTTPException(409, "Este carrinho já foi finalizado.")
    calculate_cart(cart)
    item = next((item for item in cart["items"] if item["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Item não encontrado.")
    discount_amount(item["gross_total"], payload.discount_type, payload.discount_value, strict=True)
    item.update(discount_type=payload.discount_type, discount_value=payload.discount_value)
    calculate_cart(cart)
    save_data(data)
    return {"ok": True, "cart": cart}


@app.post("/shop/quotes")
def create_quote(payload: QuoteCreatePayload) -> dict[str, Any]:
    data = load_data()
    cart = calculate_cart(get_cart_or_404(data, payload.tenant_id, payload.cart_id))
    existing = next((quote for quote in tenant_bucket(data, "quotes", payload.tenant_id).values() if quote.get("cart_id") == payload.cart_id), None)
    if existing:
        return {"ok": True, "quote": existing}
    if cart.get("status") != "open":
        raise HTTPException(status_code=409, detail="Este carrinho já foi finalizado.")
    if not cart.get("items"):
        raise HTTPException(status_code=409, detail="Carrinho vazio.")
    if cart.get("client_id") and postgres_mode("nexus") == "primary":
        client = run_postgres(pg_get_client(payload.tenant_id, cart["client_id"]))
        if client:
            cart["client_person_name"] = client.get("name") or ""
            cart["client_company_name"] = client.get("company_name") or ""
            cart["client_name"] = display_name(client, client_display_settings(payload.tenant_id)["mode"])
    elif cart.get("client_company_name"):
        cart["client_name"] = display_name({"name": cart.get("client_person_name") or cart.get("client_name"), "company_name": cart["client_company_name"]}, client_display_settings(payload.tenant_id)["mode"])
    cart.update(seller_fields(cart, capture=True))
    quote_id = f"quote-{uuid4().hex[:10]}"
    quote = {
        "id": quote_id,
        "tenant_id": payload.tenant_id,
        "cart_id": payload.cart_id,
        "status": "draft",
        **quote_validity_fields(cart["tenant_id"], cart),
        "cart_snapshot": json.loads(json.dumps(cart)),
        "message": cart_summary_text(cart),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    tenant_bucket(data, "quotes", payload.tenant_id)[quote_id] = quote
    cart["status"] = "quoted"
    save_data(data)
    return {"ok": True, "quote": quote}


@app.get("/shop/quotes")
def list_quotes(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    quotes = list(tenant_bucket(data, "quotes", tenant_id).values())
    quotes.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"ok": True, "quotes": customer_name_projection(quotes, tenant_id)}


@app.delete("/shop/quotes/{quote_id}")
def delete_quote(quote_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    if postgres_mode("loja") == "primary":
        run_postgres(delete_quote_postgres(tenant_id, quote_id))
    else:
        data = load_data()
        quote = get_quote_or_404(data, tenant_id, quote_id)
        if quote.get("status") == "approved" or any(order.get("quote_id") == quote_id for order in tenant_bucket(data, "orders", tenant_id).values()):
            raise HTTPException(409, "Este orçamento já foi aprovado ou virou um pedido e não pode ser apagado.")
        del tenant_bucket(data, "quotes", tenant_id)[quote_id]
        save_data(data)
    return {"ok": True}


@app.get("/shop/quotes/{quote_id}/pdf")
def download_quote_pdf(quote_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> Response:
    data = load_data()
    quote_data = get_quote_or_404(data, tenant_id, quote_id)
    store = data.get("configs", {}).get(tenant_id) or default_config(tenant_id)
    quote_data = customer_name_projection([quote_data], tenant_id)[0]
    pdf = build_quote_pdf(quote_data, store, company_profile_for_quote(tenant_id))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="orcamento-{quote_id}.pdf"'},
    )


@app.patch("/shop/quotes/{quote_id}/status")
def update_quote_status(quote_id: str, payload: QuoteStatusPayload) -> dict[str, Any]:
    data = load_data()
    quote = get_quote_or_404(data, payload.tenant_id, quote_id)
    quote["status"] = payload.status
    quote["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "quote": quote}


@app.post("/shop/orders")
def create_order(payload: OrderCreatePayload) -> dict[str, Any]:
    with _numbering_lock:
        return _create_order(payload)


def _create_order(payload: OrderCreatePayload) -> dict[str, Any]:
    if not payload.quote_id and not payload.cart_id:
        raise HTTPException(status_code=400, detail="Informe carrinho ou orcamento.")
    data = load_data()
    source_quote = get_quote_or_404(data, payload.tenant_id, payload.quote_id) if payload.quote_id else None
    if source_quote:
        if source_quote.get("status") in {"refused", "expired"}:
            raise HTTPException(status_code=409, detail="Esse orcamento nao pode gerar pedido.")
        try:
            if (source_quote.get("valid_until") or source_quote.get("validity_mode") != "text") and date.fromisoformat(str(source_quote.get("valid_until") or "")) < promotions.today():
                source_quote["status"] = "expired"
                source_quote["updated_at"] = now_iso()
                save_data(data)
                raise HTTPException(status_code=409, detail="Esse orcamento venceu e nao pode gerar pedido.")
        except ValueError:
            raise HTTPException(status_code=409, detail="O orcamento esta sem uma validade valida.") from None
        existing_order = next(
            (item for item in tenant_bucket(data, "orders", payload.tenant_id).values() if item.get("quote_id") == source_quote["id"]),
            None,
        )
        if existing_order:
            return {"ok": True, "order": existing_order, "existing": True}
    cart = source_quote.get("cart_snapshot") if source_quote else calculate_cart(get_cart_or_404(data, payload.tenant_id, payload.cart_id or ""))
    if not cart.get("items"):
        raise HTTPException(status_code=409, detail="Nao e possivel criar pedido sem itens.")
    if source_quote is None:
        promotions.validate_cart(payload.tenant_id, cart)
    order_id = f"order-{uuid4().hex[:10]}"
    order = {
        "id": order_id,
        "tenant_id": payload.tenant_id,
        "quote_id": payload.quote_id or "",
        **seller_fields(cart, capture=source_quote is None),
        "cart_id": cart.get("id") or payload.cart_id or "",
        "status": "new",
        "payment_status": "pending",
        "client_id": cart.get("client_id") or "",
        "client_name": cart.get("client_name") or "",
        "client_phone": cart.get("client_phone") or "",
        "items": cart.get("items") or [],
        "operation_requirements": cart.get("operation_requirements") or operation_requirements(cart.get("items") or []),
        "subtotal": cart.get("subtotal") or 0,
        "gross_subtotal": cart.get("gross_subtotal", cart.get("subtotal", 0)),
        "item_discount_total": cart.get("item_discount_total", 0),
        "discount_type": cart.get("discount_type", "amount"),
        "discount_value": cart.get("discount_value", cart.get("discount", 0)),
        "discount": cart.get("discount") or 0,
        "freight": cart.get("freight") or 0,
        "total": cart.get("total") or 0,
        "paid_total": 0,
        "refunded_total": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    if postgres_mode("loja") != "primary":
        config = local_order_config(data, payload.tenant_id)
        config["last_number"] += 1
        order.update(order_number=config["last_number"], order_prefix=config["prefix"])
    tenant_bucket(data, "orders", payload.tenant_id)[order_id] = order
    if source_quote:
        source_quote["status"] = "approved"
        source_quote["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "order": order}


@app.get("/shop/orders")
def list_orders(tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    data = load_data()
    orders = list(tenant_bucket(data, "orders", tenant_id).values())
    orders.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"ok": True, "orders": customer_name_projection(orders, tenant_id)}


@app.get("/shop/orders/{order_id}/payment-pdf")
def download_order_payment_pdf(order_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> Response:
    if postgres_mode("loja") == "primary":
        order, store, transactions, refunds = run_postgres(load_order_payment_document(tenant_id, order_id))
    else:
        data = load_data()
        order = get_order_or_404(data, tenant_id, order_id)
        store = data.get("configs", {}).get(tenant_id) or default_config(tenant_id)
        transactions = list(tenant_bucket(data, "transactions", tenant_id).values())
        refunds = list(tenant_bucket(data, "refunds", tenant_id).values())
    order = customer_name_projection([order], tenant_id)[0]
    pdf = build_order_pdf(order, store, company_profile_for_quote(tenant_id), transactions, refunds)
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('comprovante-' + order_id + '.pdf', safe='')}", "Cache-Control": "no-store"})


@app.delete("/shop/orders/{order_id}")
def delete_order(order_id: str, tenant_id: str = Query(default=DEFAULT_TENANT_ID)) -> dict[str, Any]:
    if postgres_mode("loja") == "primary":
        run_postgres(delete_order_postgres(tenant_id, order_id))
    else:
        data = load_data()
        get_order_or_404(data, tenant_id, order_id)
        del tenant_bucket(data, "orders", tenant_id)[order_id]
        save_data(data)
    return {"ok": True}


@app.patch("/shop/orders/{order_id}/status")
def update_order_status(order_id: str, payload: OrderStatusPayload) -> dict[str, Any]:
    data = load_data()
    order = get_order_or_404(data, payload.tenant_id, order_id)
    if payload.status == "paid":
        order["paid_total"] = max(float(order.get("paid_total") or 0), float(order.get("total") or 0))
        order["payment_status"] = "paid"
        order["status"] = status_after_payment(order)
    else:
        order["status"] = payload.status
    apply_operational_timeline(order, order["status"])
    order["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "order": order}


_receipt_lock = RLock()


@app.post("/shop/orders/{order_id}/payments")
def confirm_manual_payment(order_id: str, payload: ManualReceiptPayload) -> dict[str, Any]:
    user = current_user.get()
    if not user:
        raise HTTPException(401, "Autenticação necessária.")
    if payload.paid_on > datetime.now(timezone.utc).date():
        raise HTTPException(422, "A data do recebimento não pode estar no futuro.")
    receipt_id = "manual-" + hashlib.sha256(f"{payload.tenant_id}:{order_id}:{payload.request_id}".encode()).hexdigest()[:40]
    receipt = {"id": receipt_id, "tenant_id": payload.tenant_id, "order_id": order_id, "amount": sale_money(payload.amount),
               "method": payload.method, "paid_on": payload.paid_on.isoformat(), "notes": payload.notes.strip(), "status": "paid",
               "recorded_by": user.user_id, "recorded_by_name": user.user_name, "created_at": now_iso(), "source": "chronos-facil"}
    def apply(order, existing):
        result = apply_receipt(order, receipt, existing)
        if not result.get("existing") and order["payment_status"] == "paid" and order.get("status") in {"new", "paid"}:
            order["status"] = status_after_payment(order)
            apply_operational_timeline(order, order["status"])
        return result
    if postgres_mode("loja") == "primary":
        return run_postgres(record_manual_receipt(payload.tenant_id, order_id, receipt_id, apply))
    with _receipt_lock:
        data = load_data()
        order = get_order_or_404(data, payload.tenant_id, order_id)
        ledger = tenant_bucket(data, "transactions", payload.tenant_id)
        result = apply(order, ledger.get(receipt_id))
        if not result.get("existing"):
            ledger[receipt_id] = result["transaction"]
            save_data(data)
        return result


@app.post("/shop/transactions")
def create_transaction(payload: TransactionPayload) -> dict[str, Any]:
    data = load_data()
    order = get_order_or_404(data, payload.tenant_id, payload.order_id)
    transaction_id = f"txn-{uuid4().hex[:10]}"
    transaction = {"id": transaction_id, **payload.model_dump(), "created_at": now_iso()}
    tenant_bucket(data, "transactions", payload.tenant_id)[transaction_id] = transaction
    if payload.status in {"paid", "partial"}:
        order["paid_total"] = round(float(order.get("paid_total") or 0) + payload.amount, 2)
    order["payment_status"] = "paid" if float(order.get("paid_total") or 0) >= float(order.get("total") or 0) else "partial"
    if order["payment_status"] == "paid":
        order["status"] = status_after_payment(order)
        apply_operational_timeline(order, order["status"])
    order["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "transaction": transaction, "order": order}


@app.get("/shop/transactions")
def list_transactions(tenant_id: str = Query(default=DEFAULT_TENANT_ID), order_id: str = "") -> dict[str, Any]:
    data = load_data()
    transactions = list(tenant_bucket(data, "transactions", tenant_id).values())
    if order_id:
        transactions = [transaction for transaction in transactions if transaction.get("order_id") == order_id]
    transactions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"ok": True, "transactions": transactions}


@app.post("/shop/refunds")
def create_refund(payload: RefundPayload) -> dict[str, Any]:
    data = load_data()
    order = get_order_or_404(data, payload.tenant_id, payload.order_id)
    refund_id = f"refund-{uuid4().hex[:10]}"
    refund = {"id": refund_id, **payload.model_dump(), "created_at": now_iso()}
    tenant_bucket(data, "refunds", payload.tenant_id)[refund_id] = refund
    order["refunded_total"] = round(float(order.get("refunded_total") or 0) + payload.amount, 2)
    if float(order.get("refunded_total") or 0) > 0:
        order["payment_status"] = "refunded"
    order["updated_at"] = now_iso()
    save_data(data)
    return {"ok": True, "refund": refund, "order": order}


@app.get("/shop/refunds")
def list_refunds(tenant_id: str = Query(default=DEFAULT_TENANT_ID), order_id: str = "") -> dict[str, Any]:
    data = load_data()
    refunds = list(tenant_bucket(data, "refunds", tenant_id).values())
    if order_id:
        refunds = [refund for refund in refunds if refund.get("order_id") == order_id]
    refunds.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"ok": True, "refunds": refunds}


@app.get("/shop/pdf-header")
def get_pdf_header(tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    return pdf_header_settings(scoped_tenant(tenant_id, "loja"))

@app.put("/shop/pdf-header")
def put_pdf_header(payload: PdfHeaderPayload, tenant_id: str = Query(default=DEFAULT_TENANT_ID)):
    return pdf_header_settings(scoped_tenant(tenant_id, "loja"), payload.model_dump())
