"""Dependências FastAPI reutilizáveis para autenticação no Chronos Hub.

Uso em qualquer API:

    from chronos_auth import get_current_user, get_optional_user, AuthUser

    @app.get("/protected")
    def protected_route(user: AuthUser = Depends(get_current_user)):
        print(user.tenant_id, user.permissions)

    @app.get("/public-or-private")
    def mixed_route(user: AuthUser | None = Depends(get_optional_user)):
        if user:
            # logado
        else:
            # acesso público
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request


from .token import decode_token


@dataclass(frozen=True)
class AuthUser:
    """Dados do usuário autenticado extraídos do token JWT."""

    member_id: str
    user_id: str
    user_name: str
    tenant_id: str
    tenant_slug: str
    role: str
    permissions: list[str] = field(default_factory=list)
    kind: str = "member"

    # ---- helpers de permissão ----

    def has_permission(self, key: str) -> bool:
        return key in self.permissions

    def require_permission(self, key: str) -> None:
        """Levanta 403 se o usuário não tiver a permissão."""
        if key not in self.permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Permissão necessária: {key}",
            )

    @property
    def is_owner(self) -> bool:
        return self.role == "OWNER"

    @property
    def is_admin_or_above(self) -> bool:
        return self.role in {"OWNER", "ADMIN"}

    @property
    def is_manager_or_above(self) -> bool:
        return self.role in {"OWNER", "ADMIN", "MANAGER"}


def _extract_token(request: Request) -> str | None:
    """Extrai o token Bearer do header Authorization."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _decode_user(token: str) -> AuthUser:
    """Decodifica o token e retorna um AuthUser."""
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado. Faça login novamente.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

    return AuthUser(
        member_id=payload.get("sub", ""),
        user_id=payload.get("uid", ""),
        user_name=payload.get("name", ""),
        tenant_id=payload.get("tid", ""),
        tenant_slug=payload.get("slug", ""),
        role=payload.get("role", "VIEWER"),
        permissions=payload.get("perms", []),
        kind=payload["kind"],
    )


async def get_current_user(request: Request) -> AuthUser:
    """Dependência FastAPI que **exige** autenticação.

    Retorna ``AuthUser`` ou levanta ``HTTPException(401)``.
    """
    if getattr(request.state, "auth_user", None):
        return request.state.auth_user
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Autenticação necessária. Envie o header Authorization: Bearer <token>.",
        )
    return _decode_user(token)


async def get_optional_user(request: Request) -> AuthUser | None:
    """Dependência FastAPI que aceita acesso **com ou sem** token.

    Retorna ``None`` apenas quando nao ha credencial; tokens invalidos geram 401.
    """
    token = _extract_token(request)
    if not token:
        return None
    return _decode_user(token)
