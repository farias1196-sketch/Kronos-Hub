import time
from urllib.parse import urlsplit

from .scope import canonical_slug, current_token, current_user
from .token import create_token


def service_headers(service: str, tenant: str = "*") -> dict[str, str]:
    slug = canonical_slug(tenant)
    token = create_token(
        member_id=service, user_id=service, user_name=service,
        tenant_id=slug, tenant_slug=slug, role="SERVICE", permissions=[],
        extra={"kind": "service", "exp": int(time.time()) + 300},
    )
    return {"Authorization": f"Bearer {token}"}


def forwarding_headers(url: str) -> dict[str, str]:
    # Never forward a user's credential to an external integration (e.g. Ollama).
    parsed = urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.scheme != "http" or parsed.port not in {18802, 18803, 18806, 18807, 18815}:
        return {}
    token = current_token.get()
    return {"Authorization": f"Bearer {token}"} if token and current_user.get() else {}
