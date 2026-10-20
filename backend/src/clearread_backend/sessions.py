"""Verification of the caller's Firebase ID token, cached in memory."""

import base64
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from clearread_backend.errors import ApiError
from clearread_backend.firebase import AccountInfo, FirebaseAuthGateway, Tokens
from clearread_backend.models import SessionResponse

MAX_CACHE_TTL_S = 3600.0
# Used when the token's expiry cannot be read; short, so a revocation bites soon.
UNKNOWN_EXPIRY_TTL_S = 60.0
CACHE_MAX_ENTRIES = 1000


@dataclass(frozen=True)
class Principal:
    """A verified caller; the token is kept to act on Firestore as that user."""

    info: AccountInfo
    id_token: str


def bearer_token(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "invalid_session")
    return token.strip()


def token_expiry(id_token: str) -> float | None:
    """Read the ``exp`` claim without verifying it; Firebase's lookup does that."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        return float(claims["exp"])
    except (IndexError, ValueError, KeyError, TypeError):
        return None


class TokenVerifier:
    """Checks tokens with ``accounts:lookup`` and remembers the answer."""

    def __init__(
        self,
        gateway: FirebaseAuthGateway,
        clock: Callable[[], float] = time.time,
        max_entries: int = CACHE_MAX_ENTRIES,
    ) -> None:
        self._gateway = gateway
        self._clock = clock
        self._max_entries = max_entries
        self._entries: OrderedDict[str, tuple[float, AccountInfo]] = OrderedDict()

    async def verify(self, id_token: str) -> AccountInfo:
        key = hashlib.sha256(id_token.encode()).hexdigest()
        now = self._clock()
        cached = self._entries.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]
        info = await self._gateway.lookup(id_token)
        self._remember(key, now + self._ttl(id_token, now), info)
        return info

    def forget(self, id_token: str) -> None:
        self._entries.pop(hashlib.sha256(id_token.encode()).hexdigest(), None)

    def _ttl(self, id_token: str, now: float) -> float:
        expiry = token_expiry(id_token)
        remaining = UNKNOWN_EXPIRY_TTL_S if expiry is None else expiry - now
        return min(remaining, MAX_CACHE_TTL_S)

    def _remember(self, key: str, expires_at: float, info: AccountInfo) -> None:
        self._entries[key] = (expires_at, info)
        self._entries.move_to_end(key)
        if len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)


async def session_response(verifier: TokenVerifier, tokens: Tokens) -> SessionResponse:
    # The lookup also tells whether Google is linked; a missing list means "not linked".
    info = await verifier.verify(tokens.id_token)
    return SessionResponse(
        uid=info.uid,
        email=info.email,
        display_name=info.display_name,
        email_verified=info.email_verified,
        id_token=tokens.id_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        google_linked=info.google_linked,
    )
