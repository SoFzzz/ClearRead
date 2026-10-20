"""Register, sign in, refresh, password reset and account deletion."""

import httpx
import pytest
from conftest import BEARER, FakeDeepSeek, make_client
from fake_firebase import (
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    DEFAULT_UID,
    FakeFirebase,
    firebase_error,
)
from fastapi.testclient import TestClient

from clearread_backend.firebase import TIMEOUT_S

NEW = {"email": "new@example.test", "password": "long enough", "display_name": "Eva"}
SESSION_FIELDS = {
    "google_linked",
    "uid",
    "email",
    "display_name",
    "email_verified",
    "id_token",
    "refresh_token",
    "expires_in",
}


# ---- register ----------------------------------------------------------------


def test_register_creates_the_account_and_returns_a_session(
    client: TestClient, firebase: FakeFirebase
) -> None:
    response = client.post("/v1/auth/register", json=NEW)
    assert response.status_code == 201
    session = response.json()
    assert set(session) == SESSION_FIELDS
    assert session["email"] == NEW["email"]
    assert session["display_name"] == "Eva"
    assert session["email_verified"] is False
    assert session["expires_in"] == 3600
    assert firebase.users[NEW["email"]].display_name == "Eva"


def test_register_sends_the_verification_email_with_the_new_token(
    client: TestClient, firebase: FakeFirebase
) -> None:
    session = client.post("/v1/auth/register", json=NEW).json()
    (sent,) = firebase.calls_to("VERIFY_EMAIL")
    assert sent.body["idToken"] == session["id_token"]


