"""Link or sign in with Google through the backend (spec §4.14.11).

The app only opens ``/begin`` in the system browser and then polls ``/status``.
Nothing received here (codes, state, verifiers, tokens, emails) is ever logged.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from clearread_backend.errors import ApiError
from clearread_backend.firebase import FirebaseAuthGateway, FirestoreGateway
from clearread_backend.google_oauth import GoogleOAuthGateway
from clearread_backend.models import SessionResponse
from clearread_backend.sessions import TokenVerifier, bearer_token, session_response

ATTEMPT_TTL_S = 600
MAX_LIVE_ATTEMPTS = 100
GOOGLE_ROUTE_PREFIX = "/v1/auth/google/"
# Never cached and never leaking the URL (it carries the attempt id or the state).
SAFE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
PAGE_HEADERS = SAFE_HEADERS | {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"
}

# The only user-visible text in the backend; identical for every outcome on purpose.
CALLBACK_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClearRead</title>
<style>
body{font-family:Segoe UI,Arial,sans-serif;background:#fff;color:#392f5a;
max-width:32rem;margin:15vh auto;padding:0 1.5rem;line-height:1.6}
h1{font-size:1.4rem}hr{border:0;border-top:1px solid #392f5a;margin:2rem 0}
</style>
</head>
<body>
<h1>Listo. Ya puedes volver a ClearRead.</h1>
<p>Puedes cerrar esta pestaña. Si algo falló, la app te lo dirá.</p>
<hr>
<h1 lang="en">Done. You can go back to ClearRead.</h1>
<p lang="en">You can close this tab. If something went wrong, the app will tell you.</p>
</body>
</html>
"""

logger = logging.getLogger("clearread_backend")

Mode = Literal["link", "sign_in"]
Clock = Callable[[], float]
Requirement = Callable[[], Awaitable[None] | None]


class StartRequest(BaseModel):
    mode: Mode


class StartResponse(BaseModel):
    attempt_id: str
    poll_token: str
    expires_in: int


class StatusResponse(BaseModel):
    status: Literal["pending", "linked", "signed_in"]
    session: SessionResponse | None = None


@dataclass
class Attempt:
    mode: Mode
    expires_at: float
    poll_digest: bytes
    link_id_token: str = ""
    code_verifier: str = ""
    state: str = ""
    begun: bool = False
    status: Literal["pending", "linked", "signed_in", "failed"] = "pending"
    session: SessionResponse | None = None
    error: tuple[int, str] | None = None


@dataclass(frozen=True)
class BeginData:
    state: str
    code_verifier: str


def _digest(poll_token: str) -> bytes:
    return hashlib.sha256(poll_token.encode()).digest()


@dataclass
class GoogleAttemptStore:
    """In-memory attempts: one instance, lost on restart (the app says "try again")."""

    clock: Clock = time.time
    ttl_s: int = ATTEMPT_TTL_S
    max_live: int = MAX_LIVE_ATTEMPTS
    _attempts: dict[str, Attempt] = field(default_factory=dict)
    _by_state: dict[str, str] = field(default_factory=dict)

    def create(self, mode: Mode, link_id_token: str) -> tuple[str, str]:
        self._purge()
        if len(self._attempts) >= self.max_live:
            raise ApiError(429, "too_many_attempts")
        attempt_id = secrets.token_urlsafe(16)
        poll_token = secrets.token_urlsafe(32)
        self._attempts[attempt_id] = Attempt(
            mode=mode,
            expires_at=self.clock() + self.ttl_s,
            poll_digest=_digest(poll_token),
            link_id_token=link_id_token,
        )
        return attempt_id, poll_token

    def begin(self, attempt_id: str) -> BeginData:
        attempt = self._live(attempt_id)
        if attempt.begun:
            raise ApiError(404, "google_attempt_not_found")
        attempt.begun = True
        attempt.code_verifier = secrets.token_urlsafe(48)
        attempt.state = secrets.token_urlsafe(32)
        self._by_state[attempt.state] = attempt_id
        return BeginData(attempt.state, attempt.code_verifier)

    def take_by_state(self, state: str) -> Attempt | None:
        """Find the attempt of a callback; a state works only once."""
        attempt_id = self._by_state.pop(state, None)
        attempt = self._attempts.get(attempt_id or "")
        if attempt is None or self.clock() >= attempt.expires_at:
            return None
        return attempt

    def read(self, attempt_id: str, poll_token: str) -> Attempt:
        """Return an attempt to its owner; a finished one is deleted by this read."""
        attempt = self._attempts.get(attempt_id)
        if attempt is None or not hmac.compare_digest(
            attempt.poll_digest, _digest(poll_token)
        ):
            raise ApiError(404, "google_attempt_not_found")
        if self.clock() >= attempt.expires_at:
            self._drop(attempt_id)
            raise ApiError(410, "google_attempt_expired")
        if attempt.status != "pending":
            self._drop(attempt_id)
        return attempt

    def _live(self, attempt_id: str) -> Attempt:
        attempt = self._attempts.get(attempt_id)
        if attempt is None:
            raise ApiError(404, "google_attempt_not_found")
        if self.clock() >= attempt.expires_at:
            self._drop(attempt_id)
            raise ApiError(410, "google_attempt_expired")
        return attempt

    def _purge(self) -> None:
        now = self.clock()
        expired = [
            key for key, item in self._attempts.items() if item.expires_at <= now
        ]
        for attempt_id in expired:
            self._drop(attempt_id)

    def _drop(self, attempt_id: str) -> None:
        attempt = self._attempts.pop(attempt_id, None)
        if attempt is not None:
            self._by_state.pop(attempt.state, None)


def pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class RedactGoogleAccessLog(logging.Filter):
    """Hide attempt ids, codes and states from uvicorn's access log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path = args[2].partition("?")[0]
            if path.startswith(GOOGLE_ROUTE_PREFIX):
                kind = path[len(GOOGLE_ROUTE_PREFIX) :].split("/")[0]
                hidden = f"{GOOGLE_ROUTE_PREFIX}{kind}/[hidden]"
                record.args = (*args[:2], hidden, *args[3:])
        return True


def create_google_router(
    auth: FirebaseAuthGateway,
    firestore: FirestoreGateway,
    google: GoogleOAuthGateway,
    attempts: GoogleAttemptStore,
    verifier: TokenVerifier,
    redirect_uri: str,
    require_configured: Requirement,
) -> APIRouter:
    router = APIRouter()
    configured = [Depends(require_configured)]

    async def signed_in_session(google_id_token: str) -> SessionResponse:
        result = await auth.sign_in_with_idp(google_id_token, redirect_uri)
        if result.tokens is None or result.need_confirmation:
            raise ApiError(403, "google_not_linked")
        if result.is_new_user:
            # Signing in must never create a profile: remove the account Firebase made.
            try:
                await auth.delete_user(result.tokens.id_token)
            except ApiError:
                logger.error("google_orphan_user")
            raise ApiError(403, "google_not_linked")
        # Firebase may hand back an existing account that has the same email but never
        # linked Google; only the marker written by a successful link lets it in.
        tokens = result.tokens
        if not await firestore.has_google_link(tokens.uid, tokens.id_token):
            raise ApiError(403, "google_not_linked")
        return await session_response(verifier, tokens)

    async def link_google(attempt: Attempt, google_id_token: str) -> None:
        caller = await verifier.verify(attempt.link_id_token)
        try:
            await auth.sign_in_with_idp(
                google_id_token, redirect_uri, attempt.link_id_token
            )
        except ApiError as exc:
            if exc.code != "google_already_linked" or not await owns_google(
                google_id_token, caller.uid
            ):
                raise
        await firestore.mark_google_linked(caller.uid, attempt.link_id_token)

    async def owns_google(google_id_token: str, uid: str) -> bool:
        """Whether this Google account already belongs to ``uid`` (a retried link)."""
        try:
            result = await auth.sign_in_with_idp(google_id_token, redirect_uri)
        except ApiError:
            return False
        if result.tokens is None:
            return False
        if result.is_new_user:
            try:
                await auth.delete_user(result.tokens.id_token)
            except ApiError:
                logger.error("google_orphan_user")
            return False
        return result.tokens.uid == uid

    async def finish(attempt: Attempt, google_id_token: str) -> None:
        if attempt.mode == "link":
            await link_google(attempt, google_id_token)
            verifier.forget(attempt.link_id_token)
            attempt.status = "linked"
            return
        try:
            attempt.session = await signed_in_session(google_id_token)
        except ApiError as exc:
            # EMAIL_EXISTS on sign-in means the Google account is not linked to us.
            if exc.code == "google_already_linked":
                raise ApiError(403, "google_not_linked") from None
            raise
        attempt.status = "signed_in"

    async def run_callback(attempt: Attempt, code: str) -> None:
        try:
            google_id_token = await google.exchange_code(
                code, attempt.code_verifier, redirect_uri
            )
            await finish(attempt, google_id_token)
        except ApiError as exc:
            attempt.status, attempt.error = "failed", (exc.status_code, exc.code)
        except Exception:
            logger.error("google callback failed: auth_upstream_error")
            attempt.status, attempt.error = "failed", (502, "auth_upstream_error")
        finally:
            attempt.link_id_token = ""
            attempt.code_verifier = ""

    @router.post("/v1/auth/google/start", dependencies=configured)
    async def start(
        body: StartRequest, authorization: Annotated[str, Header()] = ""
    ) -> StartResponse:
        token = ""
        if body.mode == "link":
            token = bearer_token(authorization)
            await verifier.verify(token)
        attempt_id, poll_token = attempts.create(body.mode, token)
        return StartResponse(
            attempt_id=attempt_id, poll_token=poll_token, expires_in=ATTEMPT_TTL_S
        )

    @router.get("/v1/auth/google/begin/{attempt_id}", dependencies=configured)
    async def begin(attempt_id: str) -> RedirectResponse:
        data = attempts.begin(attempt_id)
        url = google.authorization_url(
            redirect_uri, data.state, pkce_challenge(data.code_verifier)
        )
        return RedirectResponse(url, status_code=302, headers=SAFE_HEADERS)

    @router.get("/v1/auth/google/callback", dependencies=configured)
    async def callback(
        code: Annotated[str, Query()] = "",
        state: Annotated[str, Query()] = "",
        error: Annotated[str, Query()] = "",
    ) -> HTMLResponse:
        attempt = attempts.take_by_state(state)
        if attempt is None:
            return HTMLResponse(CALLBACK_PAGE, 400, PAGE_HEADERS)
        if error:
            attempt.status, attempt.error = "failed", (409, "google_cancelled")
        elif not code:
            attempt.status, attempt.error = "failed", (502, "auth_upstream_error")
        else:
            await run_callback(attempt, code)
        return HTMLResponse(CALLBACK_PAGE, 200, PAGE_HEADERS)

    @router.get("/v1/auth/google/status/{attempt_id}", response_model_exclude_none=True)
    async def status(
        attempt_id: str, x_poll_token: Annotated[str, Header()] = ""
    ) -> StatusResponse:
        attempt = attempts.read(attempt_id, x_poll_token)
        if attempt.status == "failed" and attempt.error is not None:
            raise ApiError(*attempt.error)
        return StatusResponse(status=attempt.status, session=attempt.session)

    return router
