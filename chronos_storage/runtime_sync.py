"""Synchronous bridge for legacy APIs during the PostgreSQL cutover.

The first operational step keeps the existing API contracts intact while every
successful write is mirrored to the relational database.  The bridge owns an
event loop in a dedicated thread so it can safely be called from both regular
and ``async`` FastAPI handlers.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Coroutine
from typing import Any

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_ready = threading.Event()
_lock = threading.Lock()


def postgres_mode(service: str) -> str:
    """A prévia local usa exclusivamente o armazenamento SQLite."""
    return "off"


def postgres_enabled(service: str) -> bool:
    return postgres_mode(service) in {"mirror", "primary"}


def _loop_worker() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _ready.set()
    _loop.run_forever()


def run(coroutine: Coroutine[Any, Any, Any], *, timeout: float = 45) -> Any:
    """Run an async PostgreSQL operation from synchronous legacy code."""
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _ready.clear()
            _thread = threading.Thread(target=_loop_worker, name="chronos-postgres-runtime", daemon=True)
            _thread.start()
            if not _ready.wait(5):
                raise RuntimeError("Nao foi possivel iniciar o executor PostgreSQL.")
    if _loop is None:
        raise RuntimeError("Executor PostgreSQL indisponivel.")
    return asyncio.run_coroutine_threadsafe(coroutine, _loop).result(timeout=timeout)
