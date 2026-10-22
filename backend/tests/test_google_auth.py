"""Link and sign in with Google: the attempt flow, its failures and its privacy."""

import hashlib
import logging
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from conftest import BEARER, PUBLIC_BASE_URL, FakeDeepSeek, make_client
from fake_firebase import DEFAULT_UID, FakeFirebase, firebase_error
from fake_google import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    FakeClock,
    FakeGoogle,
)
from fastapi.testclient import TestClient

from clearread_backend.google_auth import (
    CALLBACK_PAGE,
    MAX_LIVE_ATTEMPTS,
    RedactGoogleAccessLog,
)
from clearread_backend.google_oauth import AUTHORIZATION_URL
from clearread_backend.settings import Settings

CALLBACK_URL = f"{PUBLIC_BASE_URL}/v1/auth/google/callback"
STUDENT = "student@example.test"
CREDENTIALS = {"email": STUDENT, "password": "correct horse"}
NOT_FOUND = {"error": "google_attempt_not_found"}


@dataclass
class Started:
    attempt_id: str
    poll_token: str
    state: str = ""
    authorization: dict[str, str] | None = None

    @property
    def poll(self) -> dict[str, str]:
        return {"X-Poll-Token": self.poll_token}


@pytest.fixture
def web(
    deepseek: FakeDeepSeek,
    firebase: FakeFirebase,
    google: FakeGoogle,
    clock: FakeClock,
) -> TestClient:
    firebase.users[STUDENT].email_verified = True
    return make_client(deepseek, firebase, google, clock)


