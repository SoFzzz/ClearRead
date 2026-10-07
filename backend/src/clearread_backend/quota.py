"""Global daily cap on calls to DeepSeek."""

from collections.abc import Callable
from datetime import UTC, date, datetime


def utc_today() -> date:
    return datetime.now(UTC).date()


class DailyQuota:
    """Counts calls per UTC day; the counter lives in memory (resets on restart)."""

    def __init__(self, limit: int, today: Callable[[], date] = utc_today) -> None:
        self._limit = limit
        self._today = today
        self._day = today()
        self._used = 0

    def try_consume(self) -> bool:
        current = self._today()
        if current != self._day:
            self._day = current
            self._used = 0
        if self._used >= self._limit:
            return False
        self._used += 1
        return True
