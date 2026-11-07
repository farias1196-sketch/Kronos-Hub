"""PostgreSQL state materialized in the current Loja API contract."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from .postgres import get_connection, transaction


def value(item: Any) -> Any:
    if isinstance(item, Decimal):
        return float(item)
    if isinstance(item, datetime):
        return item.isoformat()
    if isinstance(item, dict):
        return {key: value(entry) for key, entry in item.items()}
    if isinstance(item, list):
        return [value(entry) for entry in item]
    return item


async def load_loja_payload() -> dict[str, Any]:
    async with get_connection() as connection:
        configs = await connection.fetch("SELECT config.*, tenant.slug AS tenant_slug FROM shop_configs config JOIN tenants tenant ON tenant.id=config.tenant_id")
        products = await connection.fetch("SELECT product.*, tenant.slug AS tenant_slug FROM shop_products product JOIN tenants tenant ON tenant.id=product.tenant_id")
        variants = await connection.fetch("SELECT variant.*, tenant.slug AS tenant_slug FROM shop_product_variants variant JOIN tenants tenant ON tenant.id=variant.tenant_id")
        tiers = await connection.fetch("SELECT tier.*, tenant.slug AS tenant_slug FROM stock_tier_prices tier JOIN tenants tenant ON tenant.id=tier.tenant_id")
        carts = await connection.fetch("SELECT cart.*, tenant.slug AS tenant_slug FROM shop_carts cart JOIN tenants tenant ON tenant.id=cart.tenant_id")
        quotes = await connection.fetch("SELECT quote.*, tenant.slug AS tenant_slug FROM shop_quotes quote JOIN tenants tenant ON tenant.id=quote.tenant_id")
        orders = await connection.fetch("SELECT orders.*, tenant.slug AS tenant_slug FROM shop_orders orders JOIN tenants tenant ON tenant.id=orders.tenant_id")
        transactions = await connection.fetch("SELECT transaction.*, tenant.slug AS tenant_slug FROM shop_transactions transaction JOIN tenants tenant ON tenant.id=transaction.tenant_id")
        refunds = await connection.fetch("SELECT refund.*, tenant.slug AS tenant_slug FROM shop_refunds refund JOIN tenants tenant ON tenant.id=refund.tenant_id")
    data: dict[str, Any] = {"schema": "chronos_loja_data_v1", "configs": {}, "products": {}, "carts": {}, "quotes": {}, "orders": {}, "transactions": {}, "refunds": {}}
    for row in configs:
        config = value(dict(row["settings"] or {}))
        slug = str(row["tenant_slug"])
        data["configs"][slug] = {**config, "tenant_id": slug, "store_name": str(row["store_name"] or config.get("store_name") or ""), "chronos_slug": str(row["public_slug"] or slug), "custom_domain": str(row["custom_domain"] or ""), "custom_domain_status": str(row["domain_status"]), "whatsapp": str(row["whatsapp"] or ""), "theme": str(row["selected_template"] or config.get("theme") or "default"), "updated_at": value(row["updated_at"])}
    tiers_by_item: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in tiers:
        tiers_by_item.setdefault((str(row["tenant_slug"]), str(row["stock_item_id"])), []).append({"minimum_quantity": value(row["min_quantity"]), "unit_price": value(row["unit_price"])})
    variants_by_product: dict[tuple[str, str], dict[str, Any]] = {}
    for row in variants:
        details = value(dict(row["presentation"] or {}))
        stock_id = str(row["stock_item_id"])
        variants_by_product.setdefault((str(row["tenant_slug"]), str(row["shop_product_id"])), {})[stock_id] = {**details, "sale_price": value(row["sale_price"]), "promotional_price": value(row["promotional_price"]), "sellable": bool(row["sellable"]), "quantity_prices": tiers_by_item.get((str(row["tenant_slug"]), stock_id), [])}
    for row in products:
        slug, product_id = str(row["tenant_slug"]), str(row["id"])
        presentation = value(dict(row["presentation"] or {}))
        data["products"].setdefault(slug, {})[product_id] = {**presentation, "id": product_id, "tenant_id": slug, "public_name": str(row["public_name"] or ""), "public_description": str(row["public_description"] or ""), "public_category": str(row["public_category"] or ""), "image_url": str(row["image_url"] or ""), "published": bool(row["published"]), "highlight": bool(row["highlight"]), "order": int(row["display_order"]), "visible_stock": bool(row["visible_stock"]), "variant_prices": variants_by_product.get((slug, product_id), {})}
    for row in carts:
        snapshot = value(dict(row["snapshot"] or {})); snapshot.update(id=str(row["id"]), tenant_id=str(row["tenant_slug"]), status=str(row["status"]), source=str(row["source"]), updated_at=value(row["updated_at"]))
        data["carts"].setdefault(str(row["tenant_slug"]), {})[str(row["id"])] = snapshot
    for row in quotes:
        if row["status"] == "deleted":
            continue
        layout = value(dict(row["layout_snapshot"] or {})); quote = {"validity_mode": layout.get("validity_mode", "days"), "validity_text": layout.get("validity_text", ""), "id": str(row["id"]), "tenant_id": str(row["tenant_slug"]), "status": str(row["status"]), "valid_until": row["expires_at"].date().isoformat() if row["expires_at"] else "", "cart_id": (layout.get("cart_snapshot") or {}).get("id", ""), "cart_snapshot": layout.get("cart_snapshot") or {}, "message": layout.get("message") or "", "created_at": value(row["created_at"]), "updated_at": value(row["updated_at"])}
        data["quotes"].setdefault(str(row["tenant_slug"]), {})[quote["id"]] = quote
    for row in orders:
        if row["status"] == "deleted":
            continue
        order = value(dict(row["metadata"] or {})); order.update(order_number=int(row["order_number"]), order_prefix=order.get("order_prefix", ""), id=str(row["id"]), tenant_id=str(row["tenant_slug"]), status=str(row["status"]), total=value(row["total"]), subtotal=value(row["subtotal"]), discount=value(row["discount"]), freight=value(row["freight"]), updated_at=value(row["updated_at"]))
        data["orders"].setdefault(str(row["tenant_slug"]), {})[str(row["id"])] = order
    for row in transactions:
        transaction = value(dict(row["metadata"] or {})); transaction.update(id=str(row["id"]), tenant_id=str(row["tenant_slug"]), order_id=str(row["order_id"]), amount=value(row["amount"]), method=str(row["method"]), status=str(row["status"]), reference=str(row["reference"] or ""), notes=str(row["notes"] or ""), created_at=value(row["created_at"]))
        data["transactions"].setdefault(str(row["tenant_slug"]), {})[str(row["id"])] = transaction
    for row in refunds:
        refund = value(dict(row["metadata"] or {})); refund.update(id=str(row["id"]), tenant_id=str(row["tenant_slug"]), order_id=str(row["order_id"]), amount=value(row["amount"]), reason=str(row["reason"]), items=value(row["items"]), created_at=value(row["created_at"]))
        data["refunds"].setdefault(str(row["tenant_slug"]), {})[str(row["id"])] = refund
    return data


async def record_manual_receipt(slug, order_id, receipt_id, apply):
    from fastapi import HTTPException
    async with transaction() as connection:
        row = await connection.fetchrow("SELECT o.* FROM shop_orders o JOIN tenants t ON t.id=o.tenant_id WHERE t.slug=$1 AND o.id=$2 FOR UPDATE OF o", slug, order_id)
        if not row or row["status"] == "deleted":
            raise HTTPException(404, "Pedido não encontrado.")
        order = value(dict(row["metadata"] or {}))
        order.update(id=str(row["id"]), tenant_id=slug, total=value(row["total"]), status=str(row["status"]))
        previous = await connection.fetchval("SELECT metadata FROM shop_transactions WHERE tenant_id=$1 AND id=$2", row["tenant_id"], receipt_id)
        result = apply(order, dict(previous) if previous else None)
        if result.get("existing"):
            return result
        receipt = result["transaction"]
        stamp = datetime.fromisoformat(receipt["created_at"].replace("Z", "+00:00"))
        await connection.execute("INSERT INTO shop_transactions (id,tenant_id,order_id,amount,method,status,notes,metadata,created_at) VALUES ($1,$2,$3,$4,$5,'paid',$6,$7,$8)", receipt_id, row["tenant_id"], order_id, Decimal(str(receipt["amount"])), receipt["method"], receipt["notes"], receipt, stamp)
        await connection.execute("UPDATE shop_orders SET status=$1,metadata=$2,updated_at=$3 WHERE tenant_id=$4 AND id=$5", order["status"], order, stamp, row["tenant_id"], order_id)
        return result


async def load_order_payment_document(slug, order_id):
    """Keep totals and the payment ledger in the same read snapshot."""
    from fastapi import HTTPException
    async with get_connection() as connection:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            row = await connection.fetchrow("SELECT o.* FROM shop_orders o JOIN tenants t ON t.id=o.tenant_id WHERE t.slug=$1 AND o.id=$2 AND o.status <> 'deleted'", slug, order_id)
            if not row:
                raise HTTPException(404, "Pedido não encontrado.")
            order = value(dict(row["metadata"] or {}))
            order.update(id=str(row["id"]), tenant_id=slug, order_number=int(row["order_number"]), status=str(row["status"]), total=value(row["total"]), subtotal=value(row["subtotal"]), discount=value(row["discount"]), freight=value(row["freight"]), created_at=value(row["created_at"]))
            payments = await connection.fetch("SELECT * FROM shop_transactions WHERE tenant_id=$1 AND order_id=$2", row["tenant_id"], order_id)
            refunds = await connection.fetch("SELECT * FROM shop_refunds WHERE tenant_id=$1 AND order_id=$2", row["tenant_id"], order_id)
            config = await connection.fetchrow("SELECT store_name,settings FROM shop_configs WHERE tenant_id=$1", row["tenant_id"])
            store = {**dict(config["settings"] or {}), "store_name": config["store_name"]} if config else {}
            def entry(item):
                return {**value(dict(item["metadata"] or {})), **value({k: v for k, v in dict(item).items() if k != "metadata"})}
            return order, store, [entry(item) for item in payments], [entry(item) for item in refunds]


async def delete_quote(slug: str, quote_id: str) -> None:
    from fastapi import HTTPException
    async with transaction() as connection:
        tenant_id = await connection.fetchval("SELECT id FROM tenants WHERE slug=$1", slug)
        if not tenant_id:
            raise HTTPException(404, "Empresa não encontrada.")
        await connection.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "shop-documents:" + tenant_id)
        quote = await connection.fetchrow("SELECT status FROM shop_quotes WHERE tenant_id=$1 AND id=$2 FOR UPDATE", tenant_id, quote_id)
        if not quote or quote["status"] == "deleted":
            raise HTTPException(404, "Orçamento não encontrado.")
        linked = await connection.fetchval("SELECT EXISTS(SELECT 1 FROM shop_orders WHERE tenant_id=$1 AND quote_id=$2)", tenant_id, quote_id)
        if linked or quote["status"] == "approved":
            raise HTTPException(409, "Este orçamento já foi aprovado ou virou um pedido e não pode ser apagado.")
        # Keep a tombstone so an older whole-shop snapshot cannot resurrect the quote.
        await connection.execute("UPDATE shop_quotes SET status='deleted', updated_at=now() WHERE tenant_id=$1 AND id=$2", tenant_id, quote_id)


async def delete_order(slug: str, order_id: str) -> None:
    from fastapi import HTTPException
    async with transaction() as connection:
        tenant_id = await connection.fetchval("SELECT id FROM tenants WHERE slug=$1", slug)
        if not tenant_id:
            raise HTTPException(404, "Empresa não encontrada.")
        await connection.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", "shop-documents:" + tenant_id)
        order = await connection.fetchrow("SELECT status FROM shop_orders WHERE tenant_id=$1 AND id=$2 FOR UPDATE", tenant_id, order_id)
        if not order or order["status"] == "deleted":
            raise HTTPException(404, "Pedido não encontrado.")
        # Preserve financial records and prevent stale snapshots from restoring the order.
        await connection.execute("UPDATE shop_orders SET status='deleted', updated_at=now() WHERE tenant_id=$1 AND id=$2", tenant_id, order_id)