def start(web: TestClient, mode: str, headers: dict[str, str] | None = None) -> Started:
    response = web.post("/v1/auth/google/start", json={"mode": mode}, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in"] == 600
    return Started(body["attempt_id"], body["poll_token"])


def begin(web: TestClient, attempt: Started) -> httpx.Response:
    response = web.get(
        f"/v1/auth/google/begin/{attempt.attempt_id}", follow_redirects=False
    )
    if response.status_code == 302:
        query = urlparse(response.headers["location"]).query
        attempt.authorization = {k: v[0] for k, v in parse_qs(query).items()}
        attempt.state = attempt.authorization["state"]
    return response


def callback(web: TestClient, state: str, **query: str) -> httpx.Response:
    return web.get("/v1/auth/google/callback", params={"state": state} | query)


def status(web: TestClient, attempt: Started) -> httpx.Response:
    return web.get(f"/v1/auth/google/status/{attempt.attempt_id}", headers=attempt.poll)


def started_and_begun(web: TestClient, mode: str = "sign_in") -> Started:
    attempt = start(web, mode, BEARER if mode == "link" else None)
    assert begin(web, attempt).status_code == 302
    return attempt


def finished(web: TestClient, mode: str, who: str) -> Started:
    attempt = started_and_begun(web, mode)
    assert callback(web, attempt.state, code=f"code-{who}").status_code == 200
    return attempt


def assert_error(response: httpx.Response, status_code: int, code: str) -> None:
    assert (response.status_code, response.json()) == (status_code, {"error": code})


MARKER = {"google_linked_at": {"timestampValue": "2026-10-20T10:00:00Z"}}


def link_google(
    firebase: FakeFirebase, who: str, uid: str = DEFAULT_UID, marker: bool = True
) -> None:
    firebase.users[STUDENT].providers.append("google.com")
    firebase.idp_links[who] = uid
    if marker:
        firebase.documents[uid] = firebase.documents.get(uid, {}) | MARKER


def put_profile(web: TestClient) -> None:
    profile = {
        "settings": {"font_size": 18},
        "words": [],
        "topics": [],
        "updated_at": "2026-10-20T12:00:00Z",
    }
    response = web.put("/v1/profile", json=profile, headers=BEARER)
    assert response.status_code == 200, response.text


# ---- start ---------------------------------------------------------------------


def test_start_returns_ids_of_the_right_shape(web: TestClient) -> None:
    attempt = start(web, "sign_in")
    assert len(attempt.attempt_id) >= 21
    assert len(attempt.poll_token) >= 43


def test_start_link_needs_a_valid_bearer(web: TestClient) -> None:
    body = {"mode": "link"}
    assert_error(web.post("/v1/auth/google/start", json=body), 401, "invalid_session")
    bad = {"Authorization": "Bearer nope"}
    response = web.post("/v1/auth/google/start", json=body, headers=bad)
    assert_error(response, 401, "invalid_session")


def test_start_link_with_a_valid_bearer(web: TestClient) -> None:
    start(web, "link", BEARER)


def test_start_link_refuses_an_unverified_email_before_any_attempt(
    web: TestClient, firebase: FakeFirebase, google: FakeGoogle
) -> None:
    firebase.users[STUDENT].email_verified = False
    body = {"mode": "link"}
    response = web.post("/v1/auth/google/start", json=body, headers=BEARER)
    assert_error(response, 403, "email_not_verified")
    assert not google.requests
    assert not firebase.calls_to("signInWithIdp")
    firebase.users[STUDENT].email_verified = True
    start(web, "link", BEARER)


def test_start_link_sees_an_email_confirmed_after_the_token_was_cached(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.users[STUDENT].email_verified = False
    body = {"mode": "link"}
    refused = web.post("/v1/auth/google/start", json=body, headers=BEARER)
    assert_error(refused, 403, "email_not_verified")
    # The refusal leaves the token cached as unverified; both lookups are its own.
    assert len(firebase.calls_to("lookup")) == 2
    firebase.users[STUDENT].email_verified = True
    start(web, "link", BEARER)
    # The cached unverified state was forgotten and rechecked exactly once.
    assert len(firebase.calls_to("lookup")) == 3


def test_start_link_ignores_a_linked_google_with_the_same_email(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.users[STUDENT].email_verified = False
    link_google(firebase, "alice")
    firebase.users[STUDENT].google_email = STUDENT
    body = {"mode": "link"}
    response = web.post("/v1/auth/google/start", json=body, headers=BEARER)
    assert_error(response, 403, "email_not_verified")


def test_start_sign_in_does_not_need_a_verified_email(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.users[STUDENT].email_verified = False
    start(web, "sign_in")


def test_start_rejects_an_unknown_mode(web: TestClient) -> None:
    response = web.post("/v1/auth/google/start", json={"mode": "delete"})
    assert_error(response, 422, "invalid_request")


def test_start_refuses_when_too_many_attempts_are_alive(
    web: TestClient, clock: FakeClock
) -> None:
    for _ in range(MAX_LIVE_ATTEMPTS):
        start(web, "sign_in")
    response = web.post("/v1/auth/google/start", json={"mode": "sign_in"})
    assert_error(response, 429, "too_many_attempts")
    clock.advance(601)
    start(web, "sign_in")


# ---- begin ---------------------------------------------------------------------


def test_begin_redirects_to_google_with_pkce(web: TestClient) -> None:
    attempt = start(web, "sign_in")
    response = begin(web, attempt)
    assert response.status_code == 302
    assert response.headers["location"].startswith(AUTHORIZATION_URL + "?")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert attempt.authorization is not None
    assert attempt.authorization == {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": "openid email profile",
        "state": attempt.state,
        "code_challenge": attempt.authorization["code_challenge"],
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    assert len(attempt.state) >= 43


def test_begin_twice_is_not_found(web: TestClient) -> None:
    attempt = started_and_begun(web)
    assert_error(begin(web, attempt), 404, "google_attempt_not_found")


def test_begin_unknown_attempt_is_not_found(web: TestClient) -> None:
    response = web.get("/v1/auth/google/begin/unknown", follow_redirects=False)
    assert_error(response, 404, "google_attempt_not_found")


def test_begin_after_the_ttl_is_gone(web: TestClient, clock: FakeClock) -> None:
    attempt = start(web, "sign_in")
    clock.advance(600)
    assert_error(begin(web, attempt), 410, "google_attempt_expired")


# ---- link ------------------------------------------------------------------------


def test_link_happy_path_links_google_to_the_same_account(
    web: TestClient, firebase: FakeFirebase, google: FakeGoogle
) -> None:
    attempt = started_and_begun(web, "link")
    assert status(web, attempt).json() == {"status": "pending"}
    assert callback(web, attempt.state, code="code-alice").status_code == 200

    (token_request,) = google.requests
    verifier_hash = hashlib.sha256(token_request["code_verifier"].encode()).digest()
    assert attempt.authorization is not None
    expected = urlsafe_b64encode(verifier_hash).decode().rstrip("=")
    assert expected == attempt.authorization["code_challenge"]
    assert token_request["redirect_uri"] == CALLBACK_URL
    (idp,) = firebase.calls_to("signInWithIdp")
    assert idp.body["idToken"] == BEARER["Authorization"].removeprefix("Bearer ")
    assert idp.body["requestUri"] == CALLBACK_URL
    assert idp.body["returnIdpCredential"] is True
    assert "providerId=google.com" in idp.body["postBody"]

    assert status(web, attempt).json() == {"status": "linked"}
    assert list(firebase.users) == [STUDENT]
    assert firebase.users[STUDENT].providers == ["google.com"]
    assert "google_linked_at" in firebase.documents[DEFAULT_UID]


def test_link_reports_a_google_account_that_belongs_to_another_profile(
    web: TestClient, firebase: FakeFirebase
) -> None:
    other = firebase.add_user("other@example.test", "pw-other", "Otra")
    firebase.idp_links["alice"] = other.uid
    attempt = finished(web, "link", "alice")
    assert_error(status(web, attempt), 409, "google_already_linked")
    assert not firebase.users[STUDENT].providers


def test_link_email_exists_is_already_linked(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["signInWithIdp"] = firebase_error("EMAIL_EXISTS")
    attempt = finished(web, "link", "alice")
    assert_error(status(web, attempt), 409, "google_already_linked")


def test_link_with_a_dead_session_asks_to_sign_in_again(
    web: TestClient, firebase: FakeFirebase
) -> None:
    attempt = started_and_begun(web, "link")
    firebase.failures["signInWithIdp"] = firebase_error("INVALID_ID_TOKEN")
    callback(web, attempt.state, code="code-alice")
    assert_error(status(web, attempt), 401, "invalid_session")


def test_link_fails_and_can_be_retried_when_the_marker_cannot_be_written(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["firestore"] = httpx.Response(500, json={})
    attempt = finished(web, "link", "alice")
    assert_error(status(web, attempt), 502, "auth_upstream_error")
    assert firebase.users[STUDENT].providers == ["google.com"]
    assert DEFAULT_UID not in firebase.documents

    del firebase.failures["firestore"]
    retry = finished(web, "link", "alice")
    assert status(web, retry).json() == {"status": "linked"}
    assert "google_linked_at" in firebase.documents[DEFAULT_UID]
    assert not firebase.calls_to("delete")


def test_relinking_the_same_google_account_to_the_same_user_is_a_success(
    web: TestClient, firebase: FakeFirebase
) -> None:
    link_google(firebase, "alice", marker=False)
    attempt = finished(web, "link", "alice")
    assert status(web, attempt).json() == {"status": "linked"}
    assert "google_linked_at" in firebase.documents[DEFAULT_UID]


def test_the_marker_survives_a_profile_put(
    web: TestClient, firebase: FakeFirebase
) -> None:
    finished(web, "link", "alice")
    put_profile(web)
    put_profile(web)
    assert "google_linked_at" in firebase.documents[DEFAULT_UID]
    assert "settings" in firebase.documents[DEFAULT_UID]
    attempt = finished(web, "sign_in", "alice")
    assert status(web, attempt).json()["status"] == "signed_in"


def test_a_document_with_only_the_marker_is_not_a_profile(
    web: TestClient, firebase: FakeFirebase
) -> None:
    finished(web, "link", "alice")
    response = web.get("/v1/profile", headers=BEARER)
    assert_error(response, 404, "profile_not_found")


# ---- sign in ---------------------------------------------------------------------


def test_sign_in_happy_path_returns_the_session_of_the_linked_account(
    web: TestClient, firebase: FakeFirebase
) -> None:
    link_google(firebase, "alice")
    attempt = finished(web, "sign_in", "alice")
    (idp,) = firebase.calls_to("signInWithIdp")
    assert "idToken" not in idp.body

    response = status(web, attempt)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "signed_in"
    session = body["session"]
    assert session["uid"] == DEFAULT_UID
    assert session["google_linked"] is True
    assert session["id_token"] and session["refresh_token"]
    assert not firebase.calls_to("delete")


def test_sign_in_without_the_marker_is_refused_and_keeps_the_account(
    web: TestClient, firebase: FakeFirebase
) -> None:
    # Same email as an existing password account: Firebase says "not new".
    link_google(firebase, "alice", marker=False)
    attempt = finished(web, "sign_in", "alice")
    assert_error(status(web, attempt), 403, "google_not_linked")
    assert not firebase.calls_to("delete")
    assert list(firebase.users) == [STUDENT]


def test_sign_in_with_a_document_but_no_marker_is_refused(
    web: TestClient, firebase: FakeFirebase
) -> None:
    link_google(firebase, "alice", marker=False)
    put_profile(web)
    attempt = finished(web, "sign_in", "alice")
    assert_error(status(web, attempt), 403, "google_not_linked")


def test_sign_in_never_lets_anyone_in_when_the_marker_cannot_be_read(
    web: TestClient, firebase: FakeFirebase
) -> None:
    link_google(firebase, "alice")
    firebase.failures["firestore"] = httpx.Response(500, json={})
    attempt = finished(web, "sign_in", "alice")
    assert_error(status(web, attempt), 502, "auth_upstream_error")


def test_sign_in_for_a_new_user_deletes_it_and_fails(
    web: TestClient, firebase: FakeFirebase
) -> None:
    attempt = finished(web, "sign_in", "stranger")
    (delete,) = firebase.calls_to("delete")
    assert delete.body["idToken"] in firebase.id_tokens
    assert list(firebase.users) == [STUDENT]
    assert_error(status(web, attempt), 403, "google_not_linked")


def test_sign_in_still_fails_when_deleting_the_new_user_fails(
    web: TestClient, firebase: FakeFirebase, caplog: pytest.LogCaptureFixture
) -> None:
    firebase.failures["delete"] = firebase_error("INTERNAL")
    with caplog.at_level(logging.DEBUG):
        attempt = finished(web, "sign_in", "stranger")
    assert_error(status(web, attempt), 403, "google_not_linked")
    assert "google_orphan_user" in caplog.text
    assert "stranger" not in caplog.text


def test_sign_in_needing_confirmation_is_not_linked(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.need_confirmation = True
    attempt = finished(web, "sign_in", "alice")
    assert_error(status(web, attempt), 403, "google_not_linked")


def test_sign_in_with_email_exists_is_not_linked(
    web: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["signInWithIdp"] = firebase_error("EMAIL_EXISTS")
    attempt = finished(web, "sign_in", "alice")
    assert_error(status(web, attempt), 403, "google_not_linked")


# ---- callback --------------------------------------------------------------------


def test_callback_page_is_static_and_the_same_for_every_outcome(
    web: TestClient,
) -> None:
    ok, denied, bad = (started_and_begun(web) for _ in range(3))
    pages = [
        callback(web, ok.state, code="code-alice"),
        callback(web, denied.state, error="access_denied"),
        callback(web, bad.state, code="wrong"),
    ]
    assert {page.text for page in pages} == {CALLBACK_PAGE}
    assert {page.status_code for page in pages} == {200}
    csp = pages[0].headers["content-security-policy"]
    assert csp == "default-src 'none'; style-src 'unsafe-inline'"
    assert pages[0].headers["cache-control"] == "no-store"
    lowered = CALLBACK_PAGE.lower()
    forbidden = ("<script", "http://", "https://", "<a ", "<img", "@import", "src=")
    assert not [token for token in forbidden if token in lowered]
    assert "Listo." in CALLBACK_PAGE and "Done." in CALLBACK_PAGE


def test_access_denied_is_a_cancelled_attempt(web: TestClient) -> None:
    attempt = started_and_begun(web)
    callback(web, attempt.state, error="access_denied")
    assert_error(status(web, attempt), 409, "google_cancelled")


def test_unknown_state_is_a_400_with_the_same_page(web: TestClient) -> None:
    response = callback(web, "made-up-state", code="code-alice")
    assert response.status_code == 400
    assert response.text == CALLBACK_PAGE


def test_a_state_works_only_once(web: TestClient) -> None:
    attempt = started_and_begun(web)
    callback(web, attempt.state, error="access_denied")
    assert callback(web, attempt.state, code="code-alice").status_code == 400


def test_callback_after_expiry_is_a_400(web: TestClient, clock: FakeClock) -> None:
    attempt = started_and_begun(web)
    clock.advance(601)
    assert callback(web, attempt.state, code="code-alice").status_code == 400


def test_a_code_google_rejects_is_an_upstream_error(web: TestClient) -> None:
    attempt = started_and_begun(web)
    callback(web, attempt.state, code="rejected")
    assert_error(status(web, attempt), 502, "auth_upstream_error")


def test_google_timing_out_is_a_gateway_timeout(
    web: TestClient, google: FakeGoogle
) -> None:
    google.failure = httpx.ReadTimeout("slow")
    attempt = started_and_begun(web)
    callback(web, attempt.state, code="code-alice")
    assert_error(status(web, attempt), 504, "auth_upstream_timeout")


# ---- status ----------------------------------------------------------------------


def test_status_with_a_wrong_or_missing_poll_token_looks_like_an_unknown_id(
    web: TestClient,
) -> None:
    attempt = start(web, "sign_in")
    unknown = web.get("/v1/auth/google/status/unknown", headers=attempt.poll)
    url = f"/v1/auth/google/status/{attempt.attempt_id}"
    wrong = web.get(url, headers={"X-Poll-Token": "x"})
    missing = web.get(url)
    for response in (unknown, wrong, missing):
        assert_error(response, 404, "google_attempt_not_found")
        assert response.content == unknown.content
    assert status(web, attempt).json() == {"status": "pending"}


def test_status_after_the_ttl_is_gone(web: TestClient, clock: FakeClock) -> None:
    attempt = start(web, "sign_in")
    clock.advance(600)
    assert_error(status(web, attempt), 410, "google_attempt_expired")


def test_a_finished_result_can_be_read_only_once(web: TestClient) -> None:
    attempt = finished(web, "link", "alice")
    assert status(web, attempt).json() == {"status": "linked"}
    assert_error(status(web, attempt), 404, "google_attempt_not_found")


def test_a_failed_result_can_be_read_only_once(web: TestClient) -> None:
    attempt = started_and_begun(web)
    callback(web, attempt.state, error="access_denied")
    assert status(web, attempt).status_code == 409
    assert status(web, attempt).status_code == 404


# ---- configuration ---------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["google_client_id", "google_client_secret", "public_base_url"]
)
def test_without_google_settings_the_flow_answers_503(
    deepseek: FakeDeepSeek, firebase: FakeFirebase, missing: str
) -> None:
    web = make_client(deepseek, firebase, **{missing: ""})
    answers = [
        web.post("/v1/auth/google/start", json={"mode": "sign_in"}),
        web.get("/v1/auth/google/begin/x", follow_redirects=False),
        web.get("/v1/auth/google/callback", params={"state": "x", "code": "y"}),
    ]
    for response in answers:
        assert_error(response, 503, "google_not_configured")
    assert web.get("/v1/auth/google/status/x").status_code == 404
    assert web.post("/v1/auth/login", json=CREDENTIALS).status_code == 200


def test_settings_read_the_google_variables_and_fall_back_to_render() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "RENDER_EXTERNAL_URL": "https://clearread.onrender.test/",
    }
    settings = Settings.from_env(env)
    assert settings.google_configured
    assert settings.public_base_url == "https://clearread.onrender.test"
    assert settings.google_redirect_uri == (
        "https://clearread.onrender.test/v1/auth/google/callback"
    )
    explicit = Settings.from_env(env | {"PUBLIC_BASE_URL": "http://localhost:8000/"})
    assert explicit.public_base_url == "http://localhost:8000"
    assert not Settings.from_env({}).google_configured


# ---- google_linked in the session -------------------------------------------------


def test_login_reports_whether_google_is_linked(
    web: TestClient, firebase: FakeFirebase
) -> None:
    assert web.post("/v1/auth/login", json=CREDENTIALS).json()["google_linked"] is False
    firebase.users[STUDENT].providers = ["password", "google.com"]
    assert web.post("/v1/auth/login", json=CREDENTIALS).json()["google_linked"] is True


def test_refresh_reports_google_linked(web: TestClient, firebase: FakeFirebase) -> None:
    firebase.users[STUDENT].providers = ["google.com"]
    refresh = web.post("/v1/auth/login", json=CREDENTIALS).json()["refresh_token"]
    session = web.post("/v1/auth/refresh", json={"refresh_token": refresh}).json()
    assert session["google_linked"] is True


# ---- privacy -------------------------------------------------------------------------


def test_no_secret_reaches_the_logs_or_the_error_bodies(
    web: TestClient, firebase: FakeFirebase, caplog: pytest.LogCaptureFixture
) -> None:
    link_google(firebase, "alice")
    with caplog.at_level(logging.DEBUG):
        linked = finished(web, "sign_in", "alice")
        stranger = finished(web, "sign_in", "stranger")
        denied = started_and_begun(web)
        callback(web, denied.state, error="access_denied")
        rejected = started_and_begun(web)
        callback(web, rejected.state, code="rejected")
        failures = [status(web, a) for a in (stranger, denied, rejected)]
        session = status(web, linked).json()["session"]

    secrets_seen = [GOOGLE_CLIENT_SECRET, "code-alice", "code-stranger", "stranger"]
    secrets_seen += [session["id_token"], session["refresh_token"], session["email"]]
    for attempt in (linked, stranger, denied, rejected):
        assert attempt.authorization is not None
        secrets_seen += [attempt.attempt_id, attempt.poll_token, attempt.state]
        secrets_seen.append(attempt.authorization["code_challenge"])
    for text in [caplog.text] + [response.text for response in failures]:
        assert not [secret for secret in secrets_seen if secret in text]


def test_the_access_log_filter_hides_attempt_ids_codes_and_states() -> None:
    def record(path: str) -> logging.LogRecord:
        args = ("127.0.0.1:1", "GET", path, "1.1", 200)
        message = '%s "%s %s HTTP/%s" %d'
        return logging.LogRecord("uvicorn.access", 20, "", 0, message, args, None)

    redaction = RedactGoogleAccessLog()
    begin_line = record("/v1/auth/google/begin/SECRET-ID")
    callback_line = record("/v1/auth/google/callback?code=SECRET&state=SECRET")
    other = record("/health")
    for line in (begin_line, callback_line, other):
        assert redaction.filter(line)
    assert "SECRET" not in begin_line.getMessage()
    assert "SECRET" not in callback_line.getMessage()
    assert "/v1/auth/google/begin/[hidden]" in begin_line.getMessage()
    assert "/health" in other.getMessage()
