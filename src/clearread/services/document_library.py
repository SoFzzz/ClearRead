"""Processed-document cache and recent-documents list (HOME-F01).

The cache holds the text of personal documents, so it lives only under the
user's %APPDATA% folder (see ``clearread.core.paths.get_user_data_dir``).
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from clearread.services.text_formatter import (
    FORMATTER_VERSION,
    FormattedDocument,
    WordToken,
)

MAX_RECENTS = 10
_HASH_CHUNK_BYTES = 1024 * 1024
_INDEX_FILE = "recents.json"


@dataclass(frozen=True)
class RecentDocument:
    key: str
    name: str
    path: str
    opened_at: str  # ISO 8601
    pages: int
    is_photo: bool


@dataclass(frozen=True)
class CachedDocument:
    raw_text: str
    formatted: FormattedDocument
    appearance: str  # theme, typography and syllable switch the html was generated for


def compute_cache_key(path: Path) -> str:
    """Hash of the file contents plus the formatter version."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return f"{digest.hexdigest()}-f{FORMATTER_VERSION}"


class DocumentLibrary:
    def __init__(
        self, root: Path, clock: Callable[[], datetime] = datetime.now
    ) -> None:
        self._root = root
        self._clock = clock
        self._root.mkdir(parents=True, exist_ok=True)

    def has(self, key: str) -> bool:
        return self._cache_path(key).is_file()

    def store(
        self,
        key: str,
        source: Path,
        cached: CachedDocument,
        pages: int,
        is_photo: bool,
    ) -> None:
        formatted = cached.formatted
        payload = {
            "raw_text": cached.raw_text,
            "appearance": cached.appearance,
            "html_content": formatted.html_content,
            "tts_script": formatted.tts_script,
            "tokens": [asdict(token) for token in formatted.token_map],
        }
        self._write_json(self._cache_path(key), payload)
        entry = RecentDocument(
            key=key,
            name=source.name,
            path=str(source),
            opened_at=self._clock().isoformat(timespec="seconds"),
            pages=pages,
            is_photo=is_photo,
        )
        self._save_index([entry, *(r for r in self.recents() if r.key != key)])

    def touch(self, key: str) -> None:
        """Move an already cached document to the top of the recent list."""
        stamp = self._clock().isoformat(timespec="seconds")
        entries = self.recents()
        for index, entry in enumerate(entries):
            if entry.key == key:
                moved = RecentDocument(**{**asdict(entry), "opened_at": stamp})
                entries.pop(index)
                self._save_index([moved, *entries])
                return

    def load(self, key: str) -> CachedDocument | None:
        try:
            data = json.loads(self._cache_path(key).read_text(encoding="utf-8"))
            formatted = FormattedDocument(
                html_content=data["html_content"],
                token_map=[WordToken(**token) for token in data["tokens"]],
                tts_script=data["tts_script"],
            )
            return CachedDocument(
                data["raw_text"], formatted, data.get("appearance", "")
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def recents(self) -> list[RecentDocument]:
        try:
            raw = json.loads((self._root / _INDEX_FILE).read_text(encoding="utf-8"))
            entries = [RecentDocument(**item) for item in raw]
        except (OSError, ValueError, TypeError):
            return []
        return [entry for entry in entries if self.has(entry.key)]

    def remove(self, key: str) -> None:
        self._save_index([r for r in self.recents() if r.key != key])
        self._cache_path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        """Delete every cached document and the recent list."""
        for path in self._root.iterdir():
            if path.suffix in (".json", ".tmp"):
                path.unlink(missing_ok=True)

    def _cache_path(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def _save_index(self, entries: list[RecentDocument]) -> None:
        kept = entries[:MAX_RECENTS]
        for dropped in entries[MAX_RECENTS:]:
            self._cache_path(dropped.key).unlink(missing_ok=True)
        self._write_json(self._root / _INDEX_FILE, [asdict(entry) for entry in kept])

    def _write_json(self, target: Path, payload: object) -> None:
        fd, temp = tempfile.mkstemp(dir=str(self._root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False)
            os.replace(temp, target)
        except OSError:
            Path(temp).unlink(missing_ok=True)
            raise
