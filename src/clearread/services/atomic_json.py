"""Atomic file writes: a crash in the middle never leaves a half-written file."""

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any


def write_json_atomic(
    target: Path, payload: object, indent: int | None = None, durable: bool = False
) -> None:
    """Write next to ``target`` and swap it in; raises ``OSError`` if the disk refuses.

    ``durable`` also forces the bytes to disk before the swap, for files that must
    survive a power cut (the settings).
    """

    def dump(file: IO[Any]) -> None:
        json.dump(payload, file, indent=indent, ensure_ascii=False)

    _write_atomic(target, "w", dump, durable)


def write_bytes_atomic(target: Path, data: bytes) -> None:
    """Same guarantees as ``write_json_atomic`` for binary files (the session)."""
    _write_atomic(target, "wb", lambda file: file.write(data), durable=True)


def _write_atomic(
    target: Path, mode: str, write: Callable[[IO[Any]], object], durable: bool
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        encoding = None if "b" in mode else "utf-8"
        with os.fdopen(fd, mode, encoding=encoding) as file:
            write(file)
            if durable:
                file.flush()
                os.fsync(file.fileno())
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
