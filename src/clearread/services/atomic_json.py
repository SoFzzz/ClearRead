"""Atomic JSON writes: a crash in the middle never leaves a half-written file."""

import json
import os
import tempfile
from pathlib import Path


def write_json_atomic(
    target: Path, payload: object, indent: int | None = None, durable: bool = False
) -> None:
    """Write next to ``target`` and swap it in; raises ``OSError`` if the disk refuses.

    ``durable`` also forces the bytes to disk before the swap, for files that must
    survive a power cut (the settings).
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=indent, ensure_ascii=False)
            if durable:
                file.flush()
                os.fsync(file.fileno())
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
