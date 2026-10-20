"""SessionStore (encrypted file) and SessionManager (token refresh)."""

import json
from pathlib import Path

import pytest

from clearread.services.account_client import AccountError, AccountErrorKind
from clearread.services.session_manager import SessionManager
from clearread.services.session_store import (
    Session,
    SessionStore,
    StoredSession,
    dpapi_protect,
    dpapi_unprotect,
)

STORED = StoredSession("abc123", "ana@example.com", "Ana", "refresh-1")


def fake_protect(data: bytes) -> bytes:
    return b"ENC" + data[::-1]


def fake_unprotect(data: bytes) -> bytes:
    if not data.startswith(b"ENC"):
        raise ValueError("not ours")
    return data[3:][::-1]


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "session.bin", fake_protect, fake_unprotect)


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.save(STORED)

    assert store.load() == STORED


def test_file_holds_no_readable_secret(tmp_path: Path) -> None:
    make_store(tmp_path).save(STORED)

    raw = (tmp_path / "session.bin").read_bytes()

    assert b"refresh-1" not in raw
    assert b"ana@example.com" not in raw


def test_missing_file_loads_none(tmp_path: Path) -> None:
    assert make_store(tmp_path).load() is None


@pytest.mark.parametrize(
    "content",
    [b"", b"garbage", b"ENC" + b"}{"[::-1], b"ENC" + b"]1[ "[::-1]],
)
def test_corrupt_file_loads_none(tmp_path: Path, content: bytes) -> None:
    (tmp_path / "session.bin").write_bytes(content)

    assert make_store(tmp_path).load() is None


@pytest.mark.parametrize(
    "data",
    [
        {"uid": "../evil", "email": "a", "display_name": "b", "refresh_token": "r"},
        {"uid": "abc", "email": "a", "display_name": "b", "refresh_token": ""},
        {"uid": "abc", "email": 1, "display_name": "b", "refresh_token": "r"},
        {"uid": "abc", "email": "a", "display_name": "b"},
        {"uid": "abc", "email": "a", "display_name": "b", "refresh_token": "r", "x": 1},
    ],
)
def test_wrong_content_loads_none(tmp_path: Path, data: dict[str, object]) -> None:
    raw = json.dumps(data).encode("utf-8")
    (tmp_path / "session.bin").write_bytes(fake_protect(raw))

    assert make_store(tmp_path).load() is None


