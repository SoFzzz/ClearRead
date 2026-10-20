"""SyncController: debounced push, retry when online, pull, a change during a sync."""

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from app_fakes import Rig, make_rig, start_session
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.services.groups import GroupStore
from clearread.services.profile_sync import SyncStateStore
from clearread.ui.account_state import SyncStatus
from clearread.ui.sync_controller import RETRY_MS, SyncController

TIMEOUT_MS = 5000
DEBOUNCE_MS = 40
ENTRY = GlossaryEntry("casa", "Un lugar donde vives.", "doc", "2026-10-19")


@dataclass
class Setup:
    rig: Rig
    sync: SyncController
    state: SyncStateStore
    glossary: GlossaryStore
    topics: GroupStore
    config: AppConfig


@pytest.fixture
def setup(qtbot: QtBot, tmp_path: Path) -> Iterator[Setup]:
    rig = make_rig(tmp_path)
    start_session(rig)
    state = SyncStateStore(tmp_path)
    glossary = GlossaryStore(tmp_path / "glossary.json")
    topics = GroupStore(tmp_path / "topics.json")
    config = AppConfig()
    sync = SyncController(
        rig.services.client,
        rig.services.session,
        rig.services.runner,
        state,
        lambda: config,
        glossary,
        topics,
        debounce_ms=DEBOUNCE_MS,
    )
    yield Setup(rig, sync, state, glossary, topics, config)
    sync.shutdown()
    rig.pool.waitForDone(TIMEOUT_MS)


def wait_for_status(qtbot: QtBot, sync: SyncController, status: SyncStatus) -> None:
    qtbot.waitUntil(lambda: sync.status is status, timeout=TIMEOUT_MS)


def test_starts_with_unsaved_changes_until_the_first_sync(setup: Setup) -> None:
    assert setup.sync.status is SyncStatus.PENDING
    assert setup.sync.has_unsaved_changes


