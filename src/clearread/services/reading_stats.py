"""Reading statistics kept on this computer only (HOME-F02): words read and time spent."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from clearread.services.atomic_json import write_json_atomic


@dataclass(frozen=True)
class ReadingStats:
    words_read: int = 0
    seconds_read: int = 0


class StatsStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._stats = self._load()

    @property
    def stats(self) -> ReadingStats:
        return self._stats

    def add(self, words: int, seconds: float) -> None:
        if words <= 0 and seconds < 1:
            return
        self._stats = ReadingStats(
            self._stats.words_read + max(words, 0),
            self._stats.seconds_read + max(round(seconds), 0),
        )
        self._save()

    def reset(self) -> None:
        self._stats = ReadingStats()
        self._save()

    def _load(self) -> ReadingStats:
        if self._path is None:
            return ReadingStats()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            words, seconds = int(data["words_read"]), int(data["seconds_read"])
        except (OSError, ValueError, KeyError, TypeError):
            return ReadingStats()
        return ReadingStats(max(words, 0), max(seconds, 0))

    def _save(self) -> None:
        if self._path is None:
            return  # no file: the numbers last until the app closes
        try:
            write_json_atomic(self._path, asdict(self._stats))
        except OSError:
            pass  # the numbers still last until the app closes
