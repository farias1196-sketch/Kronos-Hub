from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas


PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN * 2)
NAVY = HexColor("#0B1F33")
GREEN = HexColor("#147A5A")
GOLD = HexColor("#D89B35")
INK = HexColor("#172735")
MUTED = HexColor("#5D6D7C")
LINE = HexColor("#D7E0E7")
PALE = HexColor("#F2F6F8")
MINT = HexColor("#EAF6F0")
WHITE_SMOKE = HexColor("#FAFCFD")

THEME_COLORS = {
    "rosa-branco": {"header": "#3B1026", "accent": "#EC4899", "header_muted": "#F9A8D4", "ink": "#3B1026", "muted": "#6D2448", "line": "#F9A8D4", "card": "#FFF7FB", "total": "#FCE7F3", "total_line": "#F9A8D4", "soft": "#FDF2F8", "text_on_header": "#FFFFFF"},
    "verde-branco": {"header": "#082F1A", "accent": "#22C55E", "header_muted": "#86EFAC", "ink": "#082F1A", "muted": "#14532D", "line": "#86EFAC", "card": "#F6FFF9", "total": "#DCFCE7", "total_line": "#86EFAC", "soft": "#ECFDF3", "text_on_header": "#FFFFFF"},
    "azul-branco": {"header": "#0F2547", "accent": "#2563EB", "header_muted": "#93C5FD", "ink": "#0F2547", "muted": "#1E3A8A", "line": "#93C5FD", "card": "#F6F9FF", "total": "#DBEAFE", "total_line": "#93C5FD", "soft": "#EFF6FF", "text_on_header": "#FFFFFF"},
    "laranja-cinza": {"header": "#171717", "accent": "#F97316", "header_muted": "#FDBA74", "ink": "#1F2937", "muted": "#4B5563", "line": "#D1D5DB", "card": "#F9FAFB", "total": "#FFF7ED", "total_line": "#FDBA74", "soft": "#F3F4F6", "text_on_header": "#FFFFFF"},
    "rosa-preto": {"header": "#09070B", "accent": "#F472B6", "header_muted": "#F9A8D4", "ink": "#2B0717", "muted": "#831843", "line": "#F9A8D4", "card": "#FFF7FB", "total": "#FCE7F3", "total_line": "#F9A8D4", "soft": "#FDF2F8", "text_on_header": "#FFFFFF"},
    "prata-cinza": {"header": "#15191F", "accent": "#CBD5E1", "header_muted": "#CBD5E1", "ink": "#1F2937", "muted": "#475569", "line": "#CBD5E1", "card": "#F8FAFC", "total": "#F1F5F9", "total_line": "#CBD5E1", "soft": "#F1F5F9", "text_on_header": "#FFFFFF"},
}


def brand_colors(company: dict[str, Any]) -> dict[str, HexColor]:
    selected = THEME_COLORS.get(str(company.get("theme_slug") or ""), THEME_COLORS["rosa-branco"])
    return {key: HexColor(value) for key, value in selected.items()}


def safe_text(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip() or fallback
    return text.encode("latin-1", "replace").decode("latin-1")


def money(value: Any) -> str:
    amount = float(value or 0)
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def quantity(value: Any) -> str:
    amount = float(value or 0)
    return str(int(amount)) if amount.is_integer() else f"{amount:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def format_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return raw[:10]


def quote_number(quote: dict[str, Any]) -> str:
    raw_id = str(quote.get("id") or "")
    return raw_id.rsplit("-", 1)[-1].upper() or "EM ABERTO"


def wrap_text(value: Any, font: str, size: float, width: float) -> list[str]:
    words = safe_text(value, "").split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = word if current and stringWidth(candidate, font, size) > width else candidate
    if current:
        lines.append(current)
    return lines


def fit_size(value: Any, font: str, preferred: float, width: float, minimum: float = 11) -> float:
    text = safe_text(value, "")
    size = preferred
    while size > minimum and stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def company_contact(company: dict[str, Any], store: dict[str, Any]) -> str:
    phone = company.get("fiscal_phone") or company.get("phone") or store.get("whatsapp")
    email = company.get("fiscal_email") or company.get("email") or company.get("owner_email")
    location = " ".join(
        value for value in [company.get("fiscal_city"), company.get("fiscal_state")] if str(value or "").strip()
    )
    return "  |  ".join(str(value).strip() for value in [phone, email, location] if str(value or "").strip())


def draw_right(canvas: Canvas, text: str, x: float, y: float, font: str, size: float, color=INK) -> None:
    canvas.setFillColor(color)
    canvas.setFont(font, size)
    canvas.drawRightString(x, y, safe_text(text, ""))


def draw_footer(canvas: Canvas, page_number: int, colors: dict[str, HexColor]) -> None:
    canvas.setStrokeColor(colors["line"])
    canvas.line(MARGIN, 51, PAGE_WIDTH - MARGIN, 51)
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, 35, "Proposta comercial - n\u00e3o substitui documento fiscal.")
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 35, f"P\u00e1gina {page_number}")


