"""Requisições entre as APIs desta distribuição, sem proxies ou redirecionamentos."""
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_local(request, timeout):
    url = request.full_url if isinstance(request, Request) else request
    parts = urlsplit(url)
    if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.username
            or parts.password or parts.port not in {18802, 18803, 18806, 18815}):
        raise ValueError("Destino externo à prévia.")
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)
