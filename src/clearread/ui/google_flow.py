"""One Google attempt from the click to the answer (design doc 4.14.11).

Start the attempt, open the browser on our backend, then ask the backend every 2 s until
there is a result, the person cancels or the attempt expires. Every network call runs in
an account worker; this object only lives in the main thread and only sends signals.
"""

import time
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal

from clearread.services.account_client import (
    AccountClient,
    AccountErrorKind,
    GoogleAttempt,
    GoogleMode,
    GoogleState,
    GoogleStatus,
)
from clearread.services.session_manager import SessionManager
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import GoogleStatusWorker, StartGoogleWorker

POLL_INTERVAL_MS = 2000
BEGIN_PATH = "/v1/auth/google/begin/"


class GoogleFlow(QObject):
    starting = Signal()  # the attempt is being created (the server may be waking)
    waking = Signal()
    waiting = Signal()  # the browser is open; waiting for the person
    linked = Signal()
    signed_in = Signal(object)  # Session
    failed = Signal(object)  # AccountErrorKind

    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        runner: AccountTaskRunner,
        open_page: Callable[[str], bool],
        poll_interval_ms: int = POLL_INTERVAL_MS,
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._session = session
        self._runner = runner
        self._open_page = open_page
        self._clock = clock
        self._run = 0  # tells the answers of a cancelled run from the current one
        self._attempt: GoogleAttempt | None = None
        self._deadline = 0.0
        self._polling = False
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)

    @property
    def active(self) -> bool:
        return self._active

    def start(self, mode: GoogleMode) -> None:
        if self._active:
            return
        self._run += 1
        self._active = True
        self.starting.emit()
        run = self._run
        self._runner.run(
            StartGoogleWorker(self._client, self._session, mode),
            on_finished=partial(self._on_started, run),
            on_failed=partial(self._on_failed, run),
            on_waking=partial(self._on_waking, run),
        )

    def cancel(self) -> None:
        """Stop waiting. The backend keeps the attempt until it expires."""
        self._stop()
        self._run += 1

    def _stop(self) -> None:
        self._timer.stop()
        self._attempt = None
        self._polling = False
        self._active = False

    def _on_waking(self, run: int) -> None:
        if run == self._run:
            self.waking.emit()

    def _on_started(self, run: int, result: object) -> None:
        if run != self._run:
            return
        if not isinstance(result, GoogleAttempt):
            self._fail(AccountErrorKind.UNEXPECTED)
        elif not self._open_page(f"{BEGIN_PATH}{result.attempt_id}"):
            self._fail(AccountErrorKind.BROWSER_UNAVAILABLE)
        else:
            self._attempt = result
            self._deadline = self._clock() + result.expires_in
            self._timer.start()
            self.waiting.emit()

    def _poll(self) -> None:
        attempt = self._attempt
        if attempt is None or self._polling:
            return
        if self._clock() >= self._deadline:
            self._fail(AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED)
            return
        self._polling = True
        run = self._run
        self._runner.run(
            GoogleStatusWorker(self._client, self._session, attempt),
            on_finished=partial(self._on_status, run),
            on_failed=partial(self._on_failed, run),
        )

    def _on_status(self, run: int, result: object) -> None:
        status = result if isinstance(result, GoogleStatus) else None
        if run != self._run:
            self._drop_abandoned_session(status)
            return
        self._polling = False
        if status is None:
            self._fail(AccountErrorKind.UNEXPECTED)
        elif status.state is GoogleState.LINKED:
            self._stop()
            self.linked.emit()
        elif status.state is GoogleState.SIGNED_IN and status.session is not None:
            self._stop()
            self.signed_in.emit(status.session)

    def _drop_abandoned_session(self, status: GoogleStatus | None) -> None:
        """A poll answered after Cancel and signed in anyway: undo it."""
        if status is not None and status.session is not None and not self._active:
            self._session.sign_out()

    def _on_failed(self, run: int, kind: AccountErrorKind) -> None:
        if run == self._run:
            self._fail(kind)

    def _fail(self, kind: AccountErrorKind) -> None:
        self._stop()
        self.failed.emit(kind)
