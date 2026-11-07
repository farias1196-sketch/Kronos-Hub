import hashlib
import hmac
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

from .config import SECRET_KEY


def _signature(path: str, expires: int) -> str:
    return hmac.new(SECRET_KEY.encode(), f"public-media:{path}:{expires}".encode(), hashlib.sha256).hexdigest()


def public_image_url(url: str, tenant: str) -> str:
    parsed = urlsplit(url or "")
    path = unquote(parsed.path)
    if not parsed.netloc and path.startswith("/api/media/"):
        path = path[len("/api/media"):]
    elif parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != 18809:
        return ""
    if not path.startswith(f"/media/cache/{tenant}/") or chr(92) in path or any(part in {".", ".."} for part in path.split("/")):
        return ""
    expires = int(time.time()) + 900
    query = urlencode({"expires": expires, "asset_signature": _signature(path, expires)})
    return "/api/media" + path + "?" + query


def valid_public_asset(scope) -> bool:
    if scope["method"] != "GET" or not scope["path"].startswith("/media/cache/"):
        return False
    values = dict(parse_qsl(scope.get("query_string", b"").decode()))
    try:
        expires = int(values.get("expires", "0"))
    except ValueError:
        return False
    return int(time.time()) < expires <= int(time.time()) + 900 and hmac.compare_digest(values.get("asset_signature", ""), _signature(scope["path"], expires))