def test_a_change_is_pushed_after_the_debounce_not_before(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.sync.notify_changed()
    assert setup.rig.server.calls == []
    assert setup.sync.status is SyncStatus.PENDING
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    assert setup.rig.server.count("PUT /v1/profile") == 1
    assert setup.rig.server.profile is not None
    assert setup.rig.server.profile["updated_at"] == setup.state.updated_at()


def test_several_quick_changes_make_one_push(qtbot: QtBot, setup: Setup) -> None:
    for _ in range(5):
        setup.sync.notify_changed()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    qtbot.wait(2 * DEBOUNCE_MS)
    assert setup.rig.server.count("PUT /v1/profile") == 1


def test_the_pushed_profile_has_settings_words_and_topics(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.glossary.add(ENTRY)
    setup.topics.create("Biologia")
    setup.sync.notify_changed()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    profile = setup.rig.server.profile
    assert profile is not None
    assert [w["word"] for w in profile["words"]] == ["casa"]  # type: ignore[index]
    assert [t["name"] for t in profile["topics"]] == ["Biologia"]  # type: ignore[index]
    assert "backend_url" not in profile["settings"]  # type: ignore[operator]


def test_offline_changes_wait_and_go_out_when_the_network_returns(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.sync.set_online(False)
    setup.sync.notify_changed()
    qtbot.wait(4 * DEBOUNCE_MS)
    assert setup.rig.server.calls == []
    assert setup.sync.status is SyncStatus.PENDING
    setup.sync.set_online(True)
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    assert setup.rig.server.count("PUT /v1/profile") == 1


def test_coming_online_with_nothing_pending_does_not_sync_again(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.sync.sync_now()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    calls = len(setup.rig.server.calls)
    setup.sync.set_online(True)
    qtbot.wait(2 * DEBOUNCE_MS)
    assert len(setup.rig.server.calls) == calls


def test_an_account_error_marks_failed_and_schedules_a_retry(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.rig.server.errors["GET /v1/profile"] = (502, "auth_upstream_error")
    setup.sync.sync_now()
    wait_for_status(qtbot, setup.sync, SyncStatus.FAILED)
    assert setup.sync._timer.isActive()
    assert setup.sync._timer.remainingTime() > RETRY_MS // 2


def test_a_newer_remote_profile_is_pulled_and_reported(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.rig.server.profile = {
        "settings": {"theme": "dark", "ui_language": "en"},
        "words": [ENTRY.__dict__],
        "topics": [],
        "updated_at": "2030-01-01T00:00:00Z",
    }
    pulled: list[AppConfig] = []
    setup.sync.config_pulled.connect(pulled.append)
    setup.sync.sync_now()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    assert [c.theme for c in pulled] == ["dark"]
    assert pulled[0].ui_language == "en"
    assert [e.word for e in setup.glossary.entries()] == ["casa"]
    assert setup.state.updated_at() == "2030-01-01T00:00:00Z"


def test_a_session_the_account_refuses_is_reported_as_ended(
    qtbot: QtBot, setup: Setup
) -> None:
    server = setup.rig.server
    server.errors["GET /v1/profile"] = (401, "invalid_session")
    server.errors["POST /v1/auth/refresh"] = (401, "session_revoked")
    with qtbot.waitSignal(setup.sync.session_ended, timeout=TIMEOUT_MS):
        setup.sync.sync_now()


def test_a_second_401_after_the_retry_ends_the_session(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.rig.server.errors["GET /v1/profile"] = (401, "invalid_session")
    with qtbot.waitSignal(setup.sync.session_ended, timeout=TIMEOUT_MS):
        setup.sync.sync_now()
    assert setup.rig.server.count("POST /v1/auth/refresh") == 1


def test_a_change_made_during_a_sync_is_not_lost(qtbot: QtBot, setup: Setup) -> None:
    gate = threading.Event()
    setup.rig.server.gates["PUT /v1/profile"] = gate
    setup.sync.notify_changed()
    qtbot.waitUntil(
        lambda: setup.rig.server.count("PUT /v1/profile") == 1, timeout=TIMEOUT_MS
    )
    setup.glossary.add(ENTRY)
    setup.sync.notify_changed()
    del setup.rig.server.gates["PUT /v1/profile"]
    gate.set()
    qtbot.waitUntil(
        lambda: setup.rig.server.count("PUT /v1/profile") == 2, timeout=TIMEOUT_MS
    )
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    profile = setup.rig.server.profile
    assert profile is not None
    assert [w["word"] for w in profile["words"]] == ["casa"]  # type: ignore[index]
    assert profile["updated_at"] == setup.state.updated_at()


def test_suspend_holds_pushes_until_resume(qtbot: QtBot, setup: Setup) -> None:
    setup.sync.suspend()
    setup.sync.notify_changed()
    qtbot.wait(4 * DEBOUNCE_MS)
    assert setup.rig.server.calls == []
    setup.sync.resume()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)


def test_nothing_goes_out_after_shutdown(qtbot: QtBot, setup: Setup) -> None:
    setup.sync.notify_changed()
    setup.sync.shutdown()
    qtbot.wait(4 * DEBOUNCE_MS)
    assert setup.rig.server.calls == []


def test_flush_pushes_pending_changes_then_calls_back(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.sync.notify_changed()
    done: list[bool] = []
    setup.sync.flush(lambda: done.append(True))
    qtbot.waitUntil(lambda: done == [True], timeout=TIMEOUT_MS)
    assert setup.sync.status is SyncStatus.OK
    assert setup.rig.server.count("PUT /v1/profile") == 1


def test_flush_offline_calls_back_at_once(setup: Setup) -> None:
    setup.sync.set_online(False)
    setup.sync.notify_changed()
    done: list[bool] = []
    setup.sync.flush(lambda: done.append(True))
    assert done == [True]


def test_flush_with_everything_saved_calls_back_at_once(
    qtbot: QtBot, setup: Setup
) -> None:
    setup.sync.sync_now()
    wait_for_status(qtbot, setup.sync, SyncStatus.OK)
    done: list[bool] = []
    setup.sync.flush(lambda: done.append(True))
    assert done == [True]
