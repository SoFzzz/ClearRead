"""A stateful fake of Firebase Auth and Firestore behind httpx.MockTransport."""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx

DEFAULT_EMAIL = "student@example.test"
DEFAULT_PASSWORD = "correct horse"
DEFAULT_TOKEN = "valid-id-token"
DEFAULT_UID = "uid-student"


def firebase_error(message: str, status: int = 400) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": status, "message": message}})


@dataclass
class User:
    uid: str
    email: str
    password: str
    display_name: str = ""
    email_verified: bool = False
    providers: list[str] = field(default_factory=list)
    google_email: str | None = None


@dataclass
class Call:
    method: str
    url: httpx.URL
    body: dict[str, Any]
    headers: httpx.Headers


@dataclass
class FakeFirebase:
    """Answers like Firebase; ``failures`` maps an operation name to a forced reply."""

    users: dict[str, User] = field(default_factory=dict)
    id_tokens: dict[str, str] = field(default_factory=dict)
    refresh_tokens: dict[str, str] = field(default_factory=dict)
    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: dict[str, httpx.Response | Exception] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    idp_links: dict[str, str] = field(default_factory=dict)
    need_confirmation: bool = False
    _ids: Any = field(default_factory=itertools.count)

    def __post_init__(self) -> None:
        user = self.add_user(DEFAULT_EMAIL, DEFAULT_PASSWORD, "Ana", DEFAULT_UID)
        self.id_tokens[DEFAULT_TOKEN] = user.uid

    def add_user(
        self, email: str, password: str, name: str = "", uid: str | None = None
    ) -> User:
        user = User(uid or f"uid-{next(self._ids)}", email, password, name)
        self.users[email] = user
        return user

    def calls_to(self, operation: str) -> list[Call]:
        return [call for call in self.calls if self._operation(call) == operation]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        call = Call(request.method, request.url, self._body(request), request.headers)
        self.calls.append(call)
        operation = self._operation(call)
        forced = self.failures.get(operation)
        if isinstance(forced, Exception):
            raise forced
        if forced is not None:
            return forced
        handlers: dict[str, Callable[[Call], httpx.Response]] = {
            "signUp": self._sign_up,
            "signInWithPassword": self._sign_in,
            "refresh": self._refresh,
            "update": self._update,
            "lookup": self._lookup,
            "delete": self._delete_user,
            "signInWithIdp": self._sign_in_with_idp,
            "PASSWORD_RESET": self._password_reset,
            "VERIFY_EMAIL": lambda call: httpx.Response(200, json={}),
            "firestore": self._firestore,
        }
        return handlers[operation](call)

    @staticmethod
    def _body(request: httpx.Request) -> dict[str, Any]:
        if not request.content:
            return {}
        if "json" in request.headers.get("content-type", ""):
            return json.loads(request.content)
        form = parse_qs(request.content.decode())
        return {key: values[0] for key, values in form.items()}

    @staticmethod
    def _operation(call: Call) -> str:
        host = call.url.host
        if host == "securetoken.googleapis.com":
            return "refresh"
        if host == "firestore.googleapis.com":
            return "firestore"
        name = call.url.path.rsplit(":", 1)[1]
        return call.body["requestType"] if name == "sendOobCode" else name

    def issue(self, user: User) -> dict[str, Any]:
        number = next(self._ids)
        id_token, refresh_token = f"id-{number}", f"refresh-{number}"
        self.id_tokens[id_token] = user.uid
        self.refresh_tokens[refresh_token] = user.uid
        return {
            "localId": user.uid,
            "email": user.email,
            "displayName": user.display_name,
            "idToken": id_token,
            "refreshToken": refresh_token,
            "expiresIn": "3600",
        }

    def _user_by_uid(self, uid: str) -> User | None:
        return next((u for u in self.users.values() if u.uid == uid), None)

    def _user_of(self, id_token: str) -> User | None:
        uid = self.id_tokens.get(id_token)
        return None if uid is None else self._user_by_uid(uid)

    def _sign_up(self, call: Call) -> httpx.Response:
        email, password = call.body["email"], call.body["password"]
        if email in self.users:
            return firebase_error("EMAIL_EXISTS")
        if len(password) < 6:
            return firebase_error(
                "WEAK_PASSWORD : Password should be at least 6 characters"
            )
        return httpx.Response(200, json=self.issue(self.add_user(email, password)))

    def _sign_in(self, call: Call) -> httpx.Response:
        user = self.users.get(call.body["email"])
        if user is None or user.password != call.body["password"]:
            return firebase_error("INVALID_LOGIN_CREDENTIALS")
        return httpx.Response(200, json=self.issue(user))

    def _refresh(self, call: Call) -> httpx.Response:
        uid = self.refresh_tokens.get(call.body["refresh_token"])
        user = None if uid is None else self._user_by_uid(uid)
        if user is None:
            return firebase_error("INVALID_REFRESH_TOKEN")
        fresh = self.issue(user)
        return httpx.Response(
            200,
            json={
                "id_token": fresh["idToken"],
                "refresh_token": fresh["refreshToken"],
                "expires_in": "3600",
                "user_id": user.uid,
                "token_type": "Bearer",
                "project_id": "fake-project",
            },
        )

    def _update(self, call: Call) -> httpx.Response:
        user = self._user_of(call.body["idToken"])
        if user is None:
            return firebase_error("INVALID_ID_TOKEN")
        user.display_name = call.body["displayName"]
        return httpx.Response(200, json=self.issue(user))

    def _lookup(self, call: Call) -> httpx.Response:
        user = self._user_of(call.body["idToken"])
        if user is None:
            return firebase_error("INVALID_ID_TOKEN")
        info = {
            "localId": user.uid,
            "email": user.email,
            "emailVerified": user.email_verified,
            "displayName": user.display_name,
            "providerUserInfo": [self._provider_entry(user, n) for n in user.providers],
        }
        return httpx.Response(200, json={"users": [info]})

    @staticmethod
    def _provider_entry(user: User, name: str) -> dict[str, str]:
        if name == "google.com" and user.google_email is not None:
            return {"providerId": name, "email": user.google_email}
        return {"providerId": name}

    def _delete_user(self, call: Call) -> httpx.Response:
        user = self._user_of(call.body["idToken"])
        if user is None:
            return firebase_error("INVALID_ID_TOKEN")
        del self.users[user.email]
        return httpx.Response(
            200, json={"kind": "identitytoolkit#DeleteAccountResponse"}
        )

    def _sign_in_with_idp(self, call: Call) -> httpx.Response:
        identity = parse_qs(call.body["postBody"])["id_token"][0]
        assert call.body["returnSecureToken"] is True
        owner = self._user_by_uid(self.idp_links.get(identity, ""))
        caller = self._user_of(call.body["idToken"]) if "idToken" in call.body else None
        if "idToken" in call.body and caller is None:
            return firebase_error("INVALID_ID_TOKEN")
        if self.need_confirmation:
            return httpx.Response(200, json={"needConfirmation": True})
        if owner is not None and caller is not None and owner is not caller:
            return firebase_error("FEDERATED_USER_ID_ALREADY_LINKED")
        if owner is not None:
            return httpx.Response(200, json=self.issue(owner) | {"isNewUser": False})
        user = caller or self.add_user(f"{identity}@gmail.test", "", uid=None)
        user.providers.append("google.com")
        self.idp_links[identity] = user.uid
        return httpx.Response(
            200, json=self.issue(user) | {"isNewUser": caller is None}
        )

    def _password_reset(self, call: Call) -> httpx.Response:
        if call.body["email"] not in self.users:
            return firebase_error("EMAIL_NOT_FOUND")
        return httpx.Response(200, json={"email": call.body["email"]})

    def _firestore(self, call: Call) -> httpx.Response:
        token = call.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.id_tokens:
            return httpx.Response(401, json={"error": {"status": "UNAUTHENTICATED"}})
        uid = call.url.path.rsplit("/", 1)[1]
        if self.id_tokens[token] != uid:
            # The rules of spec 4.14.7: only the owner may touch profiles/<uid>.
            return httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}})
        if call.method == "GET":
            if uid not in self.documents:
                return httpx.Response(404, json={"error": {"status": "NOT_FOUND"}})
            return httpx.Response(200, json={"fields": self.documents[uid]})
        if call.method == "PATCH":
            masked = call.url.params.get_list("updateMask.fieldPaths")
            fields = call.body["fields"]
            if masked:
                fields = self.documents.get(uid, {}) | fields
            self.documents[uid] = fields
            return httpx.Response(200, json={"fields": self.documents[uid]})
        self.documents.pop(uid, None)
        return httpx.Response(200, json={})