def test_clear_removes_the_file_and_is_safe_twice(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.save(STORED)

    store.clear()
    store.clear()

    assert store.load() is None


def test_save_failure_in_the_cipher_is_an_oserror(tmp_path: Path) -> None:
    def broken(data: bytes) -> bytes:
        raise RuntimeError("dpapi")

    store = SessionStore(tmp_path / "session.bin", broken, fake_unprotect)

    with pytest.raises(OSError):
        store.save(STORED)


def test_real_dpapi_round_trip(tmp_path: Path) -> None:
    pytest.importorskip("win32crypt")
    store = SessionStore(tmp_path / "session.bin", dpapi_protect, dpapi_unprotect)

    store.save(STORED)

    assert b"refresh-1" not in (tmp_path / "session.bin").read_bytes()
    assert store.load() == STORED


class FakeAccountClient:
    def __init__(self) -> None:
        self.refresh_calls: list[str] = []
        self.errors: list[AccountErrorKind] = []
        self.generation = 1

    def refresh(self, refresh_token: str) -> Session:
        self.refresh_calls.append(refresh_token)
        if self.errors:
            raise AccountError(self.errors.pop(0))
        self.generation += 1
        return make_session(self.generation, expires_at=10_000.0)


def make_session(generation: int = 1, expires_at: float = 5000.0) -> Session:
    return Session(
        "abc123",
        "ana@example.com",
        "Ana",
        False,
        f"id-{generation}",
        f"refresh-{generation}",
        expires_at,
    )


class Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.now = 1000.0
        self.client = FakeAccountClient()
        self.store = make_store(tmp_path)
        self.manager = SessionManager(
            self.client,  # type: ignore[arg-type]
            self.store,
            clock=lambda: self.now,
        )


@pytest.fixture
def fixture(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path)


def test_start_keeps_the_token_in_memory_and_saves_only_the_identity(
    fixture: Fixture,
) -> None:
    fixture.manager.start(make_session())

    assert fixture.manager.bearer() == "id-1"
    assert fixture.client.refresh_calls == []
    assert fixture.store.load() == StoredSession(
        "abc123", "ana@example.com", "Ana", "refresh-1"
    )


def test_resume_opens_offline_without_a_token(fixture: Fixture) -> None:
    fixture.store.save(STORED)

    identity = fixture.manager.resume()

    assert identity == STORED
    assert fixture.client.refresh_calls == []


def test_bearer_refreshes_an_expired_token_and_stores_the_new_refresh_token(
    fixture: Fixture,
) -> None:
    fixture.manager.start(make_session(expires_at=1030.0))  # inside the margin

    assert fixture.manager.bearer() == "id-2"
    assert fixture.client.refresh_calls == ["refresh-1"]
    stored = fixture.store.load()
    assert stored is not None and stored.refresh_token == "refresh-2"


def test_bearer_is_none_without_session_or_when_refresh_fails(fixture: Fixture) -> None:
    assert fixture.manager.bearer() is None

    fixture.store.save(STORED)
    fixture.manager.resume()
    fixture.client.errors = [AccountErrorKind.NO_NETWORK]

    assert fixture.manager.bearer() is None


def test_revoked_refresh_token_signs_out_and_clears_the_file(fixture: Fixture) -> None:
    fixture.store.save(STORED)
    fixture.manager.resume()
    fixture.client.errors = [AccountErrorKind.SESSION_REVOKED]

    with pytest.raises(AccountError) as raised:
        fixture.manager.refresh()

    assert raised.value.kind is AccountErrorKind.SESSION_REVOKED
    assert fixture.manager.identity is None
    assert fixture.store.load() is None


def test_network_failure_while_refreshing_keeps_the_session(fixture: Fixture) -> None:
    fixture.store.save(STORED)
    fixture.manager.resume()
    fixture.client.errors = [AccountErrorKind.NO_NETWORK]

    assert not fixture.manager.renew()

    assert fixture.manager.identity == STORED
    assert fixture.store.load() == STORED


def test_refresh_without_session_is_revoked(fixture: Fixture) -> None:
    with pytest.raises(AccountError) as raised:
        fixture.manager.refresh()

    assert raised.value.kind is AccountErrorKind.SESSION_REVOKED


def test_run_authorized_retries_once_after_invalid_session(fixture: Fixture) -> None:
    fixture.manager.start(make_session())
    seen: list[str] = []

    def call(token: str) -> str:
        seen.append(token)
        if token == "id-1":
            raise AccountError(AccountErrorKind.INVALID_SESSION)
        return "done"

    assert fixture.manager.run_authorized(call) == "done"
    assert seen == ["id-1", "id-2"]


def test_run_authorized_does_not_retry_twice_or_other_errors(fixture: Fixture) -> None:
    fixture.manager.start(make_session())
    calls: list[str] = []

    def always_invalid(token: str) -> str:
        calls.append(token)
        raise AccountError(AccountErrorKind.INVALID_SESSION)

    with pytest.raises(AccountError):
        fixture.manager.run_authorized(always_invalid)
    assert len(calls) == 2

    def too_large(token: str) -> str:
        raise AccountError(AccountErrorKind.PROFILE_TOO_LARGE)

    with pytest.raises(AccountError) as raised:
        fixture.manager.run_authorized(too_large)
    assert raised.value.kind is AccountErrorKind.PROFILE_TOO_LARGE
    assert len(fixture.client.refresh_calls) == 1


def test_sign_out_forgets_everything(fixture: Fixture) -> None:
    fixture.manager.start(make_session())

    fixture.manager.sign_out()

    assert fixture.manager.identity is None
    assert fixture.manager.bearer() is None
    assert fixture.store.load() is None
