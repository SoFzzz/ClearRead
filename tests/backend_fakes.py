"""A fake backend for the HTTP layer: records requests and answers from a script."""

import json
from collections.abc import Callable

import httpx

from clearread.services.account_client import AccountClient
from clearread.services.backend_transport import BackendTransport

BASE = "https://backend.test"
TOKEN = "test-token"

Handler = Callable[[httpx.Request], httpx.Response]


class FakeBackend:
    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    def bodies(self) -> list[object]:
        return [json.loads(r.content) if r.content else None for r in self.requests]


def make_transport(
    backend: FakeBackend, sleep: Callable[[float], None] = lambda seconds: None
) -> BackendTransport:
    return BackendTransport(
        BASE, TOKEN, transport=httpx.MockTransport(backend), sleep=sleep
    )


def make_account_client(
    handler: Handler, now: float = 1000.0
) -> tuple[AccountClient, FakeBackend]:
    backend = FakeBackend(handler)
    return AccountClient(make_transport(backend), clock=lambda: now), backend


def session_json(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "uid": "abc123",
        "email": "ana@example.com",
        "display_name": "Ana",
        "email_verified": False,
        "id_token": "id-1",
        "refresh_token": "refresh-1",
        "expires_in": 3600,
    }
    return {**body, **overrides}
