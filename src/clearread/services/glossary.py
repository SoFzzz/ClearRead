"""Local glossary of the words the assistant explained ("Mis palabras", AI-F05).

Stored in one JSON file under the user's data folder. Saving here never calls the
assistant again: the explanation is the one that was already shown.
"""

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from clearread.services.atomic_json import write_json_atomic
from clearread.services.groups import FILTER_ALL, NO_GROUP
from clearread.services.text_search import search_key

MAX_ENTRIES = 500


@dataclass(frozen=True)
class GlossaryEntry:
    word: str
    explanation: str
    document: str
    added_on: str  # ISO date
    topic: str = NO_GROUP  # id of a topic from the topic store


def _key(word: str) -> str:
    return " ".join(word.lower().split())


def filter_entries(
    entries: list[GlossaryEntry], topic: str = FILTER_ALL, query: str = ""
) -> list[GlossaryEntry]:
    """Entries of one topic (all of them, or none-topic ones) whose text contains ``query``."""
    in_topic = [e for e in entries if topic == FILTER_ALL or e.topic == topic]
    return search_entries(in_topic, query)


def search_entries(entries: list[GlossaryEntry], query: str) -> list[GlossaryEntry]:
    """Entries whose word or explanation contains ``query`` (all of them if it is empty)."""
    needle = search_key(query)
    if not needle:
        return list(entries)
    return [
        e
        for e in entries
        if needle in search_key(e.word) or needle in search_key(e.explanation)
    ]


def count_by_topic(entries: list[GlossaryEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.topic] = counts.get(entry.topic, 0) + 1
    return counts


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
        """A repeated word keeps the topic it already had."""
        previous = next(
            (e for e in self._entries if _key(e.word) == _key(entry.word)), None
        )
        if previous is not None and previous.topic:
            entry = replace(entry, topic=previous.topic)
        kept = [e for e in self._entries if _key(e.word) != _key(entry.word)]
        self._entries = [entry, *kept][:MAX_ENTRIES]
        self._save()

    def replace_all(self, entries: list[GlossaryEntry]) -> None:
        """Swap the whole list (a profile pulled from the account), newest first."""
        self._entries = list(entries)[:MAX_ENTRIES]
        self._save()

    def set_topic(self, word: str, topic: str) -> None:
        self._entries = [
            replace(e, topic=topic) if _key(e.word) == _key(word) else e
            for e in self._entries
        ]
        self._save()

    def clear_topic(self, topic: str) -> None:
        """Words of a deleted topic go back to "no topic"; none is deleted."""
        self._entries = [
            replace(e, topic=NO_GROUP) if e.topic == topic else e for e in self._entries
        ]
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
            known = {f.name for f in fields(GlossaryEntry)}
            entries = [
                GlossaryEntry(**{k: v for k, v in item.items() if k in known})
                for item in raw
            ]
            return entries[:MAX_ENTRIES]
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
        ):  # a missing or damaged file starts an empty list
            return []

    def _save(self) -> None:
        if self._path is None:
            return  # no file: the words last until the app closes
        try:
            write_json_atomic(self._path, [asdict(e) for e in self._entries])
        except OSError:
            pass  # losing the write only costs the saved word, never the reading
