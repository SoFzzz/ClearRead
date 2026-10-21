"""Accounts and synced profile against the ClearRead backend (v1.6).

Blocking: call it only from workers. Errors are chosen by HTTP status and the backend's
own stable error code, never by reading text; the visible messages live in ui/strings.py.
"""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from clearread.services.backend_transport import (
    BackendReply,
    BackendTransport,
    TransportError,
    TransportErrorKind,
)
from clearread.services.session_store import Session

WAKE_TIMEOUT_SECONDS = 60.0
WAKE_POLL_SECONDS = 2.0
# Both ids go into a URL path, so only URL-safe base64 characters are accepted.
_URL_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


class AccountErrorKind(Enum):
    NO_NETWORK = "no_network"
    SERVER_WAKING = "server_waking"
    TIMEOUT = "timeout"
    EMAIL_EXISTS = "email_exists"
    INVALID_CREDENTIALS = "invalid_credentials"
    PASSWORD_TOO_SHORT = "password_too_short"
    PASSWORD_TOO_LONG = "password_too_long"
    INVALID_EMAIL = "invalid_email"
    EMAIL_TOO_LONG = "email_too_long"
    NAME_TOO_LONG = "name_too_long"
    INVALID_REQUEST = "invalid_request"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    INVALID_SESSION = "invalid_session"
    SESSION_REVOKED = "session_revoked"
    PROFILE_TOO_LARGE = "profile_too_large"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNEXPECTED = "unexpected"
    GOOGLE_CANCELLED = "google_cancelled"
    GOOGLE_ALREADY_LINKED = "google_already_linked"
    GOOGLE_NOT_LINKED = "google_not_linked"
    GOOGLE_ATTEMPT_NOT_FOUND = "google_attempt_not_found"
    GOOGLE_ATTEMPT_EXPIRED = "google_attempt_expired"
    GOOGLE_NOT_CONFIGURED = "google_not_configured"
    BROWSER_UNAVAILABLE = "browser_unavailable"


class AccountError(Exception):
    def __init__(self, kind: AccountErrorKind) -> None:
        self.kind = kind
        super().__init__(kind.value)


class GoogleMode(Enum):
    LINK = "link"
    SIGN_IN = "sign_in"


class GoogleState(Enum):
    PENDING = "pending"
    LINKED = "linked"
    SIGNED_IN = "signed_in"


@dataclass(frozen=True)
class GoogleAttempt:
    attempt_id: str
    poll_token: str
    expires_in: float  # seconds


@dataclass(frozen=True)
class GoogleStatus:
    state: GoogleState
    session: Session | None = None  # only with SIGNED_IN


@dataclass(frozen=True)
class RemoteProfile:
    settings: dict[str, Any]
    words: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    updated_at: str  # RFC 3339


# The backend's own stable codes (brief v1.6); Firebase text never reaches the app.
_CODE_TO_KIND: dict[str, AccountErrorKind] = {
    "email_exists": AccountErrorKind.EMAIL_EXISTS,
    "invalid_credentials": AccountErrorKind.INVALID_CREDENTIALS,
    "password_too_short": AccountErrorKind.PASSWORD_TOO_SHORT,
    "password_too_long": AccountErrorKind.PASSWORD_TOO_LONG,
    "invalid_email": AccountErrorKind.INVALID_EMAIL,
    "email_too_long": AccountErrorKind.EMAIL_TOO_LONG,
    "name_too_long": AccountErrorKind.NAME_TOO_LONG,
    "invalid_request": AccountErrorKind.INVALID_REQUEST,
    "too_many_attempts": AccountErrorKind.TOO_MANY_ATTEMPTS,
    "invalid_session": AccountErrorKind.INVALID_SESSION,
    "session_revoked": AccountErrorKind.SESSION_REVOKED,
    "profile_too_large": AccountErrorKind.PROFILE_TOO_LARGE,
    "google_cancelled": AccountErrorKind.GOOGLE_CANCELLED,
    "google_already_linked": AccountErrorKind.GOOGLE_ALREADY_LINKED,
    "google_not_linked": AccountErrorKind.GOOGLE_NOT_LINKED,
    "google_attempt_not_found": AccountErrorKind.GOOGLE_ATTEMPT_NOT_FOUND,
    "google_attempt_expired": AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED,
    "google_not_configured": AccountErrorKind.GOOGLE_NOT_CONFIGURED,
    "auth_upstream_error": AccountErrorKind.SERVICE_UNAVAILABLE,
    "auth_upstream_timeout": AccountErrorKind.TIMEOUT,
}
# Fallback when the body has no known code (e.g. an error page from the host's proxy).
_STATUS_TO_KIND: dict[int, AccountErrorKind] = {
    410: AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED,
    413: AccountErrorKind.PROFILE_TOO_LARGE,
    422: AccountErrorKind.INVALID_REQUEST,
    429: AccountErrorKind.TOO_MANY_ATTEMPTS,
    502: AccountErrorKind.SERVICE_UNAVAILABLE,
    503: AccountErrorKind.SERVICE_UNAVAILABLE,
    504: AccountErrorKind.TIMEOUT,
}


def kind_for_error(reply: BackendReply) -> AccountErrorKind:
    if reply.error_code in _CODE_TO_KIND:
        return _CODE_TO_KIND[reply.error_code]
    return _STATUS_TO_KIND.get(reply.status, AccountErrorKind.UNEXPECTED)


