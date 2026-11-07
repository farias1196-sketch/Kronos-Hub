import hashlib
import hmac

from .config import SECRET_KEY
from .middleware import AuthUser
from .scope import canonical_slug


def webhook_headers(provider: str, tenant: str) -> dict[str, str]:
    slug = canonical_slug(tenant)
    signature = hmac.new(SECRET_KEY.encode(), f"webhook:{provider}:{slug}".encode(), hashlib.sha256).hexdigest()
    return {"X-Chronos-Webhook-Tenant": slug, "X-Chronos-Webhook": signature}


def bridge_headers() -> dict[str, str]:
    signature = hmac.new(SECRET_KEY.encode(), b"bridge:baileys", hashlib.sha256).hexdigest()
    return {"X-Chronos-Bridge": signature}


def webhook_user(request, module: str, path: str):
    provider = "baileys" if module == "zap" and path in {"/webhooks/baileys/messages", "/webhooks/baileys/connection", "/chat/messages/last-received"} else "evolution" if module == "sync" and path.startswith("/webhooks/evolution/") else None
    slug = request.headers.get("x-chronos-webhook-tenant", "")
    if provider and slug and slug != "*":
        expected = webhook_headers(provider, slug)["X-Chronos-Webhook"]
        if hmac.compare_digest(request.headers.get("x-chronos-webhook", ""), expected):
            return AuthUser(provider, provider, provider, slug, slug, "SERVICE", [], "service")
    return None
