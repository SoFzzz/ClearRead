"""Account workers: signals, serialization, the retry and the guarantee nothing escapes."""

from pathlib import Path

import httpx
import pytest
from backend_fakes import make_account_client, session_json
from pytestqt.qtbot import QtBot

from clearread.services.account_client import (
    AccountClient,
    AccountErrorKind,
    GoogleAttempt,
    GoogleState,
    RemoteProfile,
)
from clearread.services.profile_sync import SyncAction
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import Session, SessionStore, StoredSession
from clearread.workers.account_worker import (
    DeleteAccountWorker,
    GoogleStatusWorker,
    PasswordResetWorker,
    RefreshSessionWorker,
    RegisterWorker,
    SignInWorker,
    SyncProfileWorker,
    create_account_thread_pool,
)

HEALTH = "/health"
LOCAL = RemoteProfile({"theme": "light"}, [], [], "2026-10-19T12:00:00Z")


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "session.bin", lambda d: d, lambda d: d)


def make_manager(client: AccountClient, tmp_path: Path) -> SessionManager:
    return SessionManager(client, make_store(tmp_path))


def make_session() -> Session:
    return Session("abc123", "a@b.co", "Ana", False, "id-1", "r1", 9_999_999_999.0)


def run(worker: object) -> None:
    pool = create_account_thread_pool()
    pool.start(worker)  # type: ignore[arg-type]
    assert pool.waitForDone(5000)


def handler_for(routes: dict[tuple[str, str], list[httpx.Response]]):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == HEALTH:
            return httpx.Response(200, json={})
        return routes[(request.method, request.url.path)].pop(0)

    return handler


def test_pool_is_serialized() -> None:
    assert create_account_thread_pool().maxThreadCount() == 1


def test_sign_in_emits_the_session_and_starts_it(qtbot: QtBot, tmp_path: Path) -> None:
    client, _ = make_account_client(
        handler_for(
            {("POST", "/v1/auth/login"): [httpx.Response(200, json=session_json())]}
        )
    )
    manager = make_manager(client, tmp_path)
    worker = SignInWorker(client, manager, "ana@example.com", "secret-pass")

    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        run(worker)

    assert blocker.args[0].uid == "abc123"
    assert manager.identity == StoredSession(
        "abc123", "ana@example.com", "Ana", "refresh-1"
    )


def test_register_emits_the_session(qtbot: QtBot, tmp_path: Path) -> None:
    client, backend = make_account_client(
        handler_for(
            {("POST", "/v1/auth/register"): [httpx.Response(201, json=session_json())]}
        )
    )
    worker = RegisterWorker(
        client, make_manager(client, tmp_path), "a@b.co", "secret-pass", "Ana"
    )

    with qtbot.waitSignal(worker.signals.finished, timeout=5000):
        run(worker)

    assert backend.bodies()[-1]["display_name"] == "Ana"  # type: ignore[index]


def test_wrong_password_emits_its_kind_and_no_session(
    qtbot: QtBot, tmp_path: Path
) -> None:
    client, _ = make_account_client(
        handler_for(
            {
                ("POST", "/v1/auth/login"): [
                    httpx.Response(401, json={"error": "invalid_credentials"})
                ]
            }
        )
    )
    manager = make_manager(client, tmp_path)
    worker = SignInWorker(client, manager, "a@b.co", "bad-password")

    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)

    assert blocker.args == [AccountErrorKind.INVALID_CREDENTIALS]
    assert manager.identity is None


def test_password_reset_finishes(qtbot: QtBot) -> None:
    client, _ = make_account_client(
        handler_for({("POST", "/v1/auth/password-reset"): [httpx.Response(204)]})
    )
    worker = PasswordResetWorker(client, "a@b.co")

    with qtbot.waitSignal(worker.signals.finished, timeout=5000):
        run(worker)


