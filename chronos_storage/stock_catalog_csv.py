"""Editable catalog records supplementing the Stock/Loja product CSV."""
import copy
import hashlib
import json
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from fastapi import HTTPException
from .postgres import get_connection
from .stock_shop_exchange import decimal_price

COLUMNS = ['registro', 'stock_item_id', 'promocional', 'registro_versao',
    'adicional_id', 'adicional_origem', 'adicional_escopo', 'adicional_grupo',
    'adicional_descricao', 'adicional_sob_consulta', 'adicional_precos_por_quantidade',
    'promocao_id', 'promocao_nome', 'promocao_quantidade_pacote', 'promocao_valor_pacote',
    'promocao_inicio', 'promocao_termino', 'promocao_situacao']

def version(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

async def read_catalog_details(slug):
    async with get_connection() as db:
        async with db.transaction(isolation='repeatable_read', readonly=True):
            tenant = await db.fetchrow('SELECT settings FROM tenants WHERE slug=$1', slug)
            variants = await db.fetch('SELECT v.* FROM shop_product_variants v JOIN tenants t ON t.id=v.tenant_id WHERE t.slug=$1', slug)
    settings = (tenant['settings'] or {}) if tenant else {}
    return {'registered': {str(v['stock_item_id']): (v['presentation'] or {}).get('registered_extras', []) for v in variants},
            'manual': settings.get('shop_product_extras') or {}, 'promotions': settings.get('shop_promotions') or {}}

def auxiliary_rows(base_rows, details):
    """One row per extra or offer. Family extras appear once, with their scope."""
    by_id = {r['stock_item_id']: r for r in base_rows}
    output, seen_manual = [], set()
    today = datetime.now(timezone(timedelta(hours=-3))).date()
    for row in base_rows:
        row.update(registro='PRODUTO', promocional='nao')
        options = [(e, 'CADASTRO') for e in details['registered'].get(row['stock_item_id'], [])]
        options += [(e, 'AVULSO') for e in details['manual'].get(row.get('loja_produto_id'), [])
                    if not e.get('stock_item_id') or e['stock_item_id'] == row['stock_item_id']]
        finishes = [e['description'] for e, _ in options if e.get('group') == 'finish']
        row['acabamentos'] = ' | '.join(dict.fromkeys([s.strip() for s in row.get('acabamentos', '').split('|') if s.strip()] + finishes))
        for extra, origin in options:
            scope = 'FAMILIA' if origin == 'AVULSO' and not extra.get('stock_item_id') else 'VARIACAO'
            identity = (row.get('loja_produto_id'), extra['id'])
            if origin == 'AVULSO':
                if identity in seen_manual: continue
                seen_manual.add(identity)
            output.append({**{k: row.get(k, '') for k in ['sku', 'stock_item_id', 'nome', 'categoria', 'familia', 'tamanho', 'cor', 'unidade', 'loja_produto_id']},
                'registro': 'ACABAMENTO' if extra.get('group') == 'finish' else 'ADICIONAL', 'promocional': 'nao',
                'registro_versao': version(extra), 'adicional_id': extra['id'], 'adicional_origem': origin,
                'adicional_escopo': scope, 'adicional_grupo': extra.get('group', 'custom'),
                'adicional_descricao': extra['description'], 'adicional_sob_consulta': 'sim' if extra.get('on_request') else 'nao',
                'adicional_precos_por_quantidade': ' | '.join(f"{t['minimum_quantity']}:{t['unit_price']}" for t in extra.get('quantity_prices', []))})
    for promotion in details['promotions'].values():
        base = by_id.get(promotion['stock_item_id'])
        if not base or base.get('loja_produto_id') != promotion['product_id']:
            raise HTTPException(409, 'Promoção sem vínculo válido no Stock/Loja. Corrija o cadastro antes de exportar.')
        output.append({**{k: base.get(k, '') for k in ['sku', 'stock_item_id', 'categoria', 'familia', 'tamanho', 'cor', 'unidade', 'loja_produto_id', 'acabamentos']},
            'registro': 'PROMOCAO', 'nome': promotion['name'], 'promocional': 'sim', 'registro_versao': version(promotion),
            'promocao_id': promotion['id'], 'promocao_nome': promotion['name'],
            'promocao_quantidade_pacote': promotion['package_quantity'], 'promocao_valor_pacote': promotion['package_price'],
            'promocao_inicio': promotion['starts_on'], 'promocao_termino': promotion['ends_on'],
            'promocao_situacao': 'INVALIDA' if today > date.fromisoformat(promotion['ends_on']) else 'AGENDADA' if today < date.fromisoformat(promotion['starts_on']) else 'VALIDA'})
    return [*base_rows, *output]

def extra_target(details, item_id, product_id, origin, extra_id):
    options = details['registered'].get(item_id, []) if origin == 'CADASTRO' else details['manual'].get(product_id, [])
    return next((e for e in options if e['id'] == extra_id and (origin == 'CADASTRO' or not e.get('stock_item_id') or e['stock_item_id'] == item_id)), None)

def parse_auxiliary(values, item, details, product_id):
    kind = values.get('registro', '').strip().upper()
    if kind not in {'ADICIONAL', 'ACABAMENTO', 'PROMOCAO'}: raise ValueError('registro precisa ser PRODUTO, ADICIONAL, ACABAMENTO ou PROMOCAO.')
    if not item or values.get('stock_item_id') != item.id or values.get('loja_produto_id') != product_id:
        raise ValueError('Vínculo Stock/Loja alterado. Preserve SKU, stock_item_id e loja_produto_id.')
    result = {'record': kind, 'stock_item_id': item.id, 'product_id': product_id, 'sku': item.sku}
    if kind == 'PROMOCAO':
        old = details['promotions'].get(values.get('promocao_id'))
        if not old or old['stock_item_id'] != item.id or old['product_id'] != product_id: raise ValueError('Promoção não encontrada neste produto.')
        name = str(values.get('promocao_nome') or '').strip()
        if not name or len(name) > 300: raise ValueError('Informe o nome da promoção, com até 300 caracteres.')
        quantity, price = decimal_price(values.get('promocao_quantidade_pacote')), decimal_price(values.get('promocao_valor_pacote'))
        if quantity <= 0 or quantity != quantity.to_integral_value() or price <= 0: raise ValueError('Quantidade do pacote deve ser inteira positiva e seu preço maior que zero.')
        try:
            start, end = date.fromisoformat(values.get('promocao_inicio', '')), date.fromisoformat(values.get('promocao_termino', ''))
        except ValueError: raise ValueError('Datas da promoção devem usar AAAA-MM-DD.') from None
        if end < start: raise ValueError('Término da promoção anterior ao início.')
        updated = {**old, 'name': name, 'package_quantity': int(quantity), 'package_price': float(price), 'starts_on': start.isoformat(), 'ends_on': end.isoformat()}
        result.update(id=old['id'])
    else:
        origin = str(values.get('adicional_origem', '')).upper()
        if origin not in {'CADASTRO', 'AVULSO'}: raise ValueError('Origem do adicional inválida.')
        old = extra_target(details, item.id, product_id, origin, values.get('adicional_id'))
        if not old: raise ValueError('Adicional não encontrado neste produto.')
        scope = 'FAMILIA' if origin == 'AVULSO' and not old.get('stock_item_id') else 'VARIACAO'
        if values.get('adicional_escopo') != scope: raise ValueError('Preserve o escopo do adicional cadastrado.')
        description = str(values.get('adicional_descricao') or '').strip()
        if not description or len(description) > 300: raise ValueError('Descrição do adicional obrigatória, com até 300 caracteres.')
        group = values.get('adicional_grupo') or ''
        if group != old.get('group', 'custom'): raise ValueError('Preserve o grupo do adicional cadastrado.')
        if (kind == 'ACABAMENTO') != (group == 'finish'): raise ValueError('Tipo do registro incompatível com o grupo do adicional.')
        consult = str(values.get('adicional_sob_consulta') or '').casefold()
        if consult not in {'sim', 'nao', 'não'}: raise ValueError('adicional_sob_consulta precisa ser sim ou nao.')
        tiers, seen = [], set()
        for part in str(values.get('adicional_precos_por_quantidade') or '').split('|'):
            if not part.strip(): continue
            try: minimum, amount = part.split(':')
            except ValueError: raise ValueError('Faixas do adicional: quantidade:preço | quantidade:preço.') from None
            qty, price = decimal_price(minimum), decimal_price(amount)
            if qty <= 0 or price <= 0 or qty in seen: raise ValueError('Faixas do adicional precisam de quantidades e preços positivos, sem repetição.')
            seen.add(qty); tiers.append({'minimum_quantity': float(qty), 'unit_price': float(price)})
        if not tiers and consult != 'sim': raise ValueError('Informe preços do adicional ou marque sob consulta.')
        updated = {**old, 'description': description, 'on_request': consult == 'sim', 'quantity_prices': sorted(tiers, key=lambda t: t['minimum_quantity'])}
        # Avoid changing legacy optional keys or numeric types on a no-op import.
        if updated['description'] == old['description'] and updated['quantity_prices'] == old.get('quantity_prices', []) and updated['on_request'] == bool(old.get('on_request')):
            updated = copy.deepcopy(old)
        result.update(id=old['id'], origin=origin)
    if values.get('registro_versao') != version(old): raise ValueError('Este registro mudou depois da exportação. Exporte novamente antes de editar.')
    result.update(before=old, after=updated)
    return result

async def apply_auxiliary(db, tenant_id, changes):
    """Called inside the same transaction as the Stock and ordinary Loja prices."""
    if not changes: return
    settings = dict(await db.fetchval('SELECT settings FROM tenants WHERE id=$1 FOR UPDATE', tenant_id) or {})
    manual = copy.deepcopy(settings.get('shop_product_extras') or {})
    promotions = copy.deepcopy(settings.get('shop_promotions') or {})
    for change in changes:
        linked = await db.fetchval('SELECT id FROM shop_product_variants WHERE tenant_id=$1 AND stock_item_id=$2 AND shop_product_id=$3 FOR UPDATE', tenant_id, change['stock_item_id'], change['product_id'])
        if not linked: raise HTTPException(409, 'Vínculo Stock/Loja alterado. Gere uma nova prévia.')
        if change['record'] == 'PROMOCAO':
            old = promotions.get(change['id'])
            if old != change['before']: raise HTTPException(409, 'Promoção alterada. Gere uma nova prévia.')
            if change['after'] != old:
                promotions[change['id']] = {**change['after'], 'revision': old.get('revision', 1) + 1}
        elif change['origin'] == 'AVULSO':
            options = manual.get(change['product_id'], [])
            old = next((e for e in options if e['id'] == change['id']), None)
            if old != change['before']: raise HTTPException(409, 'Adicional alterado. Gere uma nova prévia.')
            options[options.index(old)] = change['after']
        else:
            row = await db.fetchrow('SELECT id,presentation FROM shop_product_variants WHERE tenant_id=$1 AND stock_item_id=$2 AND shop_product_id=$3 FOR UPDATE', tenant_id, change['stock_item_id'], change['product_id'])
            if not row: raise HTTPException(409, 'Vínculo do adicional alterado.')
            presentation = copy.deepcopy(row['presentation'] or {})
            options = presentation.get('registered_extras', [])
            old = next((e for e in options if e['id'] == change['id']), None)
            if old != change['before']: raise HTTPException(409, 'Acabamento/adicional alterado. Gere uma nova prévia.')
            options[options.index(old)] = change['after']
            await db.execute('UPDATE shop_product_variants SET presentation=$1::jsonb WHERE id=$2 AND tenant_id=$3', presentation, row['id'], tenant_id)
    await db.execute("UPDATE tenants SET settings=jsonb_set(jsonb_set(COALESCE(settings,'{}'::jsonb),'{shop_product_extras}',$2::jsonb),'{shop_promotions}',$3::jsonb) WHERE id=$1", tenant_id, manual, promotions)
