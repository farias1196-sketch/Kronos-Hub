"""Create inventory and selling configuration together, without changing siblings."""
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
from .postgres import transaction


async def create_variant(slug, product, values):
    ident = 'sale-' + uuid4().hex
    async with transaction() as db:
        tenant = await db.fetchval('SELECT id FROM tenants WHERE slug=$1 FOR UPDATE', slug)
        if not tenant:
            raise HTTPException(404, 'Empresa não encontrada.')
        saved = await db.fetchrow('SELECT * FROM shop_products WHERE tenant_id=$1 AND id=$2', tenant, product['id'])
        if not saved:
            raise HTTPException(404, 'Produto não encontrado.')
        source_id = next((v['stock_item_id'] for v in product.get('variants', []) if v.get('stock_item_id')), None)
        source = await db.fetchrow('SELECT * FROM stock_items WHERE tenant_id=$1 AND id=$2', tenant, source_id) if source_id else None
        family = await db.fetchrow('SELECT * FROM stock_families WHERE tenant_id=$1 AND id=$2', tenant, saved['stock_family_id']) if saved['stock_family_id'] else None
        category_id = source['category_id'] if source else (family['category_id'] if family else None)
        family_id = source['family_id'] if source else (family['id'] if family else None)
        sku = values['sku'].strip() or 'VAR-' + uuid4().hex[:12].upper()
        if await db.fetchval('SELECT 1 FROM stock_items WHERE tenant_id=$1 AND lower(sku)=lower($2)', tenant, sku):
            raise HTTPException(409, 'Este SKU já está cadastrado nesta empresa.')
        attributes = {**(dict(source['attributes'] or {}) if source else {}), 'size': values['size'].strip(), 'color': values['color'].strip(), 'colors': [values['color'].strip()] if values['color'].strip() else [], 'finishes': values['finishes']}
        name = ' '.join(filter(None, [product.get('family') or product['public_name'], attributes['size'], attributes['color']]))[:255]
        await db.execute('''INSERT INTO stock_items
            (id,tenant_id,category_id,family_id,sku,name,display_name,kind,unit,quantity,cost_price,attributes)
            VALUES ($1,$2,$3,$4,$5,$6,$6,'sale',$7,0,0,$8)''',
            ident, tenant, category_id, family_id, sku, name, values['unit'], attributes)
        await db.execute('''INSERT INTO shop_product_variants
            (id,tenant_id,shop_product_id,stock_item_id,sale_price,sellable)
            VALUES ($1,$2,$3,$4,$5,true)''', 'variant-' + uuid4().hex, tenant, product['id'], ident, Decimal(str(values['sale_price'])))
        for tier in values['quantity_prices']:
            await db.execute('''INSERT INTO stock_tier_prices(id,tenant_id,stock_item_id,min_quantity,unit_price)
                VALUES($1,$2,$3,$4,$5)''', 'tier-' + uuid4().hex, tenant, ident, Decimal(str(tier['minimum_quantity'])), Decimal(str(tier['unit_price'])))
    return ident
