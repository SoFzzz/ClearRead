"""AccountClient Google calls: request shape, parsing and the code -> kind mapping."""

import httpx
import pytest
from backend_fakes import make_account_client, session_json

from clearread.services.account_client import (
    AccountError,
    AccountErrorKind,
    GoogleMode,
    GoogleState,
)

ATTEMPT = {"attempt_id": "att_-1", "poll_token": "secret-poll", "expires_in": 600}


def reply(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body)


def test_start_sends_the_mode_and_the_bearer_and_parses_the_attempt() -> None:
    client, backend = make_account_client(lambda request: reply(200, ATTEMPT))
    attempt = client.start_google(GoogleMode.LINK, "id-token")
    request = backend.requests[0]
    assert (request.method, request.url.path) == ("POST", "/v1/auth/google/start")
    assert request.headers["Authorization"] == "Bearer id-token"
    assert backend.bodies() == [{"mode": "link"}]
    assert (attempt.attempt_id, attempt.poll_token, attempt.expires_in) == (
        "att_-1",
        "secret-poll",
        600.0,
    )


def test_sign_in_start_has_no_bearer() -> None:
    client, backend = make_account_client(lambda request: reply(200, ATTEMPT))
    client.start_google(GoogleMode.SIGN_IN, None)
    assert "Authorization" not in backend.requests[0].headers
    assert backend.bodies() == [{"mode": "sign_in"}]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {**ATTEMPT, "attempt_id": "has/slash"},
        {**ATTEMPT, "attempt_id": "../x"},
        {**ATTEMPT, "poll_token": ""},
        {**ATTEMPT, "expires_in": 0},
        {**ATTEMPT, "expires_in": "soon"},
        ["not", "a", "dict"],
    ],
)
def test_a_bad_attempt_is_unexpected(body: object) -> None:
    client, _ = make_account_client(lambda request: reply(200, body))
    with pytest.raises(AccountError) as caught:
        client.start_google(GoogleMode.SIGN_IN, None)
    assert caught.value.kind is AccountErrorKind.UNEXPECTED


def test_status_sends_the_poll_token_in_a_header_never_in_the_url() -> None:
    client, backend = make_account_client(
        lambda request: reply(200, {"status": "pending"})
    )
    status = client.google_status("att_-1", "secret-poll")
    request = backend.requests[0]
    assert status.state is GoogleState.PENDING and status.session is None
    assert request.url.path == "/v1/auth/google/status/att_-1"
    assert request.headers["X-Poll-Token"] == "secret-poll"
    assert "secret-poll" not in str(request.url)


def test_status_linked() -> None:
    client, _ = make_account_client(lambda request: reply(200, {"status": "linked"}))
    assert client.google_status("a", "p").state is GoogleState.LINKED


def test_status_signed_in_carries_the_session() -> None:
    body = {"status": "signed_in", "session": session_json(google_linked=True)}
    client, _ = make_account_client(lambda request: reply(200, body), now=1000.0)
    status = client.google_status("a", "p")
    assert status.state is GoogleState.SIGNED_IN
    assert status.session is not None
    assert status.session.uid == "abc123"
    assert status.session.google_linked is True
    assert status.session.expires_at == 4600.0


def test_signed_in_without_a_session_is_unexpected() -> None:
    client, _ = make_account_client(lambda request: reply(200, {"status": "signed_in"}))
    with pytest.raises(AccountError) as caught:
        client.google_status("a", "p")
    assert caught.value.kind is AccountErrorKind.UNEXPECTED


@pytest.mark.parametrize("body", [{"status": "dancing"}, {}, "pending", None])
def test_an_unknown_status_is_unexpected(body: object) -> None:
    client, _ = make_account_client(lambda request: reply(200, body))
    with pytest.raises(AccountError) as caught:
        client.google_status("a", "p")
    assert caught.value.kind is AccountErrorKind.UNEXPECTED


@pytest.mark.parametrize("attempt_id", ["", "a/b", "a b", "..", "a?x=1"])
def test_a_bad_attempt_id_never_reaches_the_network(attempt_id: str) -> None:
    client, backend = make_account_client(lambda request: reply(200, {}))
    with pytest.raises(AccountError):
        client.google_status(attempt_id, "p")
    assert backend.requests == []


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (409, "google_cancelled", AccountErrorKind.GOOGLE_CANCELLED),
        (409, "google_already_linked", AccountErrorKind.GOOGLE_ALREADY_LINKED),
        (403, "google_not_linked", AccountErrorKind.GOOGLE_NOT_LINKED),
        (403, "email_not_verified", AccountErrorKind.EMAIL_NOT_VERIFIED),
        (404, "google_attempt_not_found", AccountErrorKind.GOOGLE_ATTEMPT_NOT_FOUND),
        (410, "google_attempt_expired", AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED),
        (503, "google_not_configured", AccountErrorKind.GOOGLE_NOT_CONFIGURED),
        (401, "invalid_session", AccountErrorKind.INVALID_SESSION),
        (429, "too_many_attempts", AccountErrorKind.TOO_MANY_ATTEMPTS),
        (502, "auth_upstream_error", AccountErrorKind.SERVICE_UNAVAILABLE),
        (504, "auth_upstream_timeout", AccountErrorKind.TIMEOUT),
        (500, "something_new", AccountErrorKind.UNEXPECTED),
    ],
)
def test_every_backend_code_maps_to_its_kind(
    status: int, code: str, kind: AccountErrorKind
) -> None:
    client, _ = make_account_client(lambda request: reply(status, {"error": code}))
    for call in (
        lambda: client.start_google(GoogleMode.SIGN_IN, None),
        lambda: client.google_status("a", "p"),
    ):
        with pytest.raises(AccountError) as caught:
            call()
        assert caught.value.kind is kind


def test_a_410_without_a_code_still_means_expired() -> None:
    client, _ = make_account_client(lambda request: httpx.Response(410, text="gone"))
    with pytest.raises(AccountError) as caught:
        client.google_status("a", "p")
    assert caught.value.kind is AccountErrorKind.GOOGLE_ATTEMPT_EXPIRED


def test_session_without_google_linked_defaults_to_false() -> None:
    client, _ = make_account_client(lambda request: reply(200, session_json()))
    assert client.sign_in("a@b.co", "x" * 8).google_linked is False
