from contextvars import ContextVar

from fastapi import HTTPException

from .middleware import AuthUser

current_user: ContextVar[AuthUser | None] = ContextVar("chronos_user", default=None)
current_token: ContextVar[str | None] = ContextVar("chronos_token", default=None)


def canonical_slug(value: str) -> str:
    return value


def storage_tenant(user: AuthUser, module: str) -> str:
    return user.tenant_slug


def scoped_tenant(value: str | None, module: str = "") -> str:
    user = current_user.get()
    if user is None:
        raise HTTPException(401, "Autenticacao necessaria")
    if value is not None and not isinstance(value, str):
        raise HTTPException(403, "Identificador de empresa invalido")
    if user.kind == "service" and user.tenant_slug == "*" and user.user_id == "adm":
        if not value:
            raise HTTPException(400, "Informe a empresa")
        return value
    if value and value not in {user.tenant_id, user.tenant_slug, storage_tenant(user, "zap")}:
        raise HTTPException(403, "Empresa diferente da sessao autenticada")
    return storage_tenant(user, module)
