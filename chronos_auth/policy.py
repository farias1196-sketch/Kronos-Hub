import re

from fastapi import HTTPException

PUBLIC = {
    "core": [("POST", r"/core/auth/(login|select-tenant|change-first-password)"), ("GET", r"/core/auth/tenant-options"), ("GET", r"/core/assets/[^/]+/logo\.png")],
    "loja": [
        ("GET", r"/public/[^/]+/(catalog|product/[^/]+)"),
        ("POST", r"/public/[^/]+/carts"),
        ("GET", r"/public/[^/]+/carts/[^/]+"),
        ("POST", r"/public/[^/]+/carts/[^/]+/items"),
        ("PATCH", r"/public/[^/]+/carts/[^/]+/items/[^/]+"),
        ("DELETE", r"/public/[^/]+/carts/[^/]+/items/[^/]+"),
        ("POST", r"/public/[^/]+/checkout"),
    ],
    "agenda": [("GET", r"/public/[^/]+/(agenda|slots|agenda/availability)"), ("POST", r"/public/[^/]+/agenda/book")],
    "nexus": [("GET", r"/nexus/(public-registration|public/register)/[^/]+"), ("POST", r"/nexus/(public-registration|public/register)/[^/]+")],
    "pay": [("GET", r"/pay/providers/mercado-pago/callback"), ("POST", r"/pay/webhooks/mercado-pago")],
    "log": [("GET", r"/log/providers/melhor-envio/callback")],
}


def is_public(module, method, path):
    return (method == "GET" and path == "/health") or any(
        method == verb and re.fullmatch(pattern, path) for verb, pattern in PUBLIC.get(module, [])
    )


def authorize(user, module, method, path):
    if user.kind == "service":
        if user.user_id == "adm":
            return
        allowed = {
            "sync": [("zap", "POST", r"/chat/import/evolution-(messages|conversations)"), ("zap", "POST", r"/webhooks/baileys/messages")],
            "baileys": [("zap", "POST", r"/webhooks/baileys/(messages|connection)"), ("zap", "GET", r"/chat/messages/last-received")],
            "evolution": [("sync", "POST", r"/webhooks/evolution/[^/]+")],
            "zap": [("nexus", "POST", r"/nexus/pre-register")],
            "loja": [
                ("stock", "GET", r"/stock/items"),
                ("nexus", "POST", r"/nexus/clients"),
                ("core", "GET", r"/core/tenants/[^/]+"),
                ("core", "GET", r"/core/assets/[^/]+/logo\.png"),
            ],
            "agenda": [("stock", "GET", r"/stock/service-resources")],
        }
        if any(module == mod and method == verb and re.fullmatch(pattern, path) for mod, verb, pattern in allowed.get(user.user_id, [])):
            return
        raise HTTPException(403, "Servico sem permissao para esta rota")
    if path.startswith(("/webhooks/", "/chat/import/evolution-")) or path in {"/core/summary", "/core/import/old-reports", "/core/modules/enable-all", "/media-cache/cleanup", "/drive/auth-url", "/drive/oauth2callback"}:
        raise HTTPException(403, "Operacao exclusiva do ADM ou servico interno")
    if module == "core":
        if path.startswith("/core/auth/"):
            return
        permission = "core.company.view"
        if "/members" in path:
            permission = "core.members.view" if method == "GET" else "core.members.manage"
        elif "/audit" in path:
            permission = "core.audit.view"
        elif "/billing" in path:
            permission = "core.packages.manage"
        elif path == "/core/modules":
            permission = "core.modules.view"
        elif method != "GET":
            permission = "core.company.manage"
    elif module == "zap":
        permission = "zap.chat.view" if method == "GET" else "zap.chat.reply"
        if "/quick-replies" in path and method != "GET":
            permission = "zap.templates.manage"
        elif path == "/whatsapp/status" or path.startswith(("/chat/import", "/chat/migration", "/chat/sync", "/whatsapp/connect", "/whatsapp/disconnect", "/whatsapp/reset")):
            permission = "zap.connections.manage"
    elif module == "hera":
        permission = "hera.settings.view" if method == "GET" else "hera.transcription.use"
        if "/settings" in path and method != "GET":
            permission = "hera.settings.manage"
        elif "/logs" in path:
            permission = "hera.logs.view"
        elif "/training" in path and method == "PATCH":
            permission = "hera.settings.manage"
    else:
        permission = {"stock": "stock.products.manage", "nexus": "nexus.clients.manage", "loja": "loja.store.manage", "agenda": "agenda.events.manage", "promo": "promo.editor.manage", "pay": "pay.charges.manage", "log": "log.shipping.manage", "media": "media.files.manage", "sync": "zap.connections.manage"}[module]
    user.require_permission(permission)
