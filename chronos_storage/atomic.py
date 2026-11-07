from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def _exclusive_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Acquire a small cross-process lock next to a data file."""
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Arquivo ocupado por mais de {timeout_seconds:.0f}s: {path.name}")
                time.sleep(0.05)

        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """Persist JSON without exposing partial files or concurrent overwrites."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(path):
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temp_name = temporary.name
                json.dump(data, temporary, ensure_ascii=False, indent=indent)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temp_name, path)
            temp_name = None
        finally:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)
