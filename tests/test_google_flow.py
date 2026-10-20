"""GoogleFlow: start, open the browser, poll every tick, stop on every outcome."""

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from app_fakes import GOOGLE_TEST_POLL_MS, Rig, make_rig, start_session
from backend_fakes import session_json
from pytestqt.qtbot import QtBot

from clearread.services.account_client import AccountErrorKind, GoogleMode
from clearread.services.session_store import Session
from clearread.ui.google_flow import POLL_INTERVAL_MS, GoogleFlow

TIMEOUT_MS = 5000
BEGIN_PATH = "/v1/auth/google/begin/att-1"
STATUS_ROUTE = "GET /v1/auth/google/status/att-1"
PENDING = (200, {"status": "pending"})
SIGNED_IN = (200, {"status": "signed_in", "session": session_json(google_linked=True)})


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Rig]:
    rig = make_rig(tmp_path)
    yield rig
    rig.pool.waitForDone(TIMEOUT_MS)


def make_flow(rig: Rig, clock: Clock | None = None) -> GoogleFlow:
    services = rig.services
    flow = GoogleFlow(
        services.client,
        services.session,
        services.runner,
        services.open_page,
        GOOGLE_TEST_POLL_MS,
        clock or Clock(),
    )
    return flow


def test_the_default_poll_interval_is_two_seconds() -> None:
    assert POLL_INTERVAL_MS == 2000


def test_link_opens_the_browser_polls_with_the_token_and_stops_when_linked(
    qtbot: QtBot, rig: Rig
) -> None:
    start_session(rig)
    rig.server.google_answers = [PENDING, PENDING, (200, {"status": "linked"})]
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.linked, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.LINK)
    assert rig.browser.paths == [BEGIN_PATH]
    assert rig.server.start_bearers == ["Bearer id-1"]
    assert rig.server.poll_tokens == ["poll-1"] * 3
    assert not flow.active
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == 3  # nothing is asked after the result


def test_sign_in_stores_the_session_like_an_email_sign_in(
    qtbot: QtBot, rig: Rig
) -> None:
    rig.server.google_answers = [PENDING, SIGNED_IN]
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.signed_in, timeout=TIMEOUT_MS) as blocker:
        flow.start(GoogleMode.SIGN_IN)
    session = blocker.args[0]
    assert isinstance(session, Session) and session.google_linked
    assert rig.server.start_bearers == [None]
    stored = rig.store.load()
    assert stored is not None and stored.refresh_token == session.refresh_token
    assert rig.services.session.identity == stored
    assert rig.services.session.bearer() == session.id_token
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == 2


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (409, "google_cancelled", AccountErrorKind.GOOGLE_CANCELLED),
        (409, "google_already_linked", AccountErrorKind.GOOGLE_ALREADY_LINKED),
        (403, "google_not_linked", AccountErrorKind.GOOGLE_NOT_LINKED),
        (404, "google_attempt_not_found", AccountErrorKind.GOOGLE_ATTEMPT_NOT_FOUND),
        (410, "google_attempt_expired", AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED),
    ],
)
def test_a_failed_attempt_stops_the_polling_and_reports_its_kind(
    qtbot: QtBot, rig: Rig, status: int, code: str, kind: AccountErrorKind
) -> None:
    rig.server.google_answers = [PENDING, (status, {"error": code})]
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.failed, timeout=TIMEOUT_MS) as blocker:
        flow.start(GoogleMode.SIGN_IN)
    assert blocker.args == [kind]
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == 2
    assert not flow.active


def test_it_stops_when_the_attempt_runs_out_of_time(qtbot: QtBot, rig: Rig) -> None:
    rig.server.google_expires_in = 600
    clock = Clock()
    flow = make_flow(rig, clock)
    with qtbot.waitSignal(flow.waiting, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.SIGN_IN)
    with qtbot.waitSignal(flow.failed, timeout=TIMEOUT_MS) as blocker:
        clock.now = 601.0
    assert blocker.args == [AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED]
    polls = rig.server.polls()
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == polls
    assert not flow.active


