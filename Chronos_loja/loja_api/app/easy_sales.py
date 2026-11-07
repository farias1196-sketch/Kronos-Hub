"""Discount and manual receipt rules shared by the simplified sales flow."""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException


def money(value):
    return float(Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def discount_amount(base, kind, value, strict=False):
    base, value = Decimal(str(base)), Decimal(str(value or 0))
    limit = Decimal(100) if kind == 'percent' else base
    if value < 0 or (strict and value > limit):
        raise HTTPException(422, 'O desconto deve ficar entre zero e o valor dos produtos (ou 100%).')
    amount = base * value / 100 if kind == 'percent' else value
    return money(min(base, max(Decimal(0), amount)))


def calculate_totals(cart):
    for item in cart.get('items', []):
        gross = money(Decimal(str(item.get('quantity') or 0)) * Decimal(str(item.get('unit_price') or 0)))
        if item.get('promotion'):
            promotion = item['promotion']
            packages = Decimal(str(item.get('quantity') or 0)) / Decimal(str(promotion['package_quantity']))
            extras = sum(Decimal(str(extra['unit_price'])) for extra in item.get('extras', []))
            gross = money(packages * Decimal(str(promotion['package_price'])) + Decimal(str(item['quantity'])) * extras)
        reduction = discount_amount(gross, item.get('discount_type', 'amount'), item.get('discount_value', item.get('discount', 0)))
        item.update(gross_total=gross, discount=reduction, total=money(Decimal(str(gross)) - Decimal(str(reduction))))
    gross = money(sum(Decimal(str(i['gross_total'])) for i in cart.get('items', [])))
    subtotal = money(sum(Decimal(str(i['total'])) for i in cart.get('items', [])))
    discount = discount_amount(subtotal, cart.get('discount_type', 'amount'), cart.get('discount_value', cart.get('discount', 0)))
    freight = money(cart.get('freight', 0))
    cart.update(gross_subtotal=gross, item_discount_total=money(gross-subtotal), subtotal=subtotal, discount=discount, freight=freight,
                total=money(Decimal(str(subtotal))-Decimal(str(discount))+Decimal(str(freight))))
    return cart


def apply_receipt(order, receipt, existing=None):
    if existing:
        if any(existing.get(k) != receipt.get(k) for k in ('amount', 'method', 'paid_on', 'notes')):
            raise HTTPException(409, 'Esta confirmação já foi registrada com outros valores. Atualize o pedido.')
        return {'ok': True, 'order': order, 'transaction': existing, 'existing': True}
    if order.get('status') == 'canceled':
        raise HTTPException(409, 'Não é possível receber pagamento de um pedido cancelado.')
    net_paid = money(float(order.get('paid_total') or 0) - float(order.get('refunded_total') or 0))
    remaining = money(float(order.get('total') or 0) - net_paid)
    if receipt['amount'] <= 0 or receipt['amount'] > remaining:
        raise HTTPException(409, 'O valor recebido deve ser maior que zero e não pode exceder o saldo do pedido.')
    order['paid_total'] = money(float(order.get('paid_total') or 0) + receipt['amount'])
    order['payment_status'] = 'paid' if money(net_paid + receipt['amount']) >= money(order['total']) else 'partial'
    order.setdefault('payment_receipts', []).append(receipt)
    order['updated_at'] = receipt['created_at']
    return {'ok': True, 'order': order, 'transaction': receipt}