class AccountClient:
    def __init__(
        self,
        backend: BackendTransport,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._backend = backend
        self._clock = clock

    def ensure_awake(self, on_waking: Callable[[], None]) -> None:
        try:
            awake = self._backend.wait_until_awake(
                on_waking, WAKE_TIMEOUT_SECONDS, WAKE_POLL_SECONDS
            )
        except TransportError as exc:
            raise _from_transport(exc) from exc
        if not awake:
            raise AccountError(AccountErrorKind.SERVER_WAKING)

    def register(self, email: str, password: str, display_name: str) -> Session:
        body = {"email": email, "password": password, "display_name": display_name}
        reply = self._send("POST", "/v1/auth/register", body)
        return self._session(self._expect(reply, 201))

    def sign_in(self, email: str, password: str) -> Session:
        reply = self._send(
            "POST", "/v1/auth/login", {"email": email, "password": password}
        )
        return self._session(self._expect(reply, 200))

    def refresh(self, refresh_token: str) -> Session:
        reply = self._send("POST", "/v1/auth/refresh", {"refresh_token": refresh_token})
        return self._session(self._expect(reply, 200))

    def request_password_reset(self, email: str) -> None:
        reply = self._send("POST", "/v1/auth/password-reset", {"email": email})
        self._expect(reply, 204)

    def delete_account(self, id_token: str, password: str) -> None:
        reply = self._send(
            "DELETE", "/v1/account", {"password": password}, bearer=id_token
        )
        self._expect(reply, 204)

    def fetch_profile(self, id_token: str) -> RemoteProfile | None:
        reply = self._send("GET", "/v1/profile", bearer=id_token)
        if reply.status == 404:
            return None
        return _parse_profile(self._expect(reply, 200))

    def push_profile(self, id_token: str, profile: RemoteProfile) -> RemoteProfile:
        body = {
            "settings": profile.settings,
            "words": profile.words,
            "topics": profile.topics,
            "updated_at": profile.updated_at,
        }
        reply = self._send("PUT", "/v1/profile", body, bearer=id_token)
        return _parse_profile(self._expect(reply, 200))

    def start_google(self, mode: GoogleMode, bearer: str | None) -> GoogleAttempt:
        reply = self._send(
            "POST", "/v1/auth/google/start", {"mode": mode.value}, bearer=bearer
        )
        return _parse_attempt(self._expect(reply, 200))

    def google_status(self, attempt_id: str, poll_token: str) -> GoogleStatus:
        if _URL_SAFE_ID.fullmatch(attempt_id) is None:
            raise AccountError(AccountErrorKind.UNEXPECTED)
        reply = self._send(
            "GET",
            f"/v1/auth/google/status/{attempt_id}",
            headers={"X-Poll-Token": poll_token},
        )
        return self._parse_status(self._expect(reply, 200))

    def _parse_status(self, body: Any) -> GoogleStatus:
        try:
            state = GoogleState(body["status"])
        except (KeyError, TypeError, ValueError):
            raise AccountError(AccountErrorKind.UNEXPECTED) from None
        if state is GoogleState.SIGNED_IN:
            session = self._session(body.get("session"))
            return GoogleStatus(state, session)
        return GoogleStatus(state)

    def _send(
        self,
        method: str,
        path: str,
        body: object | None = None,
        bearer: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> BackendReply:
        try:
            return self._backend.request(
                method, path, body, bearer, extra_headers=headers
            )
        except TransportError as exc:
            raise _from_transport(exc) from exc

    @staticmethod
    def _expect(reply: BackendReply, status: int) -> Any:
        if reply.status != status:
            raise AccountError(kind_for_error(reply))
        return reply.body

    def _session(self, body: Any) -> Session:
        if not isinstance(body, dict):
            raise AccountError(AccountErrorKind.UNEXPECTED)
        try:
            return Session(
                uid=_text(body["uid"]),
                email=_text(body["email"]),
                display_name=_text(body["display_name"], allow_empty=True),
                email_verified=_flag(body["email_verified"]),
                id_token=_text(body["id_token"]),
                refresh_token=_text(body["refresh_token"]),
                expires_at=self._clock() + _seconds(body["expires_in"]),
                google_linked=_flag(body.get("google_linked", False)),
            )
        except (KeyError, TypeError):
            raise AccountError(AccountErrorKind.UNEXPECTED) from None


def _from_transport(error: TransportError) -> AccountError:
    if error.kind is TransportErrorKind.TIMEOUT:
        return AccountError(AccountErrorKind.TIMEOUT)
    return AccountError(AccountErrorKind.NO_NETWORK)


def _text(value: object, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or not (value or allow_empty):
        raise TypeError("expected a string")
    return value


def _flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError("expected a boolean")
    return value


def _seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("expected a number")
    return float(value)


def _parse_attempt(body: Any) -> GoogleAttempt:
    try:
        attempt_id = _text(body["attempt_id"])
        poll_token = _text(body["poll_token"])
        expires_in = _seconds(body["expires_in"])
    except (KeyError, TypeError):
        raise AccountError(AccountErrorKind.UNEXPECTED) from None
    if _URL_SAFE_ID.fullmatch(attempt_id) is None or expires_in <= 0:
        raise AccountError(AccountErrorKind.UNEXPECTED)
    return GoogleAttempt(attempt_id, poll_token, expires_in)


def _parse_profile(body: Any) -> RemoteProfile:
    if not isinstance(body, dict):
        raise AccountError(AccountErrorKind.UNEXPECTED)
    settings, words, topics = (
        body.get("settings"),
        body.get("words"),
        body.get("topics"),
    )
    updated_at = body.get("updated_at")
    if (
        not isinstance(settings, dict)
        or not isinstance(words, list)
        or not isinstance(topics, list)
        or not isinstance(updated_at, str)
    ):
        raise AccountError(AccountErrorKind.UNEXPECTED)
    return RemoteProfile(settings, words, topics, updated_at)
