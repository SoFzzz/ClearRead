"""Processed-document cache and the library index (HOME-F01).

The cache holds the text of personal documents, so it lives only under the
user's %APPDATA% folder (see ``clearread.core.paths.get_user_data_dir``).

The index lists every document the person added, newest opened first. An entry stays in
it even when its cache file is missing or was made by an older formatter: the document is
then processed again from its original path. Entries are matched by ``doc_id`` (the
content hash without the formatter version) so folder and position survive that.
"""

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

from clearread.services.atomic_json import write_json_atomic
from clearread.services.text_formatter import (
    FORMATTER_VERSION,
    FormattedDocument,
    WordToken,
)

MAX_DOCUMENTS = 200  # safety cap; the oldest opened document is dropped beyond it
_HASH_CHUNK_BYTES = 1024 * 1024
_INDEX_FILE = "recents.json"
_VERSION_SUFFIX = re.compile(r"-f(\d+)$")


@dataclass(frozen=True)
class RecentDocument:
    key: str
    name: str
    path: str
    opened_at: str  # ISO 8601
    pages: int
    is_photo: bool
    position: int = 0  # index of the last word read (READ-F01)
    total_words: int = 0
    folder_id: str = ""  # "" means no folder

    @property
    def doc_id(self) -> str:
        return doc_id_of(self.key)

    @property
    def progress_percent(self) -> int:
        if self.total_words <= 0:
            return 0
        return min(100, round(100 * (self.position + 1) / self.total_words))

    @property
    def can_resume(self) -> bool:
        return 0 < self.position < self.total_words - 1


@dataclass(frozen=True)
class CachedDocument:
    raw_text: str
    formatted: FormattedDocument
    appearance: str  # theme, typography and syllable switch the html was generated for


def doc_id_of(key: str) -> str:
    """The cache key without its formatter version: stable when the formatter changes."""
    return _VERSION_SUFFIX.sub("", key)


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

    def needs_processing(self, key: str) -> bool:
        """True when the cache of ``key`` is missing or made by another formatter version."""
        entry = self.recent(key)
        stored = entry.key if entry else key
        match = _VERSION_SUFFIX.search(stored)
        outdated = match is not None and match.group(1) != str(FORMATTER_VERSION)
        return outdated or not self.has(stored)

    def store(
        self,
        key: str,
        source: Path,
        cached: CachedDocument,
        pages: int,
        is_photo: bool,
        display_name: str | None = None,
        folder_id: str = "",
    ) -> None:
        """Save the cache and put the document first; an existing entry keeps its folder."""
        formatted = cached.formatted
        payload = {
            "raw_text": cached.raw_text,
            "appearance": cached.appearance,
            "html_content": formatted.html_content,
            "tts_script": formatted.tts_script,
            "tokens": [asdict(token) for token in formatted.token_map],
            "page_starts": list(formatted.page_starts),
        }
        write_json_atomic(self._cache_path(key), payload)
        before = self.recent(key)
        total_words = len(formatted.token_map)
        same_words = before is not None and before.total_words == total_words
        entry = RecentDocument(
            key=key,
            name=display_name or source.name,
            path=str(source),
            opened_at=self._clock().isoformat(timespec="seconds"),
            pages=pages,
            is_photo=is_photo,
            position=before.position if before and same_words else 0,
            total_words=total_words,
            folder_id=before.folder_id if before else folder_id,
        )
        if before is not None and before.key != key:
            self._cache_path(before.key).unlink(missing_ok=True)
        others = [r for r in self.recents() if r.doc_id != entry.doc_id]
        self._save_index([entry, *others])

    def recent(self, key: str) -> RecentDocument | None:
        wanted = doc_id_of(key)
        return next((r for r in self.recents() if r.doc_id == wanted), None)

    def set_position(self, key: str, position: int) -> None:
        """Remember the last word read; the order of the list does not change."""
        self._update(key, position=position)

    def set_folder(self, key: str, folder_id: str) -> None:
        self._update(key, folder_id=folder_id)

    def clear_folder(self, folder_id: str) -> None:
        """Documents of a deleted folder go back to "no folder"; none is deleted."""
        entries = self.recents()
        if any(e.folder_id == folder_id for e in entries):
            self._save_index(
                [
                    RecentDocument(**{**asdict(e), "folder_id": ""})
                    if e.folder_id == folder_id
                    else e
                    for e in entries
                ]
            )

    def touch(self, key: str) -> None:
        """Move a document to the top of the list."""
        wanted = doc_id_of(key)
        entries = self.recents()
        for index, entry in enumerate(entries):
            if entry.doc_id == wanted:
                stamp = self._clock().isoformat(timespec="seconds")
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
                page_starts=tuple(data.get("page_starts", (0,))),
            )
            return CachedDocument(
                data["raw_text"], formatted, data.get("appearance", "")
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def recents(self) -> list[RecentDocument]:
        """Every document of the library, newest opened first."""
        known = {f.name for f in fields(RecentDocument)}
        try:
            raw = json.loads((self._root / _INDEX_FILE).read_text(encoding="utf-8"))
            return [
                RecentDocument(**{k: v for k, v in item.items() if k in known})
                for item in raw
            ]
        except (OSError, ValueError, TypeError, AttributeError):
            return []

    def remove(self, key: str) -> None:
        """Forget the document and delete its cached copy; the original file is untouched."""
        entry = self.recent(key)
        if entry is not None:
            self._cache_path(entry.key).unlink(missing_ok=True)
        wanted = doc_id_of(key)
        self._save_index([r for r in self.recents() if r.doc_id != wanted])
        self._cache_path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        """Delete every cached document and the library index."""
        for path in self._root.iterdir():
            if path.suffix in (".json", ".tmp"):
                path.unlink(missing_ok=True)

    def _update(self, key: str, **changes: object) -> None:
        wanted = doc_id_of(key)
        entries = self.recents()
        for index, entry in enumerate(entries):
            if entry.doc_id == wanted:
                changed = RecentDocument(**{**asdict(entry), **changes})
                if changed != entry:
                    entries[index] = changed
                    self._save_index(entries)
                return

    def _cache_path(self, key: str) -> Path:
        return self._root / f"{key}.json"

    def _save_index(self, entries: list[RecentDocument]) -> None:
        kept = entries[:MAX_DOCUMENTS]
        for dropped in entries[MAX_DOCUMENTS:]:
            self._cache_path(dropped.key).unlink(missing_ok=True)
        write_json_atomic(self._root / _INDEX_FILE, [asdict(e) for e in kept])
