"""
Chronos Hub 2.0 - Pool Assíncrono e Conector PostgreSQL (asyncpg)
Gerenciamento de conexões assíncronas com pool, suporte nativo a JSONB,
codificação UTF-8 e escopo multi-tenant seguro.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from fastapi import HTTPException
import asyncpg


# Esta prévia executa o armazenamento SQLite do Hub.
_POOL: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Configura tipos e convenções compartilhadas por conexão do pool."""
    await conn.execute("SET TIME ZONE 'UTC'")
    # Configura o codec JSONB para conversão automática de/para dict/list Python
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool() -> asyncpg.Pool:
    raise HTTPException(503, "Este recurso exige PostgreSQL e está desligado nesta distribuição local.")


async def close_pool() -> None:
    """Fecha o pool graciosamente no shutdown da aplicação."""
    global _POOL
    if _POOL is not None and not _POOL._closed:
        await _POOL.close()
        _POOL = None


async def check_connection() -> dict[str, str]:
    """Confirma que o pool alcança PostgreSQL sem expor a DSN."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT current_database() AS database, current_setting('server_encoding') AS encoding"
        )
    return {"database": str(row["database"]), "encoding": str(row["encoding"])}


@asynccontextmanager
async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    """Context manager para adquirir e devolver uma conexão do pool."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        yield connection


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """Context manager para executar blocos atômicos com transação (BEGIN / COMMIT / ROLLBACK)."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            yield connection


# ==============================================================================
# HELPERS DE CONSULTA ASSÍNCRONA COM ESCOPO MULTI-TENANT
# ==============================================================================

async def fetch_for_tenant(
    query: str,
    tenant_id: str,
    *args: Any,
) -> list[asyncpg.Record]:
    """Executa SELECT garantindo o tenant_id como primeiro parâmetro obrigatório."""
    async with get_connection() as conn:
        return await conn.fetch(query, tenant_id, *args)


async def fetchrow_for_tenant(
    query: str,
    tenant_id: str,
    *args: Any,
) -> asyncpg.Record | None:
    """Executa SELECT de linha única garantindo o tenant_id."""
    async with get_connection() as conn:
        return await conn.fetchrow(query, tenant_id, *args)


async def execute_for_tenant(
    query: str,
    tenant_id: str,
    *args: Any,
) -> str:
    """Executa INSERT/UPDATE/DELETE garantindo o tenant_id."""
    async with get_connection() as conn:
        return await conn.execute(query, tenant_id, *args)