def test_cancel_stops_the_polling_and_nothing_more_is_reported(
    qtbot: QtBot, rig: Rig
) -> None:
    flow = make_flow(rig)
    outcomes: list[object] = []
    flow.failed.connect(outcomes.append)
    flow.linked.connect(lambda: outcomes.append("linked"))
    with qtbot.waitSignal(flow.waiting, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.SIGN_IN)
    qtbot.waitUntil(lambda: rig.server.polls() >= 2, timeout=TIMEOUT_MS)
    flow.cancel()
    assert not flow.active
    rig.pool.waitForDone(TIMEOUT_MS)
    polls = rig.server.polls()
    rig.server.google_answers = [(200, {"status": "linked"})]
    qtbot.wait(6 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == polls
    assert outcomes == []


def test_a_sign_in_that_answers_after_cancel_is_undone(qtbot: QtBot, rig: Rig) -> None:
    gate = threading.Event()
    rig.server.gates[STATUS_ROUTE] = gate
    rig.server.google_answers = [SIGNED_IN]
    flow = make_flow(rig)
    outcomes: list[object] = []
    flow.signed_in.connect(outcomes.append)
    with qtbot.waitSignal(flow.waiting, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.SIGN_IN)
    qtbot.waitUntil(lambda: rig.server.polls() >= 1, timeout=TIMEOUT_MS)
    flow.cancel()
    gate.set()
    rig.pool.waitForDone(TIMEOUT_MS)
    qtbot.waitUntil(lambda: rig.services.session.identity is None, timeout=TIMEOUT_MS)
    assert outcomes == []
    assert rig.store.load() is None


def test_a_browser_that_cannot_open_is_reported_and_nothing_is_polled(
    qtbot: QtBot, rig: Rig
) -> None:
    rig.browser.opens = False
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.failed, timeout=TIMEOUT_MS) as blocker:
        flow.start(GoogleMode.SIGN_IN)
    assert blocker.args == [AccountErrorKind.BROWSER_UNAVAILABLE]
    qtbot.wait(5 * GOOGLE_TEST_POLL_MS)
    assert rig.server.polls() == 0
    assert not flow.active


def test_start_errors_are_reported(qtbot: QtBot, rig: Rig) -> None:
    rig.server.errors["POST /v1/auth/google/start"] = (503, "google_not_configured")
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.failed, timeout=TIMEOUT_MS) as blocker:
        flow.start(GoogleMode.SIGN_IN)
    assert blocker.args == [AccountErrorKind.GOOGLE_NOT_CONFIGURED]
    assert rig.browser.paths == []


def test_link_renews_an_old_token_and_retries_once(qtbot: QtBot, rig: Rig) -> None:
    start_session(rig)
    rig.server.fail_once["POST /v1/auth/google/start"] = (401, "invalid_session")
    rig.server.google_answers = [(200, {"status": "linked"})]
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.linked, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.LINK)
    assert rig.server.count("POST /v1/auth/refresh") == 1
    assert rig.server.count("POST /v1/auth/google/start") == 2


def test_link_gives_up_after_one_retry(qtbot: QtBot, rig: Rig) -> None:
    start_session(rig)
    rig.server.errors["POST /v1/auth/google/start"] = (401, "invalid_session")
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.failed, timeout=TIMEOUT_MS) as blocker:
        flow.start(GoogleMode.LINK)
    assert blocker.args == [AccountErrorKind.INVALID_SESSION]
    assert rig.server.count("POST /v1/auth/google/start") == 2
    assert rig.browser.paths == []


def test_results_arrive_on_the_main_thread(qtbot: QtBot, rig: Rig) -> None:
    rig.server.google_answers = [(200, {"status": "linked"})]
    flow = make_flow(rig)
    threads: list[threading.Thread] = []
    flow.linked.connect(lambda: threads.append(threading.current_thread()))
    with qtbot.waitSignal(flow.linked, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.SIGN_IN)
    assert threads == [threading.main_thread()]


def test_a_second_start_while_active_is_ignored(qtbot: QtBot, rig: Rig) -> None:
    flow = make_flow(rig)
    with qtbot.waitSignal(flow.waiting, timeout=TIMEOUT_MS):
        flow.start(GoogleMode.SIGN_IN)
        flow.start(GoogleMode.SIGN_IN)
    assert rig.server.count("POST /v1/auth/google/start") == 1
    flow.cancel()
