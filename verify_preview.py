"""Verifica os fluxos HTTP em uma cópia temporária dos fontes, sem abrir portas."""
from pathlib import Path
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def expect(response, status):
    if response.status_code != status:
        raise AssertionError(f"{response.request.method} {response.request.url.path}: "
                             f"esperado {status}, recebido {response.status_code}, detalhe {response.json().get('detail')}")
    return response


def exercise():
    from fastapi.testclient import TestClient
    from init_preview import initialize_env, create_demo
    from preview_config import require_secret
    initialize_env()
    create_demo()
    from Chronos_ADM.adm_api.main import app as adm
    from Chronos_Core.core_api.app.main import app as core
    from Chronos_nexus.nexus_api.app.main import app as nexus

    identity = {"tenant_slug": "demo", "email": "demo@example.invalid"}
    with TestClient(adm) as a, TestClient(core) as c, TestClient(nexus) as n:
        for api in (a, c, n):
            expect(api.get("/health"), 200)
        expect(a.post("/auth/dev-reset", json={}), 404)
        expect(a.post("/auth/setup", json={}), 404)
        expect(a.get("/companies"), 401)
        expect(a.post("/auth/login", json={"username":"admin-local","password":"incorrect"}), 401)
        adm_token = expect(a.post("/auth/login", json={"username":"admin-local",
                           "password":require_secret("PREVIEW_INITIAL_ADMIN_PASSWORD")}), 200).json()["access_token"]
        expect(a.get("/companies", headers={"Authorization":f"Bearer {adm_token}"}), 200)
        import jwt
        adm_secret = require_secret("PREVIEW_ADM_SECRET")
        for payload, secret in [
            ({"sub":"admin-local"}, adm_secret),
            ({"sub":"admin-local", "exp":1}, adm_secret),
            ({"sub":"admin-local", "exp":4102444800}, require_secret("PREVIEW_SSO_SECRET")),
        ]:
            invalid = jwt.encode(payload, secret, algorithm="HS256")
            expect(a.get("/companies", headers={"Authorization":f"Bearer {invalid}"}), 401)
        print("ADM: login, recurso protegido, validade e assinatura do token.")
        initial = require_secret("PREVIEW_DEMO_PASSWORD")
        reply = expect(c.post("/core/auth/login", json={**identity,"password":initial}), 200).json()
        assert reply["mustChangePassword"] and not reply.get("token")
        new_password = secrets.token_urlsafe(30)
        expect(c.post("/core/auth/change-first-password", json={**identity,
                      "current_password":initial,"new_password":new_password}), 200)
        token = expect(c.post("/core/auth/login", json={**identity,"password":new_password}), 200).json()["token"]
        auth = {"Authorization":f"Bearer {token}"}
        expect(c.get("/core/auth/me", headers=auth), 200)
        print("Core: troca inicial, login e sessão.")
        route = "/nexus/clients"
        expect(n.get(route,params={"empresa_id":"demo"}),401)
        expect(n.get(route,params={"empresa_id":"outra"},headers=auth),403)
        expect(n.post(route,params={"empresa_id":"demo"},headers=auth,
                      json={"name":"Cliente Fictício","phone":"00000000000"}),200)
        clients = expect(n.get(route,params={"empresa_id":"demo"},headers=auth),200).json()["clients"]
        assert any(row["name"] == "Cliente Fictício" for row in clients)
        expect(a.get("/companies", headers=auth),401)
        print("Nexus: cliente persistido, acesso anônimo e acesso entre empresas bloqueados.")

        from Chronos_stock.stock_api.app.main import app as stock
        from Chronos_loja.loja_api.app.main import app as loja
        from Chronos_agenda.Agenda_api.app.main import app as agenda
        with TestClient(stock) as s, TestClient(loja) as shop, TestClient(agenda) as ag:
            for service, endpoint in [(s, "/stock/items"), (shop, "/shop/config"), (ag, "/agenda/services")]:
                expect(service.get("/health"), 200)
                expect(service.get(endpoint), 401)
                expect(service.get(endpoint, params={"tenant_id":"outra"}, headers=auth), 403)
                expect(service.get(endpoint, headers=auth), 200)
            expect(s.post("/stock/items", json={"kind":"sale", "name":"Item de teste"}, headers=auth), 200)
            listed = expect(s.get("/stock/items", headers=auth), 200).json()
            assert any(item["name"] == "Item de teste" for item in listed["items"])
            assert not expect(ag.get("/agenda/appointments", headers=auth), 200).json()["appointments"]
            from preview_http import open_local
            try:
                open_local("https://example.invalid/logo", timeout=1)
            except ValueError:
                pass
            else:
                raise AssertionError("Destino externo aceito")
            print("Estoque, Loja e Agenda: autorização, separação entre empresas e persistência do item.")

        import base64
        from importlib import import_module
        media_app = import_module("Chronos Media.media_api.app.main")
        with TestClient(media_app.app) as media:
            file = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
            params = {"tenant_id":"demo", "client_id":".."}
            expect(media.post("/media/upload", data=params, files={"file":("x.png",b"<html>", "image/png")}, headers=auth),415)
            result = expect(media.post("/media/upload", data=params, files={"file":("pixel.png", file,"image/png")}, headers=auth),200).json()["media"]
            expect(media.get(result["cache_url"]),401)
            expect(media.get(result["cache_url"], headers=auth),200)
            expect(media.get(result["download_url"], params={"tenant_id":"outra"}, headers=auth),403)
            from chronos_auth.assets import public_image_url
            signed = public_image_url("/api/media" + result["cache_url"], "demo")
            expect(media.get(signed.removeprefix("/api/media")),200)
            expect(media.delete("/media/items/"+result["id"], headers=auth),200)
            expect(media.get(result["cache_url"], headers=auth),404)
        print("Media: upload, assinatura, isolamento, rejeição de HTML e remoção da imagem.")


def main():
    # Copiar somente os fontes executáveis desta distribuição, nunca .env ou dados.
    with tempfile.TemporaryDirectory(prefix="chronos-verify-") as directory:
        sandbox = Path(directory)
        for folder in ("chronos_auth", "chronos_storage", "Chronos_ADM", "Chronos_Core", "Chronos_nexus", "Chronos_stock", "Chronos_loja", "Chronos_agenda", "Chronos Media"):
            for source in (ROOT / folder).rglob("*.py"):
                target = sandbox / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for name in ("preview_config.py", "init_preview.py", "verify_preview.py", "preview_http.py"):
            shutil.copyfile(ROOT / name, sandbox / name)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        subprocess.run([sys.executable,"-B",str(sandbox / "verify_preview.py"),"--isolated"],
                       cwd=sandbox, env=env, check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--isolated"] and ROOT.parent == Path(tempfile.gettempdir()).resolve() and ROOT.name.startswith("chronos-verify-"):
        with patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("HTTP externo")), patch("httpx.AsyncHTTPTransport.handle_async_request", side_effect=AssertionError("HTTP externo")), patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP externo")):
            exercise()
    else:
        main()
