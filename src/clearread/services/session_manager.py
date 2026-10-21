"""Keeps the current idToken fresh and hands it to the calls that need it.

Shared by the account worker pool and the AI pool, so the refresh is guarded by a lock:
two threads never spend the same refresh token twice.
"""

import threading
import time
from collections.abc import Callable
from typing import TypeVar

from clearread.services.account_client import (
    AccountClient,
    AccountError,
    AccountErrorKind,
)
from clearread.services.session_store import Session, SessionStore, StoredSession

T = TypeVar("T")

EXPIRY_MARGIN_SECONDS = 60.0


class SessionManager:
    def __init__(
        self,
        client: AccountClient,
        store: SessionStore,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._store = store
        self._clock = clock
        self._lock = threading.RLock()
        self._identity: StoredSession | None = None
        self._id_token = ""
        self._expires_at = 0.0

    @property
    def identity(self) -> StoredSession | None:
        return self._identity

    def resume(self) -> StoredSession | None:
        """Load the saved session without touching the network (offline start)."""
        with self._lock:
            self._identity = self._store.load()
            self._id_token = ""
            return self._identity

    def start(self, session: Session) -> None:
        with self._lock:
            self._apply(session)

    def sign_out(self) -> None:
        with self._lock:
            self._identity = None
            self._id_token = ""
            self._expires_at = 0.0
            try:
                self._store.clear()
            except OSError:
                # A locked file must not stop the sign-out; the stale session fails
                # to refresh at the next start and the login screen shows then.
                pass

    def refresh(self) -> Session:
        """Raises AccountError; a revoked refresh token also signs the user out."""
        with self._lock:
            if self._identity is None:
                raise AccountError(AccountErrorKind.SESSION_REVOKED)
            try:
                session = self._client.refresh(self._identity.refresh_token)
            except AccountError as error:
                if error.kind is AccountErrorKind.SESSION_REVOKED:
                    self.sign_out()
                raise
            self._apply(session)
            return session

    def renew(self) -> bool:
        try:
            self.refresh()
        except AccountError:
            return False
        return True

    def bearer(self) -> str | None:
        if self._identity is None:
            return None
        try:
            return self._valid_token()
        except AccountError:
            return None

    def run_authorized(self, call: Callable[[str], T]) -> T:
        """Run ``call(idToken)``; on invalid_session refresh once and retry once."""
        if self._identity is None:
            raise AccountError(AccountErrorKind.SESSION_REVOKED)
        try:
            return call(self._valid_token())
        except AccountError as error:
            if error.kind is not AccountErrorKind.INVALID_SESSION:
                raise
        return call(self.refresh().id_token)

    def _valid_token(self) -> str:
        with self._lock:
            if (
                self._id_token
                and self._clock() < self._expires_at - EXPIRY_MARGIN_SECONDS
            ):
                return self._id_token
            return self.refresh().id_token

    def _apply(self, session: Session) -> None:
        self._identity = StoredSession(
            session.uid, session.email, session.display_name, session.refresh_token
        )
        self._id_token = session.id_token
        self._expires_at = session.expires_at
        try:
            self._store.save(self._identity)
        except OSError:
            pass  # without the file the user signs in again next time; this run goes on