def test_register_succeeds_even_if_the_verification_email_fails(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["VERIFY_EMAIL"] = firebase_error("OPERATION_NOT_ALLOWED")
    assert client.post("/v1/auth/register", json=NEW).status_code == 201


def test_register_succeeds_even_if_setting_the_display_name_fails(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["update"] = httpx.Response(500)
    response = client.post("/v1/auth/register", json=NEW)
    assert response.status_code == 201
    assert response.json()["display_name"] == ""
    login = {"email": NEW["email"], "password": NEW["password"]}
    assert client.post("/v1/auth/login", json=login).status_code == 200


def test_register_with_a_known_email_is_409(client: TestClient) -> None:
    response = client.post("/v1/auth/register", json=NEW | {"email": DEFAULT_EMAIL})
    assert response.status_code == 409
    assert response.json() == {"error": "email_exists"}


def test_register_with_a_short_password_is_422_and_never_reaches_firebase(
    client: TestClient, firebase: FakeFirebase
) -> None:
    response = client.post("/v1/auth/register", json=NEW | {"password": "short"})
    assert response.status_code == 422
    assert response.json() == {"error": "password_too_short"}
    assert firebase.calls == []


def test_a_weak_password_rejected_by_firebase_is_password_too_short(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["signUp"] = firebase_error(
        "WEAK_PASSWORD : Password should be at least 6 characters"
    )
    response = client.post("/v1/auth/register", json=NEW)
    assert (response.status_code, response.json()) == (
        422,
        {"error": "password_too_short"},
    )


def test_password_limits_are_inclusive_and_spaces_are_kept(
    client: TestClient, firebase: FakeFirebase
) -> None:
    assert (
        client.post(
            "/v1/auth/register", json=NEW | {"password": "12345678"}
        ).status_code
        == 201
    )
    padded = " " * 8
    other = NEW | {"email": "other@example.test", "password": padded}
    assert client.post("/v1/auth/register", json=other).status_code == 201
    assert firebase.users["other@example.test"].password == padded
    long_password = NEW | {"email": "long@example.test", "password": "a" * 128}
    assert client.post("/v1/auth/register", json=long_password).status_code == 201


def test_a_password_over_128_characters_is_413(client: TestClient) -> None:
    response = client.post("/v1/auth/register", json=NEW | {"password": "a" * 129})
    assert (response.status_code, response.json()) == (413, {"error": "input_too_long"})


@pytest.mark.parametrize(
    "change",
    [
        {"email": "not-an-email"},
        {"email": ""},
        {"display_name": ""},
        {"display_name": "   "},
        {"password": ""},
    ],
)
def test_register_with_invalid_fields_is_422(client: TestClient, change: dict) -> None:
    response = client.post("/v1/auth/register", json=NEW | change)
    assert response.status_code == 422
    assert response.json() in (
        {"error": "invalid_request"},
        {"error": "password_too_short"},
    )


def test_a_display_name_over_40_characters_is_413(client: TestClient) -> None:
    response = client.post("/v1/auth/register", json=NEW | {"display_name": "n" * 41})
    assert response.status_code == 413


def test_register_trims_the_email_and_display_name(
    client: TestClient, firebase: FakeFirebase
) -> None:
    body = NEW | {"email": "  new@example.test ", "display_name": " Eva "}
    session = client.post("/v1/auth/register", json=body).json()
    assert session["email"] == "new@example.test"
    assert session["display_name"] == "Eva"


# ---- login -------------------------------------------------------------------


def test_login_returns_a_session_with_the_verified_flag(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.users[DEFAULT_EMAIL].email_verified = True
    body = {"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    response = client.post("/v1/auth/login", json=body)
    assert response.status_code == 200
    session = response.json()
    assert set(session) == SESSION_FIELDS
    assert session["uid"] == DEFAULT_UID
    assert session["display_name"] == "Ana"
    assert session["email_verified"] is True


@pytest.mark.parametrize(
    "email, password",
    [(DEFAULT_EMAIL, "wrong password"), ("nobody@example.test", "whatever 123")],
)
def test_login_with_bad_credentials_is_401_without_telling_which_part(
    client: TestClient, email: str, password: str
) -> None:
    response = client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 401
    assert response.json() == {"error": "invalid_credentials"}


@pytest.mark.parametrize(
    "firebase_code", ["EMAIL_NOT_FOUND", "INVALID_PASSWORD", "USER_DISABLED"]
)
def test_every_credential_failure_of_firebase_is_invalid_credentials(
    client: TestClient, firebase: FakeFirebase, firebase_code: str
) -> None:
    firebase.failures["signInWithPassword"] = firebase_error(firebase_code)
    body = {"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    response = client.post("/v1/auth/login", json=body)
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_credentials"},
    )


def test_login_throttled_by_firebase_is_429(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["signInWithPassword"] = firebase_error(
        "TOO_MANY_ATTEMPTS_TRY_LATER : Access blocked temporarily", 400
    )
    body = {"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    response = client.post("/v1/auth/login", json=body)
    assert (response.status_code, response.json()) == (
        429,
        {"error": "too_many_attempts"},
    )


def test_login_requires_both_fields(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"email": DEFAULT_EMAIL})
    assert (response.status_code, response.json()) == (
        422,
        {"error": "invalid_request"},
    )


# ---- refresh -----------------------------------------------------------------


def test_refresh_returns_a_fresh_session(
    client: TestClient, firebase: FakeFirebase
) -> None:
    first = client.post(
        "/v1/auth/login", json={"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    ).json()
    response = client.post(
        "/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert response.status_code == 200
    session = response.json()
    assert set(session) == SESSION_FIELDS
    assert session["uid"] == DEFAULT_UID
    assert session["email"] == DEFAULT_EMAIL
    assert session["id_token"] != first["id_token"]
    (call,) = firebase.calls_to("refresh")
    assert call.body == {
        "grant_type": "refresh_token",
        "refresh_token": first["refresh_token"],
    }


@pytest.mark.parametrize(
    "firebase_code",
    ["INVALID_REFRESH_TOKEN", "TOKEN_EXPIRED", "USER_NOT_FOUND", "USER_DISABLED"],
)
def test_a_refresh_token_that_cannot_refresh_is_session_revoked(
    client: TestClient, firebase: FakeFirebase, firebase_code: str
) -> None:
    firebase.failures["refresh"] = firebase_error(firebase_code)
    response = client.post("/v1/auth/refresh", json={"refresh_token": "anything"})
    assert (response.status_code, response.json()) == (
        401,
        {"error": "session_revoked"},
    )


def test_refresh_with_an_unknown_token_is_session_revoked(client: TestClient) -> None:
    response = client.post("/v1/auth/refresh", json={"refresh_token": "forged"})
    assert (response.status_code, response.json()) == (
        401,
        {"error": "session_revoked"},
    )


# ---- password reset ------------------------------------------------------------


@pytest.mark.parametrize("email", [DEFAULT_EMAIL, "nobody@example.test"])
def test_password_reset_is_204_whether_or_not_the_account_exists(
    client: TestClient, email: str
) -> None:
    response = client.post("/v1/auth/password-reset", json={"email": email})
    assert response.status_code == 204
    assert response.content == b""


def test_password_reset_forwards_the_first_forwarded_hop_as_user_ip(
    client: TestClient, firebase: FakeFirebase
) -> None:
    client.post(
        "/v1/auth/password-reset",
        json={"email": DEFAULT_EMAIL},
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )
    (call,) = firebase.calls_to("PASSWORD_RESET")
    assert call.body["userIp"] == "203.0.113.7"


def test_password_reset_falls_back_to_the_connection_address(
    client: TestClient, firebase: FakeFirebase
) -> None:
    client.post("/v1/auth/password-reset", json={"email": DEFAULT_EMAIL})
    (call,) = firebase.calls_to("PASSWORD_RESET")
    assert call.body["userIp"] == "testclient"


def test_password_reset_still_reports_real_upstream_failures(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["PASSWORD_RESET"] = httpx.Response(500)
    response = client.post("/v1/auth/password-reset", json={"email": DEFAULT_EMAIL})
    assert (response.status_code, response.json()) == (
        502,
        {"error": "auth_upstream_error"},
    )


def test_password_reset_rejects_a_malformed_email(client: TestClient) -> None:
    response = client.post("/v1/auth/password-reset", json={"email": "nope"})
    assert response.status_code == 422


# ---- delete account ------------------------------------------------------------


def test_delete_account_removes_the_profile_and_then_the_user(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.documents[DEFAULT_UID] = {"settings": {"mapValue": {}}}
    response = client.delete("/v1/account", headers=BEARER)
    assert response.status_code == 204
    assert DEFAULT_UID not in firebase.documents
    assert DEFAULT_EMAIL not in firebase.users
    operations = [firebase._operation(call) for call in firebase.calls]
    assert operations.index("firestore") < operations.index("delete")


def test_a_deleted_account_can_no_longer_use_its_cached_token(
    client: TestClient,
) -> None:
    assert client.get("/v1/profile", headers=BEARER).status_code == 404
    assert client.delete("/v1/account", headers=BEARER).status_code == 204
    again = client.get("/v1/profile", headers=BEARER)
    assert (again.status_code, again.json()) == (401, {"error": "invalid_session"})


def test_delete_account_needs_a_bearer_token(client: TestClient) -> None:
    response = client.delete("/v1/account")
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_session"},
    )


def test_delete_account_needing_a_recent_sign_in_asks_to_sign_in_again(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["delete"] = firebase_error("CREDENTIAL_TOO_OLD_LOGIN_AGAIN")
    response = client.delete("/v1/account", headers=BEARER)
    assert (response.status_code, response.json()) == (
        401,
        {"error": "session_revoked"},
    )


# ---- upstream failures ---------------------------------------------------------


@pytest.mark.parametrize(
    "forced, status, code",
    [
        (httpx.ReadTimeout("slow"), 504, "auth_upstream_timeout"),
        (httpx.ConnectError("down"), 502, "auth_upstream_error"),
        (httpx.Response(500, text="boom"), 502, "auth_upstream_error"),
        (httpx.Response(200, text="<html>"), 502, "auth_upstream_error"),
        (httpx.Response(200, json=[1]), 502, "auth_upstream_error"),
        (httpx.Response(200, json={"unexpected": 1}), 502, "auth_upstream_error"),
        (firebase_error("SOMETHING_NEW"), 502, "auth_upstream_error"),
        (firebase_error("OPERATION_NOT_ALLOWED"), 502, "auth_upstream_error"),
        (httpx.Response(400, text="not json"), 502, "auth_upstream_error"),
    ],
)
def test_firebase_failures_become_stable_codes_without_firebase_text(
    client: TestClient,
    firebase: FakeFirebase,
    forced: httpx.Response | Exception,
    status: int,
    code: str,
) -> None:
    firebase.failures["signInWithPassword"] = forced
    body = {"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD}
    response = client.post("/v1/auth/login", json=body)
    assert (response.status_code, response.json()) == (status, {"error": code})
    assert "SOMETHING_NEW" not in response.text


def test_the_request_to_firebase_has_a_10_second_timeout() -> None:
    assert TIMEOUT_S == 10.0


# ---- configuration -------------------------------------------------------------


@pytest.mark.parametrize(
    "change", [{"firebase_api_key": ""}, {"firebase_project_id": ""}]
)
def test_without_firebase_settings_every_auth_endpoint_is_503(
    deepseek: FakeDeepSeek, change: dict
) -> None:
    client = make_client(deepseek, **change)
    calls = [
        client.post("/v1/auth/register", json=NEW),
        client.post("/v1/auth/login", json={"email": DEFAULT_EMAIL, "password": "x"}),
        client.post("/v1/auth/refresh", json={"refresh_token": "x"}),
        client.post("/v1/auth/password-reset", json={"email": DEFAULT_EMAIL}),
        client.delete("/v1/account", headers=BEARER),
        client.get("/v1/profile", headers=BEARER),
    ]
    for response in calls:
        assert (response.status_code, response.json()) == (
            503,
            {"error": "auth_not_configured"},
        )