def test_refresh_revoked_emits_session_revoked(qtbot: QtBot, tmp_path: Path) -> None:
    client, _ = make_account_client(
        handler_for(
            {
                ("POST", "/v1/auth/refresh"): [
                    httpx.Response(401, json={"error": "session_revoked"})
                ]
            }
        )
    )
    make_store(tmp_path).save(StoredSession("abc123", "a@b.co", "Ana", "r1"))
    manager = make_manager(client, tmp_path)
    manager.resume()
    worker = RefreshSessionWorker(client, manager)

    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)

    assert blocker.args == [AccountErrorKind.SESSION_REVOKED]
    assert manager.identity is None


def test_sync_retries_once_after_invalid_session(qtbot: QtBot, tmp_path: Path) -> None:
    profile = {
        "settings": {"theme": "dark"},
        "words": [],
        "topics": [],
        "updated_at": "2026-10-19T13:00:00Z",
    }
    client, backend = make_account_client(
        handler_for(
            {
                ("GET", "/v1/profile"): [
                    httpx.Response(401, json={"error": "invalid_session"}),
                    httpx.Response(200, json=profile),
                ],
                ("POST", "/v1/auth/refresh"): [
                    httpx.Response(200, json=session_json(id_token="id-2"))
                ],
            }
        )
    )
    manager = make_manager(client, tmp_path)
    manager.start(make_session())
    worker = SyncProfileWorker(client, manager, LOCAL, "now")

    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        run(worker)

    assert blocker.args[0].action is SyncAction.PULL
    gets = [
        r for r in backend.requests if r.method == "GET" and r.url.path == "/v1/profile"
    ]
    assert [r.headers["Authorization"] for r in gets] == ["Bearer id-1", "Bearer id-2"]


def test_delete_account_signs_out(qtbot: QtBot, tmp_path: Path) -> None:
    client, _ = make_account_client(
        handler_for({("DELETE", "/v1/account"): [httpx.Response(204)]})
    )
    manager = make_manager(client, tmp_path)
    manager.start(make_session())
    worker = DeleteAccountWorker(client, manager)

    with qtbot.waitSignal(worker.signals.finished, timeout=5000):
        run(worker)

    assert manager.identity is None


def test_waking_is_emitted_when_the_backend_is_asleep(qtbot: QtBot) -> None:
    probes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == HEALTH:
            probes.append(1)
            if len(probes) == 1:
                raise httpx.ReadTimeout("asleep", request=request)
            return httpx.Response(200, json={})
        return httpx.Response(204)

    client, _ = make_account_client(handler)
    worker = PasswordResetWorker(client, "a@b.co")
    events: list[str] = []
    worker.signals.waking.connect(lambda: events.append("waking"))
    worker.signals.finished.connect(lambda result: events.append("finished"))

    run(worker)

    qtbot.waitUntil(lambda: events == ["waking", "finished"], timeout=2000)


def test_google_polls_do_not_probe_health(qtbot: QtBot, tmp_path: Path) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"status": "pending"})

    client, _ = make_account_client(handler)
    attempt = GoogleAttempt("attempt-id", "poll-token", 600)
    worker = GoogleStatusWorker(client, make_manager(client, tmp_path), attempt)

    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        run(worker)

    assert blocker.args[0].state is GoogleState.PENDING
    assert paths == ["/v1/auth/google/status/attempt-id"]


@pytest.mark.parametrize("body", [["not", "a", "session"], {"uid": "abc"}])
def test_unexpected_answers_become_a_kind_not_an_exception(
    qtbot: QtBot, tmp_path: Path, body: object
) -> None:
    client, _ = make_account_client(
        handler_for({("POST", "/v1/auth/login"): [httpx.Response(200, json=body)]})
    )
    worker = SignInWorker(
        client, make_manager(client, tmp_path), "a@b.co", "secret-pass"
    )

    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)

    assert blocker.args == [AccountErrorKind.UNEXPECTED]


def test_unexpected_exception_never_escapes(qtbot: QtBot) -> None:
    client, _ = make_account_client(
        lambda r: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    worker = PasswordResetWorker(client, "a@b.co")

    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)

    assert blocker.args == [AccountErrorKind.UNEXPECTED]
