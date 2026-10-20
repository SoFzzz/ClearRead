"""Shared fixtures: the app wired to simulated DeepSeek and Firebase (no network)."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest
from fake_firebase import DEFAULT_TOKEN, FakeFirebase
from fake_google import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, FakeClock, FakeGoogle
from fastapi.testclient import TestClient

from clearread_backend.deepseek import DeepSeekGateway
from clearread_backend.firebase import FirebaseAuthGateway, FirestoreGateway
from clearread_backend.google_auth import GoogleAttemptStore
from clearread_backend.google_oauth import GoogleOAuthGateway
from clearread_backend.main import create_app
from clearread_backend.settings import Settings

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {DEFAULT_TOKEN}"}
HEADERS = {"X-Client-Token": TOKEN} | BEARER
FAKE_KEY = "sk-fake-key-for-tests"
FAKE_FIREBASE_KEY = "fake-firebase-api-key"
PUBLIC_BASE_URL = "https://api.clearread.test"
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


@pytest.fixture
def firebase() -> FakeFirebase:
    return FakeFirebase()


def make_client(
    deepseek: FakeDeepSeek,
    firebase: FakeFirebase | None = None,
    google: FakeGoogle | None = None,
    clock: FakeClock | None = None,
    **overrides: object,
) -> TestClient:
    values = {
        "deepseek_api_key": FAKE_KEY,
        "deepseek_model": "deepseek-flash",
        "deepseek_base_url": "https://deepseek.test",
        "client_token": TOKEN,
        "daily_call_limit": 45,
        "firebase_api_key": FAKE_FIREBASE_KEY,
        "firebase_project_id": "fake-project",
        "user_daily_call_limit": 15,
        "google_client_id": GOOGLE_CLIENT_ID,
        "google_client_secret": GOOGLE_CLIENT_SECRET,
        "public_base_url": PUBLIC_BASE_URL,
    } | overrides
    settings = Settings(**values)  # type: ignore[arg-type]
    gateway = DeepSeekGateway(
        settings.deepseek_api_key,
        settings.deepseek_model,
        settings.deepseek_base_url,
        transport=httpx.MockTransport(deepseek),
    )
    transport = httpx.MockTransport(firebase or FakeFirebase())
    return TestClient(
        create_app(
            settings,
            gateway,
            FirebaseAuthGateway(settings.firebase_api_key, transport),
            FirestoreGateway(settings.firebase_project_id, transport),
            GoogleOAuthGateway(
                settings.google_client_id,
                settings.google_client_secret,
                httpx.MockTransport(google or FakeGoogle()),
            ),
            GoogleAttemptStore(clock=clock or FakeClock()),
        )
    )


@pytest.fixture
def client(deepseek: FakeDeepSeek, firebase: FakeFirebase) -> TestClient:
    return make_client(deepseek, firebase)


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
