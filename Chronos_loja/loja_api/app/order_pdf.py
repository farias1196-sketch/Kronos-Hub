"""Customer-facing, non-fiscal order payment statement."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from .quote_pdf import money, quantity, format_date, company_contact, brand_colors, safe_text, fit_size, wrap_text
from reportlab.lib.utils import ImageReader

METHODS = {"pix": "Pix", "cash": "Dinheiro", "card": "Cartão", "transfer": "Transferência", "other": "Outro", "manual": "Manual"}

def amount(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))

def payment_statement(order, transactions, refunds):
    ledger = {r["id"]: r for r in order.get("payment_receipts", []) if r.get("id")}
    ledger.update({r["id"]: r for r in transactions if r.get("order_id") == order["id"] and r.get("status") in {"paid", "partial"}})
    receipts = sorted(ledger.values(), key=lambda r: r.get("paid_on") or r.get("created_at") or "")
    total, paid, returned = (amount(order.get(key)) for key in ("total", "paid_total", "refunded_total"))
    net = max(Decimal(0), paid - returned)
    balance = max(Decimal(0), total - net)
    status = "PEDIDO CANCELADO" if order.get("status") == "canceled" else "PEDIDO QUITADO" if balance == 0 and paid > 0 else "SEM SALDO A PAGAR" if total == 0 else "PAGAMENTO PARCIAL" if net > 0 else "SEM PAGAMENTO REGISTRADO"
    return {"total": total, "paid": paid, "returned": returned, "net": net, "balance": balance, "status": status, "receipts": receipts,
            "refunds": [r for r in refunds if r.get("order_id") == order["id"]],
            "undetailed": max(Decimal(0), paid - sum((amount(r.get("amount")) for r in receipts), Decimal(0)))}

def build_order_pdf(order, store, company, transactions=(), refunds=()):
    palette = brand_colors(company)
    statement = payment_statement(order, transactions, refunds)
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=148, bottomMargin=44, title="Comprovante de pagamento do pedido", author="CHRONOS")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallText", fontName="Helvetica", fontSize=8, leading=11, textColor=palette["muted"], wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CellText", fontName="Helvetica", fontSize=9, leading=12, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="StatementTitle", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=palette["ink"], spaceAfter=8))
    styles["Heading2"].textColor = palette["ink"]
    styles["CellText"].textColor = palette["ink"]
    def p(value, style="CellText"):
        return Paragraph(escape(str(value or "-")).replace("\n", "<br/>"), styles[style])
    def table(rows, widths, header=True):
        grid = Table([[p(cell) for cell in row] for row in rows], colWidths=widths, repeatRows=1 if header else 0, splitInRow=1, hAlign="LEFT")
        commands = [("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7), ("LINEBELOW", (0,0), (-1,-1), .4, palette["line"])]
        if header: commands.append(("BACKGROUND", (0,0), (-1,0), palette["soft"]))
        grid.setStyle(TableStyle(commands))
        return grid
    story = []
    company_name = company.get("trade_name") or company.get("name") or store.get("store_name") or "Empresa"
    label = f"{order.get('order_prefix') or ''}{order['order_number']}" if order.get("order_number") is not None else order["id"]
    emitted = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M (Brasília)")
    story += [p("COMPROVANTE DE PAGAMENTO", "StatementTitle"), p("Controle do pedido - sem valor fiscal", "SmallText"), Spacer(1,10),
              p(f"Pedido {label}"), p(f"Emissão: {emitted} | Pedido criado em: {format_date(order.get('created_at'))}", "SmallText"),
              Spacer(1,10), p(f"Cliente: {order.get('client_name') or 'Não informado'}"), p(f"Telefone: {order.get('client_phone') or 'Não informado'}", "SmallText"),
              p(f"Vendedor: {order.get('seller_name') or 'Não informado'}", "SmallText"), Spacer(1,14)]
    summary = [[statement["status"], ""], ["Total do pedido", money(statement["total"])], ["Total recebido", money(statement["paid"])]]
    if statement["returned"]: summary += [["Valores devolvidos", money(statement["returned"])], ["Recebido líquido", money(statement["net"])]]
    summary.append(["Saldo restante", money(statement["balance"])])
    if statement["net"] > statement["total"]: summary.append(["Recebido acima do total", money(statement["net"] - statement["total"])])
    story += [KeepTogether(table(summary, [365,150])), Spacer(1,18), p("Itens do pedido", "Heading2")]
    rows = [["Produto / descrição", "Qtd.", "Unitário", "Total"]]
    for item in order.get("items", []):
        details = [item.get("product_name") or "Item", " · ".join(str(item.get(k) or "") for k in ("sku", "size", "color") if item.get(k))]
        if item.get("finishes"): details.append("Acabamentos: " + ", ".join(item["finishes"]))
        if item.get("extras"): details.append("Adicionais: " + "; ".join(f"{e['description']} (+{money(e['unit_price'])}/un)" for e in item["extras"]))
        if item.get("promotion"): details.append(f"Pacote: {item['promotion']['package_quantity']} unidades por {money(item['promotion']['package_price'])}")
        if item.get("discount"): details.append("Desconto do item: " + money(item["discount"]))
        if item.get("notes"): details.append(item["notes"])
        rows.append(["\n".join(filter(None, details)), quantity(item.get("quantity")), money(item.get("unit_price")), money(item.get("total"))])
    story += [table(rows, [280,55,85,95]), Spacer(1,10), table([["Subtotal dos itens", money(order.get("subtotal"))], ["Desconto do carrinho", money(order.get("discount"))], ["Frete", money(order.get("freight"))]], [365,150], False), Spacer(1,18), p("Pagamentos registrados", "Heading2")]
    payments = [["Data", "Forma de pagamento", "Valor"]]
    for receipt in statement["receipts"]:
        payments.append([format_date(receipt.get("paid_on") or receipt.get("created_at")), METHODS.get(receipt.get("method"), receipt.get("method") or "Não informada"), money(receipt.get("amount"))])
    if len(payments) > 1: story.append(table(payments, [115,260,140]))
    else: story.append(p("Nenhum recebimento com data e forma de pagamento detalhadas.", "SmallText"))
    if statement["undetailed"]: story.append(p(f"Valor recebido registrado no pedido sem detalhamento: {money(statement['undetailed'])}.", "SmallText"))
    if statement["refunds"]:
        story += [Spacer(1,12), p("Devoluções registradas", "Heading2"), table([["Data", "Descrição", "Valor"]] + [[format_date(r.get("created_at")), r.get("reason") or "Devolução", money(r.get("amount"))] for r in statement["refunds"]], [115,260,140])]
    story += [Spacer(1,14), p("Este documento apresenta os pagamentos registrados até a emissão. Uma nova emissão reflete os recebimentos posteriores. Não substitui nota fiscal.", "SmallText")]
    def footer(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(palette["header"])
        canvas.rect(0, height-122, width, 122, fill=1, stroke=0)
        canvas.setFillColor(palette["accent"])
        canvas.rect(0, height-6, width, 6, fill=1, stroke=0)
        title_x = 40
        if company.get("logo_bytes"):
            try:
                canvas.drawImage(ImageReader(BytesIO(company["logo_bytes"])), 40, height-112, width=102, height=102, preserveAspectRatio=True, anchor="c", mask="auto")
                title_x = 156
            except Exception:
                pass
        available = width-title_x-40
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", fit_size(company_name, "Helvetica-Bold", 16, available, 10))
        canvas.drawString(title_x, height-54, safe_text(company_name))
        canvas.setFillColor(palette["header_muted"])
        canvas.setFont("Helvetica", 8)
        contact = company_contact(company, store)
        contact_lines = company.get("pdf_header_lines") if company.get("pdf_header_lines") is not None else wrap_text(contact, "Helvetica", 8, available)[:3]
        for i, line in enumerate(contact_lines):
            canvas.setFont("Helvetica", fit_size(line, "Helvetica", 8, available, 4))
            canvas.drawString(title_x, height-74-i*10, safe_text(line))
        canvas.restoreState()
        canvas.saveState(); canvas.setFont("Helvetica",8); canvas.setFillColor(palette["muted"])
        canvas.drawString(40,25,"CHRONOS | Controle de pagamentos - sem valor fiscal")
        canvas.drawRightString(A4[0]-40,25,f"Página {document.page}"); canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
