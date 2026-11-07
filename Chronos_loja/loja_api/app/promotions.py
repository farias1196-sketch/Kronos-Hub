"""Dated package offers sharing the original inventory item."""
import calendar
import copy
import json
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from preview_config import ROOT
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from chronos_storage import atomic_write_json
from chronos_storage.postgres import transaction
from chronos_storage.runtime_sync import postgres_mode, run

LOCK = RLock()
DATA_PATH = ROOT / ".local/loja/promotions.json"

def today():
    try:
        zone = ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        # Windows installations without the optional tzdata package.
        zone = timezone(timedelta(hours=-3))
    return datetime.now(zone).date()

def next_month(day):
    year, month = day.year + (day.month == 12), day.month % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))

def expired(promotion):
    return today() > date.fromisoformat(promotion["ends_on"])

def change(catalog, payload, promotion_id=None):
    stamp = today()
    if promotion_id:
        old = catalog.get(promotion_id)
        if not old:
            raise HTTPException(404, "Promoção não encontrada.")
        promotion = {**old, "package_price": payload["package_price"], "revision": old.get("revision", 1) + 1}
    else:
        promotion = {**payload, "id": "promotion-" + uuid4().hex, "revision": 1}
    promotion.update(starts_on=stamp.isoformat(), ends_on=next_month(stamp).isoformat())
    catalog[promotion["id"]] = promotion
    return promotion

async def pg_store(slug, payload=None, promotion_id=None):
    async with transaction() as db:
        row = await db.fetchrow("SELECT id, settings->'shop_promotions' AS promotions FROM tenants WHERE slug=$1" + (" FOR UPDATE" if payload else ""), slug)
        if not row:
            raise HTTPException(404, "Empresa não encontrada.")
        catalog = dict(row["promotions"] or {})
        if payload is None:
            return catalog
        result = change(catalog, payload, promotion_id)
        await db.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{shop_promotions}',$2::jsonb) WHERE id=$1", row["id"], catalog)
        return result

def store(slug, payload=None, promotion_id=None):
    if postgres_mode("loja") == "primary":
        return run(pg_store(slug, payload, promotion_id))
    with LOCK:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else {}
        catalog = data.setdefault(slug, {})
        if payload is None:
            return catalog
        result = change(catalog, payload, promotion_id)
        atomic_write_json(DATA_PATH, data)
        return result

def products(base, catalog):
    originals = {product["id"]: product for product in base}
    offers = []
    for promotion in catalog.values():
        source = originals.get(promotion["product_id"])
        if not source:
            continue
        variant = next((v for v in source["variants"] if str(v["stock_item_id"]) == promotion["stock_item_id"]), None)
        if not variant:
            continue
        info = {**promotion, "invalid": expired(promotion)}
        option = {**copy.deepcopy(variant), "promotion": info, "promotional_price": 0, "sale_price": promotion["package_price"] / promotion["package_quantity"], "quantity_prices": []}
        offers.append({**source, "id": promotion["id"], "public_name": promotion["name"], "family": promotion["name"], "promotion": info, "variants": [option], "variant_prices": {}})
    return offers

def price(variant, quantity):
    promotion = variant["promotion"]
    if expired(promotion):
        raise HTTPException(409, "Promoção inválida. Revalide a promoção antes de adicionar ao carrinho.")
    if Decimal(str(quantity)) % Decimal(str(promotion["package_quantity"])):
        raise HTTPException(422, f"Esta promoção exige múltiplos de {promotion['package_quantity']} unidades.")
    return {"unit_price": promotion["package_price"] / promotion["package_quantity"], "price_source": "package_promotion", "minimum_quantity": promotion["package_quantity"]}

def validate_cart(slug, cart, deadline=None):
    items = [item for item in cart.get("items", []) if item.get("promotion")]
    if not items:
        return deadline
    catalog = store(slug)
    for item in items:
        snapshot = item["promotion"]
        current = catalog.get(snapshot["id"])
        if not current or expired(current) or expired(snapshot):
            raise HTTPException(409, "Promoção inválida no carrinho. Revalide e adicione o item novamente.")
        if current["revision"] != snapshot["revision"]:
            raise HTTPException(409, "A promoção foi atualizada. Remova o item e adicione novamente para confirmar o novo valor.")
        if deadline:
            deadline = min(deadline, snapshot["ends_on"])
    return deadline
