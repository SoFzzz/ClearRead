"""Local glossary of the words the assistant explained ("Mis palabras", AI-F05).

Stored in one JSON file under the user's data folder. Saving here never calls the
assistant again: the explanation is the one that was already shown.
"""

import json
import os
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_ENTRIES = 500


@dataclass(frozen=True)
class GlossaryEntry:
    word: str
    explanation: str
    document: str
    added_on: str  # ISO date


def _key(word: str) -> str:
    return " ".join(word.lower().split())


def _search_key(text: str) -> str:
    """Case- and accent-insensitive: typing "celula" finds the word with its accent."""
    decomposed = unicodedata.normalize("NFD", _key(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def search_entries(entries: list[GlossaryEntry], query: str) -> list[GlossaryEntry]:
    """Entries whose word or explanation contains ``query`` (all of them if it is empty)."""
    needle = _search_key(query)
    if not needle:
        return list(entries)
    return [
        e
        for e in entries
        if needle in _search_key(e.word) or needle in _search_key(e.explanation)
    ]


class GlossaryStore:
    """Newest entries first; a word explained twice keeps only its latest explanation.

    Without a path the glossary lives in memory only.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries = self._load()

    def entries(self) -> list[GlossaryEntry]:
        return list(self._entries)

    def add(self, entry: GlossaryEntry) -> None:
        kept = [e for e in self._entries if _key(e.word) != _key(entry.word)]
        self._entries = [entry, *kept][:MAX_ENTRIES]
        self._save()

    def remove(self, word: str) -> None:
        self._entries = [e for e in self._entries if _key(e.word) != _key(word)]
        self._save()

    def search(self, query: str) -> list[GlossaryEntry]:
        return search_entries(self._entries, query)

    def _load(self) -> list[GlossaryEntry]:
        if self._path is None:
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [GlossaryEntry(**item) for item in raw][:MAX_ENTRIES]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self) -> None:
        if self._path is None:
            return  # no file: the words last until the app closes
        temp: str | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump([asdict(e) for e in self._entries], file, ensure_ascii=False)
            os.replace(temp, self._path)
        except OSError:
            # Losing the write only costs the saved word, never the reading.
            if temp is not None:
                Path(temp).unlink(missing_ok=True)
