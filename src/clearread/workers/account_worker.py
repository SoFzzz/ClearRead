"""Workers that run account and sync calls off the UI thread (v1.6).

Same pattern as ai_worker: dispatched onto a dedicated QThreadPool with
maxThreadCount=1, so the calls are serialized and never race on the session.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from clearread.services.account_client import (
    AccountClient,
    AccountError,
    AccountErrorKind,
    GoogleAttempt,
    GoogleMode,
    RemoteProfile,
)
from clearread.services.profile_sync import run_sync
from clearread.services.session_manager import SessionManager


def create_account_thread_pool() -> QThreadPool:
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    return pool


class AccountWorkerSignals(QObject):
    waking = Signal()  # the backend is starting up
    # object: Session, SyncResult or None, depending on the worker. PySide6 does not
    # handle plain Enum members reliably, so failures are objects too.
    finished = Signal(object)
    failed = Signal(object)  # AccountErrorKind


class _AccountWorker(QRunnable):
    def __init__(
        self,
        client: AccountClient,
        call: Callable[[], object],
        wake_backend: bool = True,
    ) -> None:
        super().__init__()
        self.signals = AccountWorkerSignals()
        self._client = client
        self._call = call
        self._wake_backend = wake_backend

    def run(self) -> None:
        try:
            if self._wake_backend:
                self._client.ensure_awake(self.signals.waking.emit)
            self.signals.finished.emit(self._call())
        except AccountError as exc:
            self.signals.failed.emit(exc.kind)
        except Exception:  # noqa: BLE001 - the UI must never wait on an unexpected failure
            self.signals.failed.emit(AccountErrorKind.UNEXPECTED)


class SignInWorker(_AccountWorker):
    def __init__(
        self, client: AccountClient, session: SessionManager, email: str, password: str
    ) -> None:
        super().__init__(client, lambda: self._sign_in(session, email, password))

    def _sign_in(self, session: SessionManager, email: str, password: str) -> object:
        result = self._client.sign_in(email, password)
        session.start(result)
        return result


class RegisterWorker(_AccountWorker):
    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        email: str,
        password: str,
        display_name: str,
    ) -> None:
        super().__init__(
            client, lambda: self._register(session, email, password, display_name)
        )

    def _register(
        self, session: SessionManager, email: str, password: str, display_name: str
    ) -> object:
        result = self._client.register(email, password, display_name)
        session.start(result)
        return result


class PasswordResetWorker(_AccountWorker):
    def __init__(self, client: AccountClient, email: str) -> None:
        super().__init__(client, lambda: client.request_password_reset(email))


class RefreshSessionWorker(_AccountWorker):
    """Startup refresh in the background; failures leave the app working offline."""

    def __init__(self, client: AccountClient, session: SessionManager) -> None:
        super().__init__(client, session.refresh)


class SyncProfileWorker(_AccountWorker):
    def __init__(
        self,
        client: AccountClient,
        session: SessionManager,
        local: RemoteProfile,
        now: str,
    ) -> None:
        super().__init__(
            client,
            lambda: session.run_authorized(
                lambda token: run_sync(client, token, local, now)
            ),
        )


class DeleteAccountWorker(_AccountWorker):
    def __init__(self, client: AccountClient, session: SessionManager) -> None:
        super().__init__(client, lambda: self._delete(session))

    def _delete(self, session: SessionManager) -> None:
        session.run_authorized(self._client.delete_account)
        session.sign_out()


class StartGoogleWorker(_AccountWorker):
    """Opens a Google attempt; linking needs the signed-in user's token."""

    def __init__(
        self, client: AccountClient, session: SessionManager, mode: GoogleMode
    ) -> None:
        super().__init__(client, lambda: self._start(session, mode))

    def _start(self, session: SessionManager, mode: GoogleMode) -> object:
        if mode is GoogleMode.LINK:
            return session.run_authorized(
                lambda token: self._client.start_google(mode, token)
            )
        return self._client.start_google(mode, None)


class GoogleStatusWorker(_AccountWorker):
    """One poll. A finished sign in is stored like an email sign in (SignInWorker).

    Polls skip the wake-up probe: the start call already woke the backend, and a
    probe every 2 s would double the traffic.
    """

    def __init__(
        self, client: AccountClient, session: SessionManager, attempt: GoogleAttempt
    ) -> None:
        super().__init__(
            client, lambda: self._poll(session, attempt), wake_backend=False
        )

    def _poll(self, session: SessionManager, attempt: GoogleAttempt) -> object:
        status = self._client.google_status(attempt.attempt_id, attempt.poll_token)
        if status.session is not None:
            session.start(status.session)
        return status
