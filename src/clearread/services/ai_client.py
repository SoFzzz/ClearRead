"""Optional generative-AI assistant client (§4.10).

Talks only to the ClearRead backend (§4.11), never to DeepSeek. The only app module
allowed to import httpx (NFR-OFF01). Calls block, so they must run inside a worker,
never on the UI thread (AI-F04).
"""

import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx


class AIErrorKind(Enum):
    """Machine-readable error kind; the visible messages live in ui/strings.py."""

    NO_NETWORK = "no_network"
    SERVER_WAKING = "server_waking"
    TIMEOUT = "timeout"
    SESSION_LIMIT = "session_limit"
    DAILY_LIMIT = "daily_limit"
    INPUT_TOO_LONG = "input_too_long"
    SERVICE_UNAVAILABLE = "service_unavailable"
    BAD_RESPONSE = "bad_response"


class AIUnavailableError(Exception):
    def __init__(self, kind: AIErrorKind) -> None:
        self.kind = kind
        super().__init__(kind.value)


@dataclass(frozen=True)
class AIResponse:
    text: str
    from_cache: bool = False


class AIClient(ABC):
    """Abstract interface so the UI never depends on a concrete transport."""

    @abstractmethod
    def ensure_awake(self, on_waking: Callable[[], None]) -> None: ...

    @abstractmethod
    def explain_word(self, word: str, context_sentence: str) -> AIResponse: ...

    @abstractmethod
    def simplify_paragraph(self, text: str) -> AIResponse: ...


# The backend's own stable error codes (§4.11); its answers never carry DeepSeek text.
_CODE_TO_KIND: dict[str, AIErrorKind] = {
    "invalid_client_token": AIErrorKind.SERVICE_UNAVAILABLE,
    "input_too_long": AIErrorKind.INPUT_TOO_LONG,
    "invalid_request": AIErrorKind.BAD_RESPONSE,
    "daily_limit_reached": AIErrorKind.DAILY_LIMIT,
    "upstream_auth_failed": AIErrorKind.SERVICE_UNAVAILABLE,
    "upstream_no_balance": AIErrorKind.SERVICE_UNAVAILABLE,
    "upstream_bad_response": AIErrorKind.SERVICE_UNAVAILABLE,
    "upstream_timeout": AIErrorKind.TIMEOUT,
}
# Fallback when the body has no known code (e.g. an error page from the host's proxy).
_STATUS_TO_KIND: dict[int, AIErrorKind] = {
    401: AIErrorKind.SERVICE_UNAVAILABLE,
    413: AIErrorKind.INPUT_TOO_LONG,
    429: AIErrorKind.DAILY_LIMIT,
    502: AIErrorKind.SERVICE_UNAVAILABLE,
    503: AIErrorKind.SERVICE_UNAVAILABLE,
    504: AIErrorKind.TIMEOUT,
}

CACHE_MAX_ENTRIES = 200
_KEY_SEPARATOR = "\x1f"


class DiskResponseCache:
    """Answers kept in one JSON file, keyed by (function, normalized text).

    A missing or damaged file just means an empty cache: the cache never fails a call.
    """

    def __init__(self, path: Path, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._path = path
        self._max_entries = max_entries
        self._entries = self._load()

    def get(self, key: tuple[str, ...]) -> str | None:
        return self._entries.get(_KEY_SEPARATOR.join(key))

    def set(self, key: tuple[str, ...], text: str) -> None:
        joined = _KEY_SEPARATOR.join(key)
        self._entries.pop(joined, None)
        self._entries[joined] = text
        while len(self._entries) > self._max_entries:
            del self._entries[next(iter(self._entries))]
        self._save()

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(v, str)}

    def _save(self) -> None:
        temp_file: str | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_file = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(self._entries, file, ensure_ascii=False)
            os.replace(temp_file, self._path)
        except OSError:
            # Losing the cache write only costs a repeated request.
            if temp_file is not None:
                Path(temp_file).unlink(missing_ok=True)


def kind_for_error(status_code: int, body: Any) -> AIErrorKind:
    code = body.get("error") if isinstance(body, dict) else None
    if isinstance(code, str) and code in _CODE_TO_KIND:
        return _CODE_TO_KIND[code]
    return _STATUS_TO_KIND.get(status_code, AIErrorKind.BAD_RESPONSE)


class BackendAIClient(AIClient):
    MAX_CALLS_PER_SESSION = 30
    REQUEST_TIMEOUT_SECONDS = 30.0
    HEALTH_PROBE_SECONDS = 5.0
    WAKE_TIMEOUT_SECONDS = 60.0
    WAKE_POLL_SECONDS = 2.0

    def __init__(
        self,
        base_url: str,
        client_token: str,
        cache: DiskResponseCache,
        lang: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._lang = lang
        self._headers = {"X-Client-Token": client_token}
        self._cache = cache
        self._transport = transport
        self._sleep = sleep
        self._monotonic = monotonic
        self._calls_this_session = 0

    def ensure_awake(self, on_waking: Callable[[], None]) -> None:
        if self._health_ok():
            return
        on_waking()
        deadline = self._monotonic() + self.WAKE_TIMEOUT_SECONDS
        while self._monotonic() < deadline:
            self._sleep(self.WAKE_POLL_SECONDS)
            if self._health_ok():
                return
        raise AIUnavailableError(AIErrorKind.SERVER_WAKING)

    def explain_word(self, word: str, context_sentence: str) -> AIResponse:
        payload = {
            "word": word,
            "context_sentence": context_sentence,
            "lang": self._lang,
        }
        return self._call_or_cache("/v1/explain", payload)

    def simplify_paragraph(self, text: str) -> AIResponse:
        return self._call_or_cache("/v1/simplify", {"text": text, "lang": self._lang})

    def _health_ok(self) -> bool:
        try:
            with httpx.Client(transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/health", timeout=self.HEALTH_PROBE_SECONDS
                )
        except httpx.TimeoutException:
            return False  # A sleeping Render service holds the request open.
        except httpx.RequestError as exc:
            raise AIUnavailableError(AIErrorKind.NO_NETWORK) from exc
        return response.status_code == 200

    def _call_or_cache(self, path: str, payload: dict[str, str]) -> AIResponse:
        cache_key = (path, *(" ".join(v.lower().split()) for v in payload.values()))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return AIResponse(text=cached, from_cache=True)
        if self._calls_this_session >= self.MAX_CALLS_PER_SESSION:
            raise AIUnavailableError(AIErrorKind.SESSION_LIMIT)
        text = self._post(path, payload)
        self._cache.set(cache_key, text)
        return AIResponse(text=text)

    def _post(self, path: str, payload: dict[str, str]) -> str:
        try:
            with httpx.Client(transport=self._transport) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    json=payload,
                    headers=self._headers,
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                )
        except httpx.TimeoutException as exc:
            raise AIUnavailableError(AIErrorKind.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise AIUnavailableError(AIErrorKind.NO_NETWORK) from exc

        self._calls_this_session += 1
        body = self._json_or_none(response)
        if response.status_code != 200:
            raise AIUnavailableError(kind_for_error(response.status_code, body))
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise AIUnavailableError(AIErrorKind.BAD_RESPONSE)
        return text.strip()

    @staticmethod
    def _json_or_none(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None
