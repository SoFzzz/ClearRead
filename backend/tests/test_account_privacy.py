"""BE-F03 extended: logs never carry emails, passwords, tokens or profile contents."""

import logging

import httpx
import pytest
from conftest import BEARER, FAKE_FIREBASE_KEY
from fake_firebase import DEFAULT_UID, FakeFirebase, firebase_error
from fastapi.testclient import TestClient

from clearread_backend.settings import Settings

EMAIL = "marta.ejemplo@example.test"
PASSWORD = "contrasena-secreta-123"
WORD = "zorbalimento"
PROFILE = {
    "settings": {"note": "ajuste privado de Marta"},
    "words": [{"word": WORD, "explanation": "explicacion privada"}],
    "topics": [],
    "updated_at": "2026-10-19T12:00:00Z",
}


def logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def assert_nothing_leaked(caplog: pytest.LogCaptureFixture, *extra: str) -> None:
    text = logged(caplog)
    secrets = (
        EMAIL,
        PASSWORD,
        WORD,
        "Marta",
        FAKE_FIREBASE_KEY,
        "valid-id-token",
        *extra,
    )
    for secret in secrets:
        assert secret not in text


def test_account_flows_log_no_email_password_or_token(
    caplog: pytest.LogCaptureFixture, client: TestClient, firebase: FakeFirebase
) -> None:
    caplog.set_level(logging.DEBUG)
    session = client.post(
        "/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "display_name": "Marta"},
    ).json()
    client.post("/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    client.post("/v1/auth/login", json={"email": EMAIL, "password": "wrong-password-1"})
    client.post("/v1/auth/refresh", json={"refresh_token": session["refresh_token"]})
    client.post("/v1/auth/password-reset", json={"email": EMAIL})
    client.post("/v1/auth/password-reset", json={"email": "ghost@example.test"})
    assert_nothing_leaked(
        caplog, session["id_token"], session["refresh_token"], "ghost@example.test"
    )


def test_deleting_an_account_logs_no_password_email_or_token(
    caplog: pytest.LogCaptureFixture, client: TestClient, firebase: FakeFirebase
) -> None:
    caplog.set_level(logging.DEBUG)
    session = client.post(
        "/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "display_name": "Marta"},
    ).json()
    headers = {"Authorization": f"Bearer {session['id_token']}"}
    client.request(
        "DELETE", "/v1/account", json={"password": "wrong-password-1"}, headers=headers
    )
    response = client.request(
        "DELETE", "/v1/account", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 204
    assert_nothing_leaked(
        caplog, "wrong-password-1", session["id_token"], session["refresh_token"]
    )


def test_profile_flows_log_no_contents(
    caplog: pytest.LogCaptureFixture, client: TestClient, firebase: FakeFirebase
) -> None:
    caplog.set_level(logging.DEBUG)
    client.put("/v1/profile", json=PROFILE, headers=BEARER)
    client.get("/v1/profile", headers=BEARER)
    firebase.failures["firestore"] = httpx.Response(500, text=f"{WORD} {EMAIL}")
    client.get("/v1/profile", headers=BEARER)
    client.put("/v1/profile", json=PROFILE, headers=BEARER)
    assert_nothing_leaked(caplog)
    assert "auth_upstream_error" in logged(caplog)


@pytest.mark.parametrize(
    "forced, expected",
    [
        (
            httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "message": f"denied {DEFAULT_UID} {EMAIL} "
                        "https://firestore.googleapis.com/v1/x",
                        "status": "PERMISSION_DENIED",
                    }
                },
            ),
            "http_status=403 firestore_status=PERMISSION_DENIED",
        ),
        (
            httpx.Response(500, text=f"{WORD} {EMAIL}"),
            "http_status=500 firestore_status=none",
        ),
        (
            httpx.Response(400, json={"error": {"status": f"{EMAIL} {WORD}"}}),
            "http_status=400 firestore_status=none",
        ),
    ],
)
def test_firestore_failures_log_only_the_http_and_firestore_status(
    caplog: pytest.LogCaptureFixture,
    client: TestClient,
    firebase: FakeFirebase,
    forced: httpx.Response,
    expected: str,
) -> None:
    caplog.set_level(logging.DEBUG)
    firebase.failures["firestore"] = forced
    response = client.get("/v1/profile", headers=BEARER)
    assert response.json() == {"error": "auth_upstream_error"}
    assert f"auth_upstream_error {expected}" in logged(caplog)
    assert_nothing_leaked(caplog, DEFAULT_UID, "firestore.googleapis.com", "denied")


def test_firebase_error_text_is_logged_as_our_code_only(
    caplog: pytest.LogCaptureFixture, client: TestClient, firebase: FakeFirebase
) -> None:
    caplog.set_level(logging.DEBUG)
    firebase.failures["signInWithPassword"] = firebase_error(
        f"TOO_MANY_ATTEMPTS_TRY_LATER : {EMAIL} {PASSWORD}"
    )
    response = client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.json() == {"error": "too_many_attempts"}
    assert_nothing_leaked(caplog)
    assert "too_many_attempts" in logged(caplog)
    assert EMAIL not in response.text


def test_failed_firebase_calls_do_not_leak_in_the_response(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["signUp"] = httpx.Response(500, text=f"{EMAIL} {PASSWORD}")
    response = client.post(
        "/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "display_name": "Marta"},
    )
    assert response.json() == {"error": "auth_upstream_error"}


def test_the_firebase_key_is_not_in_the_docs_or_the_openapi_schema(
    client: TestClient,
) -> None:
    assert FAKE_FIREBASE_KEY not in client.get("/openapi.json").text
    assert FAKE_FIREBASE_KEY not in client.get("/docs").text


def test_settings_read_the_firebase_variables_with_safe_defaults() -> None:
    defaults = Settings.from_env({})
    assert (defaults.firebase_api_key, defaults.firebase_project_id) == ("", "")
    assert defaults.user_daily_call_limit == 15
    assert not defaults.auth_configured
    given = Settings.from_env(
        {
            "FIREBASE_API_KEY": "k",
            "FIREBASE_PROJECT_ID": "p",
            "USER_DAILY_CALL_LIMIT": "4",
        }
    )
    assert (given.firebase_api_key, given.firebase_project_id) == ("k", "p")
    assert given.user_daily_call_limit == 4
    assert given.auth_configured
