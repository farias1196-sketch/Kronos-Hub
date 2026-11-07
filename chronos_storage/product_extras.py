"""Reusable product additions, independent of price-list snapshot imports."""
from fastapi import HTTPException
from .postgres import transaction


def append_extra(options, extra):
    existing = next((item for item in options if item["description"].casefold() == extra["description"].casefold() and item.get("stock_item_id", "") == extra.get("stock_item_id", "")), None)
    if existing:
        if existing["quantity_prices"] != extra["quantity_prices"]:
            raise HTTPException(409, "Já existe um adicional com esta descrição e outro valor.")
        return existing
    if len(options) >= 100:
        raise HTTPException(422, "Este produto já possui 100 adicionais avulsos cadastrados.")
    options.append(extra)
    return extra


async def product_extras(slug, product_id=None, extra=None):
    async with transaction() as connection:
        row = await connection.fetchrow("SELECT id, settings->'shop_product_extras' AS extras FROM tenants WHERE slug=$1" + (" FOR UPDATE" if extra else ""), slug)
        if not row:
            raise HTTPException(404, "Empresa não encontrada.")
        catalog = dict(row["extras"] or {})
        if extra is None:
            return catalog
        result = append_extra(catalog.setdefault(product_id, []), extra)
        await connection.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{shop_product_extras}',$2::jsonb) WHERE id=$1", row["id"], catalog)
        return result
