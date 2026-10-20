"""The only module that talks HTTP (NFR-OFF01).

Owns what every call to the ClearRead backend (§4.11) shares: base URL, the client
token header, the optional bearer token, timeouts, the wake probe, JSON decoding and
the mapping of transport failures. Calls block, so they must run inside a worker.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import httpx

# Type of the injectable httpx transport, so other modules never import httpx.
HttpTransport = httpx.BaseTransport

REQUEST_TIMEOUT_SECONDS = 30.0
HEALTH_PROBE_SECONDS = 5.0


class TransportErrorKind(Enum):
    NO_NETWORK = "no_network"
    TIMEOUT = "timeout"


class TransportError(Exception):
    def __init__(self, kind: TransportErrorKind) -> None:
        self.kind = kind
        super().__init__(kind.value)


@dataclass(frozen=True)
class BackendReply:
    status: int
    body: Any  # decoded JSON, or None when the body is empty or not JSON

    @property
    def error_code(self) -> str | None:
        code = self.body.get("error") if isinstance(self.body, dict) else None
        return code if isinstance(code, str) else None


class BearerSource(Protocol):
    """Where AI calls get the user's idToken, and how they ask for a fresh one."""

    def bearer(self) -> str | None: ...

    def renew(self) -> bool: ...


class BackendTransport:
    def __init__(
        self,
        base_url: str,
        client_token: str,
        transport: HttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_token = client_token
        self._transport = transport
        self._sleep = sleep
        self._monotonic = monotonic

    def request(
        self,
        method: str,
        path: str,
        json_body: object | None = None,
        bearer: str | None = None,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        extra_headers: dict[str, str] | None = None,
    ) -> BackendReply:
        headers = {"X-Client-Token": self._client_token, **(extra_headers or {})}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            with httpx.Client(transport=self._transport) as client:
                response = client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json_body,
                    headers=headers,
                    timeout=timeout,
                )
        except httpx.TimeoutException as exc:
            raise TransportError(TransportErrorKind.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise TransportError(TransportErrorKind.NO_NETWORK) from exc
        return BackendReply(response.status_code, _json_or_none(response))

    def is_awake(self) -> bool:
        try:
            with httpx.Client(transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/health", timeout=HEALTH_PROBE_SECONDS
                )
        except httpx.TimeoutException:
            return False  # A sleeping Render service holds the request open.
        except httpx.RequestError as exc:
            raise TransportError(TransportErrorKind.NO_NETWORK) from exc
        return response.status_code == 200

    def wait_until_awake(
        self, on_waking: Callable[[], None], wake_timeout: float, poll_seconds: float
    ) -> bool:
        """True once the backend answers; False if it stays asleep past the timeout."""
        if self.is_awake():
            return True
        on_waking()
        deadline = self._monotonic() + wake_timeout
        while self._monotonic() < deadline:
            self._sleep(poll_seconds)
            if self.is_awake():
                return True
        return False


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None
