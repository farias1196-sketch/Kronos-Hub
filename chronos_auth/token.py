"""Criação e verificação de tokens JWT para o Chronos Hub."""

from __future__ import annotations

import time
from typing import Any

import jwt

from .config import SECRET_KEY, TOKEN_ALGORITHM, TOKEN_EXPIRATION_HOURS


def create_token(
    *,
    member_id: str,
    user_id: str,
    user_name: str,
    tenant_id: str,
    tenant_slug: str,
    role: str,
    permissions: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    """Gera um JWT assinado com os dados do membro autenticado."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": member_id,
        "uid": user_id,
        "name": user_name,
        "tid": tenant_id,
        "slug": tenant_slug,
        "role": role,
        "perms": permissions,
        "iat": now,
        "exp": now + TOKEN_EXPIRATION_HOURS * 3600,
        "iss": "chronos-core",
        "aud": "chronos-api",
        "kind": "member",
        "member_id": member_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "tenant_slug": tenant_slug,
        "permissions": permissions,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decodifica e valida um JWT.

    Levanta ``jwt.ExpiredSignatureError`` se expirado e
    ``jwt.InvalidTokenError`` para qualquer outro problema.
    """
    payload = jwt.decode(
        token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM],
        issuer="chronos-core", audience="chronos-api",
        options={"require": ["exp", "iat", "sub", "uid", "tid", "slug", "role", "perms", "kind"]},
    )
    if any(not isinstance(payload[key], str) or not payload[key] for key in ("sub", "uid", "tid", "slug", "role")):
        raise jwt.InvalidTokenError("Identidade incompleta")
    if not isinstance(payload["perms"], list) or any(not isinstance(p, str) for p in payload["perms"]):
        raise jwt.InvalidTokenError("Permissoes invalidas")
    if payload["kind"] not in {"member", "service"}:
        raise jwt.InvalidTokenError("Tipo de token invalido")
    return payload
