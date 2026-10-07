"""Shared fixtures: the app wired to a simulated DeepSeek (no network, no real key)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient

from clearread_backend.deepseek import DeepSeekGateway
from clearread_backend.main import create_app
from clearread_backend.settings import Settings

TOKEN = "test-token"
HEADERS = {"X-Client-Token": TOKEN}
FAKE_KEY = "sk-fake-key-for-tests"
Handler = Callable[[httpx.Request], httpx.Response]


def completion(text: str, finish_reason: str = "stop") -> httpx.Response:
    body = {"choices": [{"message": {"content": text}, "finish_reason": finish_reason}]}
    return httpx.Response(200, json=body)


@dataclass
class FakeDeepSeek:
    """Records every request and answers with ``handler``."""

    handler: Handler = lambda request: completion("Respuesta simple.")  # noqa: E731
    requests: list[dict] = field(default_factory=list)
    headers: list[httpx.Headers] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        self.headers.append(request.headers)
        return self.handler(request)


@pytest.fixture
def deepseek() -> FakeDeepSeek:
    return FakeDeepSeek()


def make_client(deepseek: FakeDeepSeek, **overrides: object) -> TestClient:
    values = {
        "deepseek_api_key": FAKE_KEY,
        "deepseek_model": "deepseek-flash",
        "deepseek_base_url": "https://deepseek.test",
        "client_token": TOKEN,
        "daily_call_limit": 45,
    } | overrides
    settings = Settings(**values)  # type: ignore[arg-type]
    gateway = DeepSeekGateway(
        settings.deepseek_api_key,
        settings.deepseek_model,
        settings.deepseek_base_url,
        transport=httpx.MockTransport(deepseek),
    )
    return TestClient(create_app(settings, gateway))


@pytest.fixture
def client(deepseek: FakeDeepSeek) -> TestClient:
    return make_client(deepseek)
