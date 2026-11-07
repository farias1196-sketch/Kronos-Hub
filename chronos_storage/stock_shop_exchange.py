"""One CSV, one database transaction for Stock and Loja corrections."""
from decimal import Decimal
from fastapi import HTTPException
from .postgres import get_connection

SHOP_COLUMNS = ['loja_produto_id', 'preco_venda', 'preco_promocional', 'vender_loja', 'precos_por_quantidade']


async def read_shop_prices(slug):
    async with get_connection() as connection:
        variants = await connection.fetch("SELECT v.* FROM shop_product_variants v JOIN tenants t ON t.id=v.tenant_id WHERE t.slug=$1", slug)
        tiers = await connection.fetch("SELECT p.* FROM stock_tier_prices p JOIN tenants t ON t.id=p.tenant_id WHERE t.slug=$1 ORDER BY p.min_quantity", slug)
    prices = {}
    for row in variants:
        key = str(row['stock_item_id'])
        if key in prices:
            raise HTTPException(409, 'Uma variação está vinculada a mais de um produto da Loja. Revise o cadastro antes de exportar.')
        prices[key] = {'loja_produto_id': str(row['shop_product_id']), 'preco_venda': str(row['sale_price']),
                       'preco_promocional': '' if row['promotional_price'] is None else str(row['promotional_price']),
                       'vender_loja': 'sim' if row['sellable'] else 'nao', 'precos_por_quantidade': ''}
    grouped = {}
    for row in tiers:
        grouped.setdefault(str(row['stock_item_id']), []).append(f"{row['min_quantity']}:{row['unit_price']}")
    for key, price in prices.items():
        price['precos_por_quantidade'] = ' | '.join(grouped.get(key, []))
    return prices


def decimal_price(raw):
    text = str(raw).strip().replace(',', '.')
    try:
        value = Decimal(text)
        if not value.is_finite() or value < 0 or value >= Decimal('100000000000000') or value.as_tuple().exponent < -4:
            raise ValueError()
        return value
    except Exception:
        raise ValueError('Preço inválido: use valor não negativo, sem separador de milhar e com até quatro casas decimais.') from None


def parse_shop_columns(values):
    # A blank Loja identifier means that this line only changes Stock.
    product_id = str(values.get('loja_produto_id') or '').strip()
    if not product_id:
        if any(str(values.get(k) or '').strip() for k in SHOP_COLUMNS[1:]):
            raise ValueError('Preços informados sem loja_produto_id. Sincronize o produto na Loja e exporte novamente.')
        return None
    if any(k not in values for k in SHOP_COLUMNS):
        raise ValueError('Mantenha todas as colunas da Loja para importar os preços.')
    sale = decimal_price(values.get('preco_venda') or 0)
    promo_raw = str(values.get('preco_promocional') or '').strip()
    promo = decimal_price(promo_raw) if promo_raw else None
    sellable = str(values.get('vender_loja') or '').strip().lower()
    if sellable not in {'sim', 'nao', 'não'}:
        raise ValueError('vender_loja precisa ser sim ou nao.')
    tiers, seen = [], set()
    for part in str(values.get('precos_por_quantidade') or '').split('|'):
        if not part.strip(): continue
        try: minimum, unit = part.split(':')
        except ValueError: raise ValueError('Faixas: use quantidade:preço | quantidade:preço. Exemplo: 100:2,3456 | 200:2,10.') from None
        qty, price = decimal_price(minimum), decimal_price(unit)
        if qty <= 0 or qty != qty.to_integral_value() or qty in seen or price <= 0:
            raise ValueError('As faixas precisam de quantidades inteiras positivas, sem repetição, e preços maiores que zero.')
        seen.add(qty); tiers.append({'minimum_quantity': int(qty), 'unit_price': str(price)})
    return {'product_id': product_id, 'sale_price': str(sale), 'promotional_price': str(promo) if promo is not None else None,
            'sellable': sellable == 'sim', 'quantity_prices': sorted(tiers, key=lambda t: t['minimum_quantity'])}


async def commit_stock_shop(slug, stock_payload, price_updates, auxiliary=None):
    raise HTTPException(503, "A importação conjunta requer PostgreSQL e está desligada nesta distribuição local.")
