"""Runs account workers on the dedicated pool and answers on the main thread."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from PySide6.QtCore import QObject, QThreadPool, Slot

from clearread.services.account_client import AccountErrorKind
from clearread.workers.account_worker import (
    AccountWorkerSignals,
    DeleteAccountWorker,
    GoogleStatusWorker,
    PasswordResetWorker,
    RefreshSessionWorker,
    RegisterWorker,
    SignInWorker,
    StartGoogleWorker,
    SyncProfileWorker,
)

AccountTask: TypeAlias = (
    SignInWorker
    | RegisterWorker
    | PasswordResetWorker
    | RefreshSessionWorker
    | SyncProfileWorker
    | DeleteAccountWorker
    | StartGoogleWorker
    | GoogleStatusWorker
)


@dataclass(frozen=True)
class _Callbacks:
    on_finished: Callable[[object], None] | None
    on_failed: Callable[[AccountErrorKind], None] | None
    on_waking: Callable[[], None] | None


class AccountTaskRunner(QObject):
    def __init__(self, pool: QThreadPool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = pool
        # The signals live as long as their worker runs; this keeps them referenced.
        self._live: dict[QObject, _Callbacks] = {}

    def run(
        self,
        task: AccountTask,
        on_finished: Callable[[object], None] | None = None,
        on_failed: Callable[[AccountErrorKind], None] | None = None,
        on_waking: Callable[[], None] | None = None,
    ) -> None:
        signals: AccountWorkerSignals = task.signals
        self._live[signals] = _Callbacks(on_finished, on_failed, on_waking)
        signals.waking.connect(self._on_waking)
        signals.finished.connect(self._on_finished)
        signals.failed.connect(self._on_failed)
        self._pool.start(task)

    @Slot()
    def _on_waking(self) -> None:
        callbacks = self._live.get(self.sender())
        if callbacks is not None and callbacks.on_waking is not None:
            callbacks.on_waking()

    @Slot(object)
    def _on_finished(self, result: object) -> None:
        callbacks = self._live.pop(self.sender(), None)
        if callbacks is not None and callbacks.on_finished is not None:
            callbacks.on_finished(result)

    @Slot(object)
    def _on_failed(self, kind: AccountErrorKind) -> None:
        callbacks = self._live.pop(self.sender(), None)
        if callbacks is not None and callbacks.on_failed is not None:
            callbacks.on_failed(kind)
