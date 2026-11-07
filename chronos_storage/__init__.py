"""Shared durability and storage helpers for Chronos services."""

from .atomic import atomic_write_json

__all__ = [
    "atomic_write_json",
]

# Some legacy services only need atomic JSON writes and have deliberately small
# virtual environments. Keep their startup independent from asyncpg.
try:
    from .postgres import (
        check_connection,
        close_pool,
        execute_for_tenant,
        fetch_for_tenant,
        fetchrow_for_tenant,
        get_connection,
        get_pool,
        transaction,
    )
except ModuleNotFoundError as error:
    if error.name != "asyncpg":
        raise
else:
    __all__.extend([
        "get_pool",
        "close_pool",
        "get_connection",
        "transaction",
        "check_connection",
        "fetch_for_tenant",
        "fetchrow_for_tenant",
        "execute_for_tenant",
    ])
