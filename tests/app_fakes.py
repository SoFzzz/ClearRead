"""Doubles for the v1.6 UI tests: a scripted account backend and the app's services."""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import numpy as np
from backend_fakes import make_account_client, session_json
from fakes import EngineSource, FakeAIClient
from PySide6.QtCore import QThreadPool

from clearread.core.device_settings import DeviceSettingsStore
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import OCRResult
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import Session, SessionStore, StoredSession
from clearread.services.tts_controller import TTSController
from clearread.ui.app_controller import AppServices
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import create_account_thread_pool

UID = "abc123"
SYNC_TEST_DEBOUNCE_MS = 50
GOOGLE_TEST_POLL_MS = 20


@dataclass
class FakeAccountServer:
    """What the backend does with account calls; tests change its fields to script it."""

    profile: dict[str, object] | None = None
    errors: dict[str, tuple[int, str]] = field(default_factory=dict)  # "METHOD path"
    session_fields: dict[str, object] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    gates: dict[str, threading.Event] = field(default_factory=dict)  # block a route
    fail_once: dict[str, tuple[int, str]] = field(default_factory=dict)  # then recovers
    # Google: answers to the status polls, in order; "pending" once they run out.
    google_answers: list[tuple[int, dict[str, object]]] = field(default_factory=list)
    google_expires_in: int = 600
    start_bearers: list[str | None] = field(default_factory=list)
    poll_tokens: list[str | None] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        route = f"{request.method} {request.url.path}"
        if request.url.path == "/health":
            return httpx.Response(200, json={})
        self.calls.append(route)
        if route in self.gates:
            self.gates[route].wait(timeout=10)
        if route in self.fail_once:
            status, code = self.fail_once.pop(route)
            return httpx.Response(status, json={"error": code})
        if route in self.errors:
            status, code = self.errors[route]
            return httpx.Response(status, json={"error": code})
        return self._answer(route, request)

    def _answer(self, route: str, request: httpx.Request) -> httpx.Response:
        if route in ("POST /v1/auth/login", "POST /v1/auth/refresh"):
            return httpx.Response(200, json=session_json(**self.session_fields))
        if route == "POST /v1/auth/register":
            return httpx.Response(201, json=session_json(**self.session_fields))
        if route == "POST /v1/auth/google/start":
            self.start_bearers.append(request.headers.get("Authorization"))
            return httpx.Response(200, json=self._attempt())
        if route.startswith("GET /v1/auth/google/status/"):
            self.poll_tokens.append(request.headers.get("X-Poll-Token"))
            status, body = (
                self.google_answers.pop(0)
                if self.google_answers
                else (200, {"status": "pending"})
            )
            return httpx.Response(status, json=body)
        if route == "GET /v1/profile":
            if self.profile is None:
                return httpx.Response(404, json={"error": "profile_not_found"})
            return httpx.Response(200, json=self.profile)
        if route == "PUT /v1/profile":
            self.profile = json.loads(request.content)
            return httpx.Response(200, json=self.profile)
        return httpx.Response(204)

    def _attempt(self) -> dict[str, object]:
        return {
            "attempt_id": "att-1",
            "poll_token": "poll-1",
            "expires_in": self.google_expires_in,
        }

    def count(self, route: str) -> int:
        return self.calls.count(route)

    def polls(self) -> int:
        return sum(
            call.startswith("GET /v1/auth/google/status/") for call in self.calls
        )


class StubOCR:
    def process_image(self, image: np.ndarray, page_number: int = 1) -> OCRResult:
        return OCRResult(page_number, "")


def identity_store(path: Path) -> SessionStore:
    """A session file without Windows encryption: tests of the flow, not of DPAPI."""
    return SessionStore(path, lambda data: data, lambda data: data)


def save_session(store: SessionStore, uid: str = UID) -> None:
    store.save(StoredSession(uid, "ana@example.com", "Ana", "refresh-0"))


class FakeBrowser:
    """Records the pages the app asks the system browser to open."""

    def __init__(self, opens: bool = True) -> None:
        self.opens = opens
        self.paths: list[str] = []

    def open_backend_page(self, path: str) -> bool:
        self.paths.append(path)
        return self.opens


@dataclass
class Rig:
    services: AppServices
    server: FakeAccountServer
    network: NetworkMonitor
    store: SessionStore
    pool: QThreadPool
    browser: FakeBrowser


def make_rig(tmp_path: Path, server: FakeAccountServer | None = None) -> Rig:
    server = server or FakeAccountServer()
    client, _ = make_account_client(server, now=time.time())
    store = identity_store(tmp_path / "session.bin")
    session = SessionManager(client, store)
    pool = create_account_thread_pool()
    network = NetworkMonitor(None)
    browser = FakeBrowser()
    services = AppServices(
        data_dir=tmp_path,
        profile_dir_for=lambda uid: _profile_dir(tmp_path, uid),
        client=client,
        session=session,
        runner=AccountTaskRunner(pool),
        device=DeviceSettingsStore(tmp_path / "device.json"),
        network=network,
        ocr_engine=StubOCR(),  # type: ignore[arg-type]
        make_tts=lambda: TTSController(engine_factory=EngineSource()),
        make_ai_client=lambda config, cache, bearer: FakeAIClient(),
        open_page=browser.open_backend_page,
        sync_debounce_ms=SYNC_TEST_DEBOUNCE_MS,
        google_poll_ms=GOOGLE_TEST_POLL_MS,
    )
    return Rig(services, server, network, store, pool, browser)


def _profile_dir(tmp_path: Path, uid: str) -> Path:
    path = tmp_path / "profiles" / uid
    path.mkdir(parents=True, exist_ok=True)
    return path


def start_session(rig: Rig, uid: str = UID) -> Session:
    """Sign in without the UI, the way a stored or fresh session would be."""
    session = Session(
        uid, "ana@example.com", "Ana", True, "id-1", "r1", 9_999_999_999.0
    )
    rig.services.session.start(session)
    return session