def draw_header(canvas: Canvas, store: dict[str, Any], company: dict[str, Any], quote: dict[str, Any], page_number: int, colors: dict[str, HexColor]) -> float:
    canvas.setFillColor(colors["header"])
    canvas.rect(0, PAGE_HEIGHT - 122, PAGE_WIDTH, 122, stroke=0, fill=1)
    canvas.setFillColor(colors["accent"])
    canvas.rect(0, PAGE_HEIGHT - 6, PAGE_WIDTH, 6, stroke=0, fill=1)

    logo = company.get("logo_bytes")
    title_x = MARGIN
    if logo:
        try:
            canvas.drawImage(
                ImageReader(BytesIO(logo)),
                MARGIN,
                PAGE_HEIGHT - 112,
                width=102,
                height=102,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
            title_x += 116
        except Exception:
            pass

    company_name = company.get("trade_name") or company.get("name") or store.get("store_name") or "Sua empresa"
    contact = company_contact(company, store)
    canvas.setFillColor(white)
    # Reserve a fixed right column for the proposal number when a large logo is used.
    canvas.setFont("Helvetica-Bold", fit_size(company_name, "Helvetica-Bold", 15, 190, 10))
    canvas.drawString(title_x, PAGE_HEIGHT - 64, safe_text(company_name))
    canvas.setFillColor(colors["header_muted"])
    canvas.setFont("Helvetica", 8)
    contact_lines = company.get("pdf_header_lines") if company.get("pdf_header_lines") is not None else wrap_text(contact or "Atendimento personalizado", "Helvetica", 8, 275)[:2]
    for index, line in enumerate(contact_lines):
        canvas.setFont("Helvetica", fit_size(line, "Helvetica", 8, 275, 4))
        canvas.drawString(title_x, PAGE_HEIGHT - 83 - (index * 10), safe_text(line))

    right = PAGE_WIDTH - MARGIN
    canvas.setFillColor(colors["header_muted"])
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawRightString(right, PAGE_HEIGHT - 50, "PROPOSTA COMERCIAL")
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawRightString(right, PAGE_HEIGHT - 72, f"OR\u00c7AMENTO #{quote_number(quote)}")
    canvas.setFillColor(colors["header_muted"])
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(right, PAGE_HEIGHT - 91, f"Emitido em {format_date(quote.get('created_at'))}")
    return PAGE_HEIGHT - 151


def draw_client_card(canvas: Canvas, cart: dict[str, Any], quote: dict[str, Any], y: float, colors: dict[str, HexColor]) -> float:
    seller_lines = wrap_text("Vendedor: " + str(cart.get("seller_name") or "Não informado"), "Helvetica", 9, CONTENT_WIDTH - 40)
    card_height = 82 + len(seller_lines) * 12
    canvas.setFillColor(colors["card"])
    canvas.roundRect(MARGIN, y - card_height, CONTENT_WIDTH, card_height, 8, stroke=0, fill=1)
    canvas.setStrokeColor(colors["line"])
    canvas.roundRect(MARGIN, y - card_height, CONTENT_WIDTH, card_height, 8, stroke=1, fill=0)
    canvas.setFillColor(colors["accent"])
    canvas.roundRect(MARGIN, y - card_height, 6, card_height, 6, stroke=0, fill=1)
    third = CONTENT_WIDTH / 3
    middle_x = MARGIN + third + 15
    right_x = MARGIN + (third * 2) + 15
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(MARGIN + 20, y - 20, "CLIENTE")
    canvas.drawString(middle_x, y - 20, "WHATSAPP")
    canvas.drawString(right_x, y - 20, "VALIDADE")
    canvas.setFillColor(colors["ink"])
    client_name = safe_text(cart.get("client_name"), "Cliente nao informado")
    canvas.setFont("Helvetica-Bold", fit_size(client_name, "Helvetica-Bold", 11.5, third - 32, 9))
    canvas.drawString(MARGIN + 20, y - 39, client_name)
    canvas.setFont("Helvetica", 9.5)
    canvas.drawString(middle_x, y - 39, safe_text(cart.get("client_phone"), "Nao informado"))
    canvas.setFillColor(colors["accent"])
    canvas.setFont("Helvetica-Bold", 11.5)
    canvas.drawString(right_x, y - 39, (format_date(quote.get("valid_until")) if quote.get("valid_until") else "Condição personalizada"))
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(right_x, y - 55, "Valores sujeitos a esta validade.")
    canvas.setFillColor(colors["ink"])
    canvas.setFont("Helvetica", 9)
    for index, line in enumerate(seller_lines):
        canvas.drawString(MARGIN + 20, y - 78 - index * 12, line)
    return y - card_height - 26


def draw_table_header(canvas: Canvas, y: float, colors: dict[str, HexColor]) -> float:
    canvas.setFillColor(colors["header"])
    canvas.roundRect(MARGIN, y - 23, CONTENT_WIDTH, 30, 5, stroke=0, fill=1)
    canvas.setFillColor(colors["header_muted"])
    canvas.setFont("Helvetica-Bold", 8)
    # Baselines are deliberately below the geometric center to account for font ascent.
    label_y = y - 11
    canvas.drawString(MARGIN + 11, label_y, "PRODUTO / VARIA\u00c7\u00c3O")
    canvas.drawRightString(352, label_y, "QTD.")
    canvas.drawRightString(444, label_y, "VALOR UNIT.")
    canvas.drawRightString(PAGE_WIDTH - MARGIN - 11, label_y, "TOTAL")
    return y - 40


def draw_summary_and_totals(canvas: Canvas, cart: dict[str, Any], quote: dict[str, Any], y: float, colors: dict[str, HexColor]) -> float:
    gap = 14
    box_width = 220
    box_x = PAGE_WIDTH - MARGIN - box_width
    box_height = 101 + (17 if float(cart.get("discount") or 0) else 0) + (17 if float(cart.get("freight") or 0) else 0)
    summary_width = box_x - MARGIN - gap
    canvas.setFillColor(colors["soft"])
    canvas.roundRect(MARGIN, y - box_height, summary_width, box_height, 8, stroke=0, fill=1)
    canvas.setStrokeColor(colors["line"])
    canvas.roundRect(MARGIN, y - box_height, summary_width, box_height, 8, stroke=1, fill=0)
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(MARGIN + 16, y - 20, "RESUMO DO OR\u00c7AMENTO")
    canvas.setFillColor(colors["ink"])
    canvas.setFont("Helvetica-Bold", 12)
    count = int(cart.get("items_count") or len(cart.get("items") or []))
    canvas.drawString(MARGIN + 16, y - 43, f"{count} {'item' if count == 1 else 'itens'} nesta proposta")
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(MARGIN + 16, y - 61, f"Emiss\u00e3o: {format_date(quote.get('created_at'))}")
    canvas.drawString(MARGIN + 16, y - 77, (f"Válido até: {format_date(quote.get('valid_until'))}" if quote.get("valid_until") else "Validade: ver condições abaixo"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN + 16, y - 92, "Pagamento, frete e prazo ser\u00e3o confirmados no atendimento.")

    canvas.setFillColor(colors["total"])
    canvas.roundRect(box_x, y - box_height, box_width, box_height, 8, stroke=0, fill=1)
    canvas.setStrokeColor(colors["total_line"])
    canvas.roundRect(box_x, y - box_height, box_width, box_height, 8, stroke=1, fill=0)
    line_y = y - 22
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 9.5)
    canvas.drawString(box_x + 16, line_y, "Subtotal")
    draw_right(canvas, money(cart.get("subtotal")), box_x + box_width - 16, line_y, "Helvetica", 9.5, colors["muted"])
    if float(cart.get("discount") or 0):
        line_y -= 17
        canvas.drawString(box_x + 16, line_y, "Desconto")
        draw_right(canvas, f"-{money(cart.get('discount'))}", box_x + box_width - 16, line_y, "Helvetica", 9.5, colors["muted"])
    if float(cart.get("freight") or 0):
        line_y -= 17
        canvas.drawString(box_x + 16, line_y, "Frete")
        draw_right(canvas, money(cart.get("freight")), box_x + box_width - 16, line_y, "Helvetica", 9.5, colors["muted"])
    line_y -= 13
    canvas.setStrokeColor(colors["accent"])
    canvas.line(box_x + 16, line_y, box_x + box_width - 16, line_y)
    line_y -= 24
    canvas.setFillColor(colors["ink"])
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(box_x + 16, line_y, "TOTAL")
    draw_right(canvas, money(cart.get("total")), box_x + box_width - 16, line_y, "Helvetica-Bold", 17, colors["accent"])
    return y - box_height - 23


def draw_terms(canvas: Canvas, cart: dict[str, Any], y: float, colors: dict[str, HexColor]) -> float:
    notes = safe_text(cart.get("notes"), "")
    title = "OBSERVA\u00c7\u00d5ES" if notes else "CONDI\u00c7\u00d5ES COMERCIAIS"
    body = notes or "Valores v\u00e1lidos conforme esta proposta. A disponibilidade, o frete e a forma de pagamento ser\u00e3o alinhados pela equipe comercial."
    lines = wrap_text(body, "Helvetica", 8.5, CONTENT_WIDTH - 30)
    box_height = max(66, 38 + (len(lines) * 12))
    canvas.setFillColor(colors["soft"])
    canvas.roundRect(MARGIN, y - box_height, CONTENT_WIDTH, box_height, 8, stroke=0, fill=1)
    canvas.setStrokeColor(colors["line"])
    canvas.roundRect(MARGIN, y - box_height, CONTENT_WIDTH, box_height, 8, stroke=1, fill=0)
    canvas.setFillColor(colors["ink"])
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(MARGIN + 15, y - 20, title)
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 8.5)
    line_y = y - 39
    for line in lines:
        canvas.drawString(MARGIN + 15, line_y, line)
        line_y -= 12
    return y - box_height - 24


