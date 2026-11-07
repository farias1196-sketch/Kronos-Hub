import json
from urllib.parse import parse_qsl, urlencode

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse
from starlette.routing import Match

from .middleware import get_current_user
from .policy import authorize, is_public
from .scope import current_token, current_user, scoped_tenant, storage_tenant
from .webhooks import webhook_user
from .assets import valid_public_asset

TENANT_KEYS = {"tenant_id", "empresa_id", "tenant_slug", "current_slug"}


class SSOAuthentication:
    def __init__(self, app, owner, module):
        self.app, self.owner, self.module = app, owner, module

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        path, method = scope["path"].rstrip("/") or "/", scope["method"]
        if is_public(self.module, method, path) or (self.module == "media" and valid_public_asset(scope)):
            return await self.app(scope, receive, send)
        user_reset = token_reset = None
        try:
            request = Request(scope, receive)
            user = webhook_user(request, self.module, path) or await get_current_user(request)
            authorize(user, self.module, method, path)
            user_reset = current_user.set(user)
            token_reset = current_token.set(request.headers.get("authorization", " ").split(" ", 1)[-1] or None)
            scope.setdefault("state", {})["auth_user"] = user
            route_params = {}
            for route in self.owner.routes:
                match, child = route.matches(scope)
                if match == Match.FULL:
                    route_params = child.get("path_params", {})
                    break
            for key, value in route_params.items():
                if key in TENANT_KEYS or (self.module == "core" and key == "slug"):
                    scoped_tenant(value, self.module)
            guard = getattr(self.owner.state, "sso_resource_guard", None)
            if guard:
                import inspect
                guarded = guard(user, path, route_params)
                if inspect.isawaitable(guarded):
                    await guarded
            pairs = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)
            for key, value in pairs:
                if key in TENANT_KEYS:
                    scoped_tenant(value, self.module)
            global_admin = user.kind == "service" and user.user_id == "adm" and user.tenant_slug == "*"
            if not global_admin:
                pairs = [(k, v) for k, v in pairs if k not in TENANT_KEYS]
                pairs.extend((key, storage_tenant(user, self.module) if key in {"tenant_id", "empresa_id"} else user.tenant_slug) for key in TENANT_KEYS)
                scope["query_string"] = urlencode(pairs).encode()
            content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if method in {"POST", "PUT", "PATCH", "DELETE"} and (not content_type or content_type == "application/json" or content_type.endswith("+json")):
                raw = await request.body()
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    raise HTTPException(400, "JSON invalido")
                if isinstance(body, dict) and not global_admin:
                    for key in TENANT_KEYS & body.keys():
                        scoped_tenant(body[key], self.module)
                    if not path.startswith("/core/auth/"):
                        body.update(tenant_id=storage_tenant(user, self.module), empresa_id=storage_tenant(user, self.module))
                    raw = json.dumps(body).encode()
                async def replay():
                    nonlocal raw
                    if raw is not None:
                        data, raw = raw, None
                        return {"type": "http.request", "body": data, "more_body": False}
                    return await receive()
                scope["headers"] = [(k, v) for k, v in scope["headers"] if k != b"content-length"]
                return await self.app(scope, replay, send)
            return await self.app(scope, receive, send)
        except HTTPException as error:
            headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
            await JSONResponse({"detail": error.detail}, status_code=error.status_code, headers=headers)(scope, receive, send)
        finally:
            if token_reset is not None:
                current_token.reset(token_reset)
            if user_reset is not None:
                current_user.reset(user_reset)


def install_sso(app, module):
    # Install before CORS so authentication failures also receive CORS headers.
    app.add_middleware(SSOAuthentication, owner=app, module=module)
