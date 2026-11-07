"""Leitura e snapshots do catálogo híbrido do Chronos.

O PostgreSQL é a fonte de verdade. O JSON produzido aqui é derivado, versionado
e próprio para consumo rápido da Hera, Loja e integrações de exportação.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .postgres import get_connection


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


async def build_catalog_snapshot(tenant_id: str) -> dict[str, Any]:
    """Monta um catálogo de leitura sem transformar JSON em fonte de verdade."""
    async with get_connection() as connection:
        categories = await connection.fetch(
            """
            SELECT id, name, slug, description, custom_columns
            FROM stock_categories
            WHERE tenant_id = $1
            ORDER BY name
            """,
            tenant_id,
        )
        definitions = await connection.fetch(
            """
            SELECT category_id, field_key, label, value_type, required, options, display_order, settings
            FROM stock_category_attribute_definitions
            WHERE tenant_id = $1
            ORDER BY category_id, display_order, label
            """,
            tenant_id,
        )
        items = await connection.fetch(
            """
            SELECT
                item.id, item.sku, item.name, item.display_name, item.description, item.kind, item.unit,
                item.quantity, item.min_quantity, item.cost_price, item.supplier, item.location,
                item.width, item.height, item.depth, item.weight_grams, item.art_lead_days, item.production_lead_days,
                item.attributes, item.status,
                category.id AS category_id, category.name AS category_name,
                family.id AS family_id, family.name AS family_name, family.attributes AS family_attributes
            FROM stock_items item
            LEFT JOIN stock_categories category ON category.tenant_id = item.tenant_id AND category.id = item.category_id
            LEFT JOIN stock_families family ON family.tenant_id = item.tenant_id AND family.id = item.family_id
            WHERE item.tenant_id = $1
            ORDER BY category.name NULLS LAST, family.name NULLS LAST, item.name
            """,
            tenant_id,
        )
        tiers = await connection.fetch(
            """
            SELECT stock_item_id, min_quantity, unit_price
            FROM stock_tier_prices
            WHERE tenant_id = $1
            ORDER BY stock_item_id, min_quantity
            """,
            tenant_id,
        )
        store_variants = await connection.fetch(
            """
            SELECT variant.stock_item_id, product.id AS shop_product_id, product.public_name,
                   product.published, product.highlight, product.image_url, product.presentation,
                   variant.sale_price, variant.promotional_price, variant.sellable, variant.presentation AS variant_presentation
            FROM shop_product_variants variant
            JOIN shop_products product ON product.tenant_id = variant.tenant_id AND product.id = variant.shop_product_id
            WHERE variant.tenant_id = $1
            ORDER BY variant.stock_item_id
            """,
            tenant_id,
        )

    fields_by_category: dict[str, list[dict[str, Any]]] = {}
    for row in definitions:
        fields_by_category.setdefault(str(row["category_id"]), []).append(json_safe(dict(row)))
    tiers_by_item: dict[str, list[dict[str, Any]]] = {}
    for row in tiers:
        tiers_by_item.setdefault(str(row["stock_item_id"]), []).append(json_safe(dict(row)))
    store_by_item = {str(row["stock_item_id"]): json_safe(dict(row)) for row in store_variants}

    catalog_items = []
    for row in items:
        item = json_safe(dict(row))
        item_id = str(item.pop("id"))
        item_name = item.pop("name")
        category_id = item.get("category_id") or ""
        catalog_items.append(
            {
                "id": item_id,
                "sku": item.pop("sku"),
                "name": item_name,
                "display_name": item.pop("display_name") or item_name,
                "description": item.pop("description") or "",
                "kind": item.pop("kind"),
                "status": item.pop("status"),
                "unit": item.pop("unit"),
                "inventory": {
                    "quantity": item.pop("quantity"),
                    "min_quantity": item.pop("min_quantity"),
                    "location": item.pop("location") or "",
                },
                "commercial": {
                    "cost_price": item.pop("cost_price"),
                    "tier_prices": tiers_by_item.get(item_id, []),
                    "store": store_by_item.get(item_id),
                },
                "operation": {
                    "art_lead_days": item.pop("art_lead_days"),
                    "production_lead_days": item.pop("production_lead_days"),
                },
                "shipping": {
                    "width": item.pop("width"),
                    "height": item.pop("height"),
                    "depth": item.pop("depth"),
                    "weight_grams": item.pop("weight_grams"),
                },
                "category": {"id": category_id or None, "name": item.pop("category_name") or ""},
                "family": {
                    "id": item.pop("family_id") or None,
                    "name": item.pop("family_name") or "",
                    "attributes": item.pop("family_attributes") or {},
                },
                "attributes": item.pop("attributes") or {},
                "supplier": item.pop("supplier") or "",
                "attribute_definitions": fields_by_category.get(category_id, []),
            }
        )

    return {
        "schema": "chronos.catalog.v1",
        "tenant_id": tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "categories": [json_safe(dict(row)) for row in categories],
        "items": catalog_items,
    }


async def refresh_catalog_snapshot(tenant_id: str) -> dict[str, Any]:
    """Gera uma nova versão somente quando o catálogo realmente mudou."""
    snapshot = await build_catalog_snapshot(tenant_id)
    # A geração não deve criar uma nova versão quando apenas o relógio mudou.
    content_for_checksum = {key: value for key, value in snapshot.items() if key != "generated_at"}
    canonical = json.dumps(content_for_checksum, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    async with get_connection() as connection:
        existing = await connection.fetchrow(
            """
            SELECT version, checksum, generated_at
            FROM catalog_snapshots
            WHERE tenant_id = $1 AND checksum = $2
            """,
            tenant_id,
            checksum,
        )
        if existing:
            return {"changed": False, "version": existing["version"], "checksum": checksum, "generated_at": existing["generated_at"]}
        row = await connection.fetchrow(
            """
            INSERT INTO catalog_snapshots (tenant_id, checksum, payload)
            VALUES ($1, $2, $3)
            RETURNING version, generated_at
            """,
            tenant_id,
            checksum,
            snapshot,
        )
    return {"changed": True, "version": row["version"], "checksum": checksum, "generated_at": row["generated_at"]}


async def current_catalog_snapshot(tenant_id: str) -> dict[str, Any] | None:
    async with get_connection() as connection:
        row = await connection.fetchrow(
            """
            SELECT version, checksum, payload, generated_at
            FROM catalog_snapshots
            WHERE tenant_id = $1
            ORDER BY version DESC
            LIMIT 1
            """,
            tenant_id,
        )
    return json_safe(dict(row)) if row else None
