"""Company order sequences, serialized with the document import transaction."""
from fastapi import HTTPException
from .postgres import transaction


def checked_config(prefix, last_number, minimum):
    if last_number < minimum:
        raise HTTPException(409, f"O último número não pode ser menor que {minimum}, para não repetir pedidos.")
    return {"prefix": prefix, "last_number": last_number}


async def read_config(connection, tenant_id):
    config = await connection.fetchval("SELECT settings->'shop_order_numbering' FROM tenants WHERE id=$1", tenant_id) or {}
    maximum = await connection.fetchval("SELECT COALESCE(MAX(order_number),0) FROM shop_orders WHERE tenant_id=$1", tenant_id)
    return {"prefix": config.get("prefix", ""), "last_number": max(int(config.get("last_number", 0)), maximum)}


async def write_config(connection, tenant_id, config):
    await connection.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{shop_order_numbering}',$2::jsonb) WHERE id=$1", tenant_id, config)


async def configure(slug, updates=None):
    async with transaction() as connection:
        tenant_id = await connection.fetchval("SELECT id FROM tenants WHERE slug=$1", slug)
        if not tenant_id:
            raise HTTPException(404, "Empresa não encontrada.")
        await connection.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", "shop-documents:" + tenant_id)
        config = await read_config(connection, tenant_id)
        if updates is not None:
            config = checked_config(updates["prefix"], updates["last_number"], config["last_number"])
            await write_config(connection, tenant_id, config)
        return config


async def assign_number(connection, tenant_id, order):
    # Caller holds the company document lock until both sequence and order commit.
    existing = await connection.fetchrow("SELECT order_number, metadata FROM shop_orders WHERE tenant_id=$1 AND id=$2", tenant_id, order["id"])
    if existing:
        number = existing["order_number"]
        prefix = (existing["metadata"] or {}).get("order_prefix", "")
    else:
        config = await read_config(connection, tenant_id)
        number, prefix = config["last_number"] + 1, config["prefix"]
        await write_config(connection, tenant_id, {"prefix": prefix, "last_number": number})
    order.update(order_number=number, order_prefix=prefix)
    return number
