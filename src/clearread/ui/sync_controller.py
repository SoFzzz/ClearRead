"""Keeps the synced profile (settings, words, topics) in step with the account (v1.6).

Lives on the main thread: the network part runs in ``SyncProfileWorker`` and its result
is applied here. A local change is pushed a few seconds after the last one, and again when
the network comes back.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from clearread.core.config import AppConfig
from clearread.services.account_client import AccountClient, AccountErrorKind
from clearread.services.glossary import GlossaryStore
from clearread.services.groups import GroupStore
from clearread.services.profile_sync import (
    SyncAction,
    SyncResult,
    SyncStateStore,
    apply_sync_result,
    build_profile,
    utc_timestamp,
)
from clearread.services.session_manager import SessionManager
from clearread.ui.account_state import SyncStatus
from clearread.workers.account_tasks import AccountTaskRunner
from clearread.workers.account_worker import SyncProfileWorker

DEBOUNCE_MS = 3000
RETRY_MS = 60_000
FLUSH_WAIT_MS = 5000
_LATER_KINDS = (
    AccountErrorKind.NO_NETWORK,
    AccountErrorKind.TIMEOUT,
    AccountErrorKind.SERVER_WAKING,
)
_ENDED_KINDS = (AccountErrorKind.SESSION_REVOKED, AccountErrorKind.INVALID_SESSION)


class SyncController(QObject):
    status_changed = Signal(object)  # SyncStatus
    config_pulled = Signal(object)  # AppConfig: the account's settings won
    session_ended = Signal()  # the account no longer accepts this session

    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        runner: AccountTaskRunner,
        state: SyncStateStore,
        config_source: Callable[[], AppConfig],
        glossary: GlossaryStore,
        topics: GroupStore,
        online: bool = True,
        debounce_ms: int = DEBOUNCE_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._session = session
        self._runner = runner
        self._state = state
        self._config_source = config_source
        self._glossary = glossary
        self._topics = topics
        self._online = online
        self._debounce_ms = debounce_ms
        self._status = SyncStatus.PENDING
        self._in_flight = False
        self._changed_in_flight = False
        self._resync = False
        self._suspended = False
        self._closed = False
        self._flush_waiters: list[Callable[[], None]] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.sync_now)

    @property
    def status(self) -> SyncStatus:
        return self._status

    @property
    def has_unsaved_changes(self) -> bool:
        return self._status is not SyncStatus.OK

    def notify_changed(self) -> None:
        """Call after any local change of settings, words or topics."""
        self._state.touch()
        if self._in_flight:
            self._changed_in_flight = True
        self._set_status(SyncStatus.PENDING)
        self._timer.start(self._debounce_ms)

    def set_online(self, online: bool) -> None:
        self._online = online
        if online and self._status is not SyncStatus.OK:
            self.sync_now()

    def suspend(self) -> None:
        """Stop pushing, e.g. while the account is being deleted."""
        self._suspended = True
        self._timer.stop()

    def resume(self) -> None:
        self._suspended = False
        if self._status is not SyncStatus.OK:
            self._timer.start(self._debounce_ms)

    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()

    def sync_now(self) -> None:
        if self._closed or self._suspended:
            return
        if not self._online:
            self._set_status(SyncStatus.PENDING)
            return
        if self._in_flight:
            self._resync = True
            return
        self._timer.stop()
        self._start_worker()

    def flush(self, done: Callable[[], None]) -> None:
        """Push what is pending, then call ``done`` once (also if it takes too long)."""
        if not self.has_unsaved_changes or not self._online or self._closed:
            done()
            return
        called: list[bool] = []

        def once() -> None:
            if not called:
                called.append(True)
                done()

        self._flush_waiters.append(once)
        QTimer.singleShot(FLUSH_WAIT_MS, once)
        self.sync_now()

    def _start_worker(self) -> None:
        local = build_profile(
            self._config_source(),
            self._glossary.entries(),
            self._topics.groups(),
            self._state.updated_at(),
        )
        self._in_flight = True
        self._changed_in_flight = False
        worker = SyncProfileWorker(self._client, self._session, local, utc_timestamp())
        self._runner.run(worker, self._on_synced, self._on_failed)

    def _on_synced(self, result: object) -> None:
        self._in_flight = False
        if self._closed or not isinstance(result, SyncResult):
            return
        if self._changed_in_flight:
            # The change made meanwhile is newer than what the account answered.
            self._state.touch()
            self._timer.start(self._debounce_ms)
            self._finish_round(SyncStatus.PENDING)
            return
        config = apply_sync_result(
            result, self._state, self._config_source(), self._glossary, self._topics
        )
        if result.action is SyncAction.PULL:
            self.config_pulled.emit(config)
        self._finish_round(SyncStatus.OK)

    def _on_failed(self, kind: AccountErrorKind) -> None:
        self._in_flight = False
        if self._closed:
            return
        if kind in _ENDED_KINDS:
            self.session_ended.emit()
            return
        if kind not in _LATER_KINDS:
            self._timer.start(RETRY_MS)
        self._finish_round(
            SyncStatus.PENDING if kind in _LATER_KINDS else SyncStatus.FAILED
        )

    def _finish_round(self, status: SyncStatus) -> None:
        self._set_status(status)
        if self._resync:
            self._resync = False
            self.sync_now()
            return
        waiters, self._flush_waiters = self._flush_waiters, []
        for waiter in waiters:
            waiter()

    def _set_status(self, status: SyncStatus) -> None:
        if status is not self._status:
            self._status = status
            self.status_changed.emit(status)