def build_quote_pdf(quote: dict[str, Any], store: dict[str, Any], company: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, pageCompression=1, title=f"Orcamento {quote_number(quote)}")
    cart = quote.get("cart_snapshot") or {}
    if quote.get("validity_text"):
        cart = {**cart, "notes": "Validade: " + quote["validity_text"] + (("\nLimite da promoção: " + format_date(quote["valid_until"])) if quote.get("valid_until") else "") + ("\n" + cart["notes"] if cart.get("notes") else "")}

    colors = brand_colors(company)
    page_number = 1
    y = draw_header(canvas, store, company, quote, page_number, colors)
    y = draw_client_card(canvas, cart, quote, y, colors)

    canvas.setFillColor(colors["ink"])
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(MARGIN, y, "Itens da proposta")
    canvas.setFillColor(colors["muted"])
    canvas.setFont("Helvetica", 8.5)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, y, "Valores em reais (R$)")
    y = draw_table_header(canvas, y - 15, colors)

    for item in cart.get("items") or []:
        item_name = safe_text(item.get("product_name"), "Produto ou servico")
        if item.get("finishes"):
            item_name += " - Acabamentos: " + ", ".join(item["finishes"])
        if item.get("extras"):
            item_name += " - Adicionais: " + "; ".join(f"{extra['description']} (+{money(extra['unit_price'])}/un)" for extra in item["extras"])
        if float(item.get("discount") or 0):
            item_name += f" (desconto: {money(item['discount'])})"
        variation = "  |  ".join(value for value in [item.get("sku"), item.get("size"), item.get("color")] if value)
        product_lines = wrap_text(item_name, "Helvetica-Bold", 9.5, 252)
        row_height = max(35, (len(product_lines) * 12) + (14 if variation else 0) + 10)
        if y - row_height < 224:
            draw_footer(canvas, page_number, colors)
            canvas.showPage()
            page_number += 1
            y = draw_header(canvas, store, company, quote, page_number, colors)
            canvas.setFillColor(colors["ink"])
            canvas.setFont("Helvetica-Bold", 12)
            canvas.drawString(MARGIN, y, "Itens da proposta - continua\u00e7\u00e3o")
            y = draw_table_header(canvas, y - 15, colors)
        canvas.setStrokeColor(colors["line"])
        canvas.line(MARGIN, y + 8, PAGE_WIDTH - MARGIN, y + 8)
        item_y = y - 7
        canvas.setFillColor(colors["ink"])
        for index, line in enumerate(product_lines):
            canvas.setFont("Helvetica-Bold" if index == 0 else "Helvetica", 9.5)
            canvas.drawString(MARGIN + 11, item_y - (index * 12), line)
        if variation:
            canvas.setFillColor(colors["muted"])
            canvas.setFont("Helvetica", 7.8)
            canvas.drawString(MARGIN + 11, item_y - (len(product_lines) * 12), safe_text(variation))
        draw_right(canvas, quantity(item.get("quantity")), 352, item_y, "Helvetica", 9)
        draw_right(canvas, money(item.get("unit_price")), 444, item_y, "Helvetica", 9)
        draw_right(canvas, money(item.get("total")), PAGE_WIDTH - MARGIN - 11, item_y, "Helvetica-Bold", 9.5)
        y -= row_height

    canvas.setStrokeColor(colors["line"])
    canvas.line(MARGIN, y + 7, PAGE_WIDTH - MARGIN, y + 7)
    y -= 18
    if y < 262:
        draw_footer(canvas, page_number, colors)
        canvas.showPage()
        page_number += 1
        y = draw_header(canvas, store, company, quote, page_number, colors)
    y = draw_summary_and_totals(canvas, cart, quote, y, colors)
    if y < 156:
        draw_footer(canvas, page_number, colors)
        canvas.showPage()
        page_number += 1
        y = draw_header(canvas, store, company, quote, page_number, colors)
    draw_terms(canvas, cart, y, colors)
    draw_footer(canvas, page_number, colors)
    canvas.save()
    return buffer.getvalue()
