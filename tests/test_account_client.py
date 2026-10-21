"""AccountClient against a fake backend: payloads, parsing and error mapping."""

import httpx
import pytest
from backend_fakes import make_account_client, session_json

from clearread.services.account_client import (
    AccountClient,
    AccountError,
    AccountErrorKind,
    RemoteProfile,
)

PROFILE = RemoteProfile(
    {"theme": "dark"}, [{"word": "casa"}], [], "2026-10-19T10:00:00Z"
)


def profile_json() -> dict[str, object]:
    return {"settings": {"theme": "dark"}, "words": [], "topics": [], "updated_at": "t"}


def failing(status: int, code: str | None = None) -> AccountClient:
    body = {"error": code} if code else None
    client, _ = make_account_client(lambda r: httpx.Response(status, json=body))
    return client


def test_sign_in_posts_credentials_and_builds_the_session() -> None:
    client, backend = make_account_client(
        lambda r: httpx.Response(200, json=session_json()), now=1000.0
    )

    session = client.sign_in("ana@example.com", "secret-pass")

    assert backend.requests[0].url.path == "/v1/auth/login"
    assert backend.bodies() == [{"email": "ana@example.com", "password": "secret-pass"}]
    assert (session.uid, session.display_name, session.email_verified) == (
        "abc123",
        "Ana",
        False,
    )
    assert session.expires_at == 4600.0


def test_register_expects_201_and_sends_the_display_name() -> None:
    client, backend = make_account_client(
        lambda r: httpx.Response(201, json=session_json())
    )

    client.register("ana@example.com", "secret-pass", "Ana")

    assert backend.requests[0].url.path == "/v1/auth/register"
    assert backend.bodies() == [
        {"email": "ana@example.com", "password": "secret-pass", "display_name": "Ana"}
    ]


def test_refresh_sends_the_refresh_token() -> None:
    client, backend = make_account_client(
        lambda r: httpx.Response(200, json=session_json(id_token="id-2"))
    )

    assert client.refresh("refresh-1").id_token == "id-2"
    assert backend.bodies() == [{"refresh_token": "refresh-1"}]


def test_delete_with_a_wrong_password_is_invalid_credentials() -> None:
    with pytest.raises(AccountError) as error:
        failing(401, "invalid_credentials").delete_account("id-1", "nope")
    assert error.value.kind is AccountErrorKind.INVALID_CREDENTIALS


def test_password_reset_and_delete_expect_204_and_use_the_bearer() -> None:
    client, backend = make_account_client(lambda r: httpx.Response(204))

    client.request_password_reset("ana@example.com")
    client.delete_account("id-1", "my password")

    assert [r.method for r in backend.requests] == ["POST", "DELETE"]
    assert backend.bodies()[1] == {"password": "my password"}
    assert backend.requests[1].url.path == "/v1/account"
    assert backend.requests[1].headers["Authorization"] == "Bearer id-1"
    assert "Authorization" not in backend.requests[0].headers


def test_fetch_profile_returns_the_remote_profile() -> None:
    client, backend = make_account_client(
        lambda r: httpx.Response(200, json=profile_json())
    )

    profile = client.fetch_profile("id-1")

    assert profile == RemoteProfile({"theme": "dark"}, [], [], "t")
    assert backend.requests[0].headers["Authorization"] == "Bearer id-1"


def test_missing_profile_is_none() -> None:
    assert failing(404, "profile_not_found").fetch_profile("id-1") is None


def test_push_profile_puts_the_whole_profile() -> None:
    client, backend = make_account_client(
        lambda r: httpx.Response(200, json=profile_json())
    )

    client.push_profile("id-1", PROFILE)

    assert backend.requests[0].method == "PUT"
    assert backend.bodies() == [
        {
            "settings": {"theme": "dark"},
            "words": [{"word": "casa"}],
            "topics": [],
            "updated_at": "2026-10-19T10:00:00Z",
        }
    ]


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (409, "email_exists", AccountErrorKind.EMAIL_EXISTS),
        (401, "invalid_credentials", AccountErrorKind.INVALID_CREDENTIALS),
        (422, "password_too_short", AccountErrorKind.PASSWORD_TOO_SHORT),
        (422, "invalid_request", AccountErrorKind.INVALID_REQUEST),
        (429, "too_many_attempts", AccountErrorKind.TOO_MANY_ATTEMPTS),
        (401, "invalid_session", AccountErrorKind.INVALID_SESSION),
        (401, "session_revoked", AccountErrorKind.SESSION_REVOKED),
        (413, "profile_too_large", AccountErrorKind.PROFILE_TOO_LARGE),
        (502, "auth_upstream_error", AccountErrorKind.SERVICE_UNAVAILABLE),
        (504, "auth_upstream_timeout", AccountErrorKind.TIMEOUT),
    ],
)
def test_backend_codes_map_to_kinds(
    status: int, code: str, kind: AccountErrorKind
) -> None:
    with pytest.raises(AccountError) as raised:
        failing(status, code).sign_in("a@b.co", "12345678")

    assert raised.value.kind is kind


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (429, AccountErrorKind.TOO_MANY_ATTEMPTS),
        (503, AccountErrorKind.SERVICE_UNAVAILABLE),
        (504, AccountErrorKind.TIMEOUT),
        (500, AccountErrorKind.UNEXPECTED),
    ],
)
def test_unknown_body_falls_back_to_the_status(
    status: int, kind: AccountErrorKind
) -> None:
    with pytest.raises(AccountError) as raised:
        failing(status).sign_in("a@b.co", "12345678")

    assert raised.value.kind is kind


@pytest.mark.parametrize(
    "body",
    [None, ["x"], {"uid": "abc"}, session_json(expires_in="soon"), session_json(uid=5)],
)
def test_malformed_session_is_unexpected(body: object) -> None:
    client, _ = make_account_client(lambda r: httpx.Response(200, json=body))

    with pytest.raises(AccountError) as raised:
        client.sign_in("a@b.co", "12345678")

    assert raised.value.kind is AccountErrorKind.UNEXPECTED


def test_malformed_profile_is_unexpected() -> None:
    client, _ = make_account_client(lambda r: httpx.Response(200, json={"words": 1}))

    with pytest.raises(AccountError) as raised:
        client.fetch_profile("id-1")

    assert raised.value.kind is AccountErrorKind.UNEXPECTED


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (httpx.ConnectError("down"), AccountErrorKind.NO_NETWORK),
        (httpx.ReadTimeout("slow"), AccountErrorKind.TIMEOUT),
    ],
)
def test_transport_failures_map_to_kinds(
    error: httpx.HTTPError, kind: AccountErrorKind
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    client, _ = make_account_client(handler)

    with pytest.raises(AccountError) as raised:
        client.refresh("r")
    assert raised.value.kind is kind

    if kind is AccountErrorKind.NO_NETWORK:
        with pytest.raises(AccountError) as awake:
            client.ensure_awake(lambda: None)
        assert awake.value.kind is AccountErrorKind.NO_NETWORK
