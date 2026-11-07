"""PostgreSQL representation compatible with the current Stock API."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .postgres import get_connection


def number(value: Any) -> float:
    return float(value) if isinstance(value, Decimal) else float(value or 0)


async def load_stock_payload() -> dict[str, Any]:
    """Materialize the relational catalog in the legacy API payload shape."""
    async with get_connection() as connection:
        categories = await connection.fetch("SELECT category.*, tenant.slug AS tenant_slug FROM stock_categories category JOIN tenants tenant ON tenant.id=category.tenant_id ORDER BY tenant.slug, category.name")
        definitions = await connection.fetch("SELECT definition.*, tenant.slug AS tenant_slug FROM stock_category_attribute_definitions definition JOIN tenants tenant ON tenant.id=definition.tenant_id ORDER BY display_order")
        families = await connection.fetch("SELECT family.*, tenant.slug AS tenant_slug FROM stock_families family JOIN tenants tenant ON tenant.id=family.tenant_id ORDER BY name")
        items = await connection.fetch("""
            SELECT item.*, tenant.slug AS tenant_slug, category.name AS category_name, family.name AS family_name
            FROM stock_items item
            JOIN tenants tenant ON tenant.id=item.tenant_id
            LEFT JOIN stock_categories category ON category.tenant_id=item.tenant_id AND category.id=item.category_id
            LEFT JOIN stock_families family ON family.tenant_id=item.tenant_id AND family.id=item.family_id
            ORDER BY item.tenant_id, item.name
        """)
        suppliers = await connection.fetch("SELECT supplier.*, tenant.slug AS tenant_slug FROM stock_suppliers supplier JOIN tenants tenant ON tenant.id=supplier.tenant_id ORDER BY name")
        movements = await connection.fetch("SELECT movement.*, tenant.slug AS tenant_slug FROM stock_movements movement JOIN tenants tenant ON tenant.id=movement.tenant_id ORDER BY created_at")
        resources = await connection.fetch("SELECT resource.*, tenant.slug AS tenant_slug FROM stock_service_resources resource JOIN tenants tenant ON tenant.id=resource.tenant_id ORDER BY name")

    families_by_category: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in families:
        attributes = dict(row["attributes"] or {})
        families_by_category.setdefault((str(row["tenant_slug"]), str(row["category_id"])), []).append({
            "id": str(row["id"]), "name": str(row["name"]), "colors": list(attributes.get("colors") or []),
        })
    definitions_by_category: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in definitions:
        settings = dict(row["settings"] or {})
        definitions_by_category.setdefault((str(row["tenant_slug"]), str(row["category_id"])), []).append({
            **settings, "id": str(row["id"]), "key": str(row["field_key"]), "name": str(row["label"]),
            "type": str(row["value_type"]), "required": bool(row["required"]), "options": list(row["options"] or []),
            "order": int(row["display_order"]),
        })
    payload: dict[str, Any] = {"schema": "chronos_stock_data_v2", "sale_items": [], "internal_items": [], "categories": [], "suppliers": [], "service_resources": [], "movements": []}
    for row in categories:
        key = (str(row["tenant_slug"]), str(row["id"]))
        columns = definitions_by_category.get(key) or list(row["custom_columns"] or [])
        payload["categories"].append({"id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "name": str(row["name"]), "custom_columns": columns, "families": families_by_category.get(key, [])})
    for row in items:
        attributes = dict(row["attributes"] or {})
        colors = attributes.pop("colors", []) or []
        item = {
            "id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "kind": str(row["kind"]), "name": str(row["name"]),
            "sku": str(row["sku"] or ""), "description": str(row["description"] or ""), "category": str(row["category_name"] or ""),
            "family": str(row["family_name"] or ""), "size": str(attributes.pop("size", "") or ""), "color": str(attributes.pop("color", "") or ""),
            "colors": list(colors), "finishes": list(attributes.pop("finishes", []) or []), "display_name": str(row["display_name"] or ""), "unit": str(row["unit"]),
            "quantity": number(row["quantity"]), "min_quantity": number(row["min_quantity"]), "cost_price": number(row["cost_price"]),
            "supplier": str(row["supplier"] or ""), "location": str(row["location"] or ""), "art_lead_days": int(row["art_lead_days"] or 0),
            "production_lead_days": int(row["production_lead_days"] or 0), "status": str(row["status"]), "attributes": attributes,
        }
        payload["sale_items" if item["kind"] == "sale" else "internal_items"].append(item)
    for row in suppliers:
        address = dict(row["address"] or {})
        payload["suppliers"].append({"id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "name": str(row["name"]), "document": str(row["document"] or ""), "contact_name": str(row["contact_name"] or ""), "phone": str(row["phone"] or ""), "email": str(row["email"] or ""), **address})
    payload["service_resources"] = [
        {**dict(row["settings"] or {}), "id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "name": str(row["name"]), "status": str(row["status"])}
        for row in resources
    ]
    payload["movements"] = [{"id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "item_id": str(row["stock_item_id"]), "type": str(row["movement_type"]), "quantity": number(row["quantity_delta"]), "reason": str(row["notes"] or ""), "requested_by": str(row["created_by_member_id"] or ""), "created_at": row["created_at"].isoformat()} for row in movements]
    return payload
