"""Firebase Authentication and Cloud Firestore through their REST APIs.

Firebase error strings are translated to our own stable codes here; Firebase text
never reaches the app, and nothing received or sent is logged.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from clearread_backend.errors import ApiError
from clearread_backend.firestore_values import decode_fields, encode_fields
from clearread_backend.models import Profile

TIMEOUT_S = 10.0
IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1/accounts"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIRESTORE_URL = "https://firestore.googleapis.com/v1"
PROFILE_SCHEMA_VERSION = 1
# Outside the synced payload: only a successful Google link writes it (spec 4.14.11).
GOOGLE_LINK_FIELD = "google_linked_at"

logger = logging.getLogger("clearread_backend")
# httpx logs every request URL at INFO, and ours carry the Firebase API key.
logging.getLogger("httpx").setLevel(logging.WARNING)

_UPSTREAM_ERROR = (502, "auth_upstream_error")
# Only enum-shaped values are logged: anything else could be message text.
_GRPC_STATUS = re.compile(r"[A-Z_]{1,40}")
_ERROR_CODES: dict[str, tuple[int, str]] = {
    "EMAIL_EXISTS": (409, "email_exists"),
    "INVALID_EMAIL": (422, "invalid_request"),
    "WEAK_PASSWORD": (422, "password_too_short"),
    "TOO_MANY_ATTEMPTS_TRY_LATER": (429, "too_many_attempts"),
    # One answer for all four, so a caller cannot tell whether an email exists.
    "INVALID_LOGIN_CREDENTIALS": (401, "invalid_credentials"),
    "EMAIL_NOT_FOUND": (401, "invalid_credentials"),
    "INVALID_PASSWORD": (401, "invalid_credentials"),
    "USER_DISABLED": (401, "invalid_credentials"),
    "INVALID_ID_TOKEN": (401, "invalid_session"),
    "USER_NOT_FOUND": (401, "invalid_session"),
    "TOKEN_EXPIRED": (401, "invalid_session"),
    # Only a fresh sign-in fixes this one; a token refresh would not.
    "CREDENTIAL_TOO_OLD_LOGIN_AGAIN": (401, "session_revoked"),
    "INVALID_REFRESH_TOKEN": (401, "session_revoked"),
    "OPERATION_NOT_ALLOWED": _UPSTREAM_ERROR,
}
# Linking Google: an account that already belongs to someone else is not an outage.
_IDP_CODES = _ERROR_CODES | {
    "FEDERATED_USER_ID_ALREADY_LINKED": (409, "google_already_linked"),
    "EMAIL_EXISTS": (409, "google_already_linked"),
    "INVALID_IDP_RESPONSE": _UPSTREAM_ERROR,
}
GOOGLE_PROVIDER_ID = "google.com"
# A refresh token that cannot refresh means signing in again, whatever the cause.
_REFRESH_CODES = _ERROR_CODES | {
    "TOKEN_EXPIRED": (401, "session_revoked"),
    "USER_NOT_FOUND": (401, "session_revoked"),
    "USER_DISABLED": (401, "session_revoked"),
}


@dataclass(frozen=True)
class Tokens:
    uid: str
    id_token: str
    refresh_token: str
    expires_in: int


@dataclass(frozen=True)
class AccountInfo:
    uid: str
    email: str
    email_verified: bool
    display_name: str
    google_linked: bool = False


@dataclass(frozen=True)
class IdpSignIn:
    """Result of ``signInWithIdp``; ``tokens`` is None when confirmation is needed."""

    tokens: Tokens | None
    is_new_user: bool
    need_confirmation: bool


async def send_request(
    transport: httpx.AsyncBaseTransport | None,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            return await client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        raise ApiError(504, "auth_upstream_timeout") from None
    except httpx.HTTPError:
        raise ApiError(*_UPSTREAM_ERROR) from None


def _firebase_code(response: httpx.Response) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
    # Messages may carry a detail after the code: "WEAK_PASSWORD : ...".
    return str(message).split(" : ")[0].strip()


def _firestore_status(response: httpx.Response) -> str:
    try:
        status = response.json()["error"]["status"]
    except (ValueError, KeyError, TypeError):
        return ""
    if isinstance(status, str) and _GRPC_STATUS.fullmatch(status):
        return status
    return ""


def _raise_for_error(
    response: httpx.Response,
    codes: dict[str, tuple[int, str]] = _ERROR_CODES,
    ignore: frozenset[str] = frozenset(),
) -> None:
    if response.is_success:
        return
    firebase_code = _firebase_code(response)
    if firebase_code in ignore:
        return
    status, code = codes.get(firebase_code, _UPSTREAM_ERROR)
    logger.warning("firebase failure: %s", code)
    raise ApiError(status, code)


def json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise ApiError(*_UPSTREAM_ERROR)
    return data


def _google_entry(user: dict[str, Any]) -> dict[str, Any] | None:
    providers = user.get("providerUserInfo")
    if not isinstance(providers, list):
        return None
    for item in providers:
        if isinstance(item, dict) and item.get("providerId") == GOOGLE_PROVIDER_ID:
            return item
    return None


def _same_email(first: object, second: object) -> bool:
    if not isinstance(first, str) or not isinstance(second, str):
        return False
    return bool(first.strip()) and first.strip().lower() == second.strip().lower()


def _effective_verified(user: dict[str, Any], google: dict[str, Any] | None) -> bool:
    """Firebase's flag, or a linked Google account that owns the same email."""
    if user.get("emailVerified") is True:
        return True
    return google is not None and _same_email(google.get("email"), user.get("email"))


