"""Daily caps on calls to DeepSeek: one global and one per user."""

from collections.abc import Callable
from datetime import UTC, date, datetime


def utc_today() -> date:
    return datetime.now(UTC).date()


class DailyQuota:
    """Counts calls per key and UTC day; counters live in memory (reset on restart).

    The global cap uses the default key; the per-user cap uses the uid.
    """

    def __init__(self, limit: int, today: Callable[[], date] = utc_today) -> None:
        self._limit = limit
        self._today = today
        self._day = today()
        self._used: dict[str, int] = {}

    def try_consume(self, key: str = "") -> bool:
        current = self._today()
        if current != self._day:
            self._day = current
            self._used = {}
        used = self._used.get(key, 0)
        if used >= self._limit:
            return False
        self._used[key] = used + 1
        return True