def _tokens(data: dict[str, Any]) -> Tokens:
    try:
        return Tokens(
            uid=data.get("localId") or data["user_id"],
            id_token=data.get("idToken") or data["id_token"],
            refresh_token=data.get("refreshToken") or data["refresh_token"],
            expires_in=int(data.get("expiresIn") or data["expires_in"]),
        )
    except (KeyError, ValueError, TypeError):
        raise ApiError(*_UPSTREAM_ERROR) from None


class FirebaseAuthGateway:
    def __init__(
        self, api_key: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_key = api_key
        self._transport = transport

    async def _call(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        ignore: frozenset[str] = frozenset(),
        codes: dict[str, tuple[int, str]] = _ERROR_CODES,
    ) -> dict[str, Any]:
        response = await send_request(
            self._transport,
            "POST",
            f"{IDENTITY_URL}:{endpoint}",
            params={"key": self._api_key},
            json=payload,
        )
        _raise_for_error(response, codes, ignore)
        # Only an ignored error gets here without success; it has nothing to read.
        return json_object(response) if response.is_success else {}

    async def sign_up(self, email: str, password: str) -> Tokens:
        data = await self._call(
            "signUp",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return _tokens(data)

    async def sign_in(self, email: str, password: str) -> Tokens:
        data = await self._call(
            "signInWithPassword",
            {"email": email, "password": password, "returnSecureToken": True},
        )
        return _tokens(data)

    async def refresh(self, refresh_token: str) -> Tokens:
        response = await send_request(
            self._transport,
            "POST",
            REFRESH_URL,
            params={"key": self._api_key},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        _raise_for_error(response, _REFRESH_CODES)
        return _tokens(json_object(response))

    async def set_display_name(self, id_token: str, display_name: str) -> Tokens:
        data = await self._call(
            "update",
            {
                "idToken": id_token,
                "displayName": display_name,
                "returnSecureToken": True,
            },
        )
        return _tokens(data)

    async def send_verification_email(self, id_token: str) -> None:
        await self._call(
            "sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": id_token}
        )

    async def send_password_reset(self, email: str, user_ip: str) -> None:
        await self._call(
            "sendOobCode",
            {"requestType": "PASSWORD_RESET", "email": email, "userIp": user_ip},
            ignore=frozenset({"EMAIL_NOT_FOUND"}),
        )

    async def lookup(self, id_token: str) -> AccountInfo:
        data = await self._call("lookup", {"idToken": id_token})
        try:
            user = data["users"][0]
            google = _google_entry(user)
            return AccountInfo(
                uid=user["localId"],
                email=user.get("email", ""),
                email_verified=_effective_verified(user, google),
                display_name=user.get("displayName", ""),
                google_linked=google is not None,
            )
        except (KeyError, IndexError, TypeError):
            raise ApiError(*_UPSTREAM_ERROR) from None

    async def sign_in_with_idp(
        self,
        google_id_token: str,
        request_uri: str,
        link_id_token: str | None = None,
    ) -> IdpSignIn:
        """Sign in with a Google ID token, or link it to ``link_id_token``'s account."""
        payload: dict[str, Any] = {
            "postBody": "id_token="
            f"{quote(google_id_token, safe='')}&providerId={GOOGLE_PROVIDER_ID}",
            "requestUri": request_uri,
            "returnSecureToken": True,
            "returnIdpCredential": True,
        }
        if link_id_token is not None:
            payload["idToken"] = link_id_token
        data = await self._call("signInWithIdp", payload, codes=_IDP_CODES)
        # With returnIdpCredential some failures come back as a 200 with errorMessage.
        in_body = _IDP_CODES.get(str(data.get("errorMessage", "")))
        if in_body is not None:
            raise ApiError(*in_body)
        if data.get("needConfirmation") is True:
            return IdpSignIn(None, False, True)
        return IdpSignIn(_tokens(data), data.get("isNewUser") is True, False)

    async def delete_user(self, id_token: str) -> None:
        await self._call("delete", {"idToken": id_token})


def _update_mask(document: dict[str, Any]) -> list[tuple[str, str]]:
    return [("updateMask.fieldPaths", name) for name in document]


class FirestoreGateway:
    def __init__(
        self, project_id: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base = (
            f"{FIRESTORE_URL}/projects/{quote(project_id, safe='')}"
            "/databases/(default)/documents/profiles"
        )
        self._transport = transport

    async def _call(
        self, method: str, uid: str, id_token: str, **kwargs: Any
    ) -> httpx.Response:
        response = await send_request(
            self._transport,
            method,
            f"{self._base}/{quote(uid, safe='')}",
            headers={"Authorization": f"Bearer {id_token}"},
            **kwargs,
        )
        if response.status_code == 404 and method == "GET":
            raise ApiError(404, "profile_not_found")
        if response.status_code == 401:
            raise ApiError(401, "invalid_session")
        if not response.is_success:
            logger.warning(
                "firestore failure: %s http_status=%s firestore_status=%s",
                _UPSTREAM_ERROR[1],
                response.status_code,
                _firestore_status(response) or "none",
            )
            raise ApiError(*_UPSTREAM_ERROR)
        return response

    async def get_profile(self, uid: str, id_token: str) -> Profile:
        response = await self._call("GET", uid, id_token)
        try:
            raw = json_object(response)["fields"]
            if "settings" not in raw:
                # A document holding only the Google marker is not a synced profile.
                raise ApiError(404, "profile_not_found")
            fields = decode_fields(raw)
            return Profile(
                settings=fields["settings"],
                words=fields["words"],
                topics=fields["topics"],
                updated_at=fields["updated_at"],
            )
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ApiError(*_UPSTREAM_ERROR) from None

    async def put_profile(self, uid: str, id_token: str, profile: Profile) -> None:
        document = profile.model_dump() | {"schema_version": PROFILE_SCHEMA_VERSION}
        body = {"fields": encode_fields(document)}
        # The mask keeps every other field of the document, such as the Google marker.
        await self._call(
            "PATCH", uid, id_token, json=body, params=_update_mask(document)
        )

    async def mark_google_linked(self, uid: str, id_token: str) -> None:
        document = {GOOGLE_LINK_FIELD: datetime.now(UTC)}
        body = {"fields": encode_fields(document)}
        await self._call(
            "PATCH", uid, id_token, json=body, params=_update_mask(document)
        )

    async def has_google_link(self, uid: str, id_token: str) -> bool:
        """Whether the marker exists; any read failure is an upstream error."""
        try:
            response = await self._call("GET", uid, id_token)
        except ApiError as exc:
            if exc.code == "profile_not_found":
                return False
            raise ApiError(*_UPSTREAM_ERROR) from None
        fields = json_object(response).get("fields")
        return isinstance(fields, dict) and GOOGLE_LINK_FIELD in fields

    async def delete_profile(self, uid: str, id_token: str) -> None:
        await self._call("DELETE", uid, id_token)
