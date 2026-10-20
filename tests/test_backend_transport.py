"""BackendTransport: headers, JSON decoding, failure mapping and the wake probe."""

import httpx
import pytest
from backend_fakes import BASE, TOKEN, FakeBackend, make_transport

from clearread.services.backend_transport import (
    BackendTransport,
    TransportError,
    TransportErrorKind,
)


def test_request_sends_client_token_and_json_without_bearer() -> None:
    backend = FakeBackend(lambda r: httpx.Response(200, json={"ok": True}))

    reply = make_transport(backend).request("POST", "/v1/x", {"a": 1})

    request = backend.requests[0]
    assert request.headers["X-Client-Token"] == TOKEN
    assert "Authorization" not in request.headers
    assert backend.bodies() == [{"a": 1}]
    assert (reply.status, reply.body) == (200, {"ok": True})


def test_request_sends_bearer_when_given() -> None:
    backend = FakeBackend(lambda r: httpx.Response(204))

    make_transport(backend).request("GET", "/v1/profile", bearer="tok")

    assert backend.requests[0].headers["Authorization"] == "Bearer tok"


def test_empty_or_non_json_body_decodes_to_none() -> None:
    backend = FakeBackend(lambda r: httpx.Response(502, text="<html>"))

    assert make_transport(backend).request("GET", "/x").body is None


def test_error_code_reads_the_backend_code_only() -> None:
    session = FakeBackend(
        lambda r: httpx.Response(401, json={"error": "invalid_session"})
    )
    assert make_transport(session).request("GET", "/x").error_code == "invalid_session"

    other = FakeBackend(lambda r: httpx.Response(401, json=["x"]))
    assert make_transport(other).request("GET", "/x").error_code is None


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (httpx.ReadTimeout("slow"), TransportErrorKind.TIMEOUT),
        (httpx.ConnectError("down"), TransportErrorKind.NO_NETWORK),
    ],
)
def test_transport_failures_map_to_kinds(
    error: httpx.HTTPError, kind: TransportErrorKind
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(TransportError) as raised:
        make_transport(FakeBackend(handler)).request("GET", "/x")

    assert raised.value.kind is kind


def test_base_url_trailing_slash_is_ignored() -> None:
    backend = FakeBackend(lambda r: httpx.Response(200, json={}))
    transport = BackendTransport(
        BASE + "/", TOKEN, transport=httpx.MockTransport(backend)
    )

    transport.request("GET", "/v1/profile")

    assert str(backend.requests[0].url) == f"{BASE}/v1/profile"


def _clocked_transport(
    handler: httpx.MockTransport | None, clock: list[float]
) -> BackendTransport:
    return BackendTransport(
        BASE,
        TOKEN,
        transport=handler,
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
        monotonic=lambda: clock[0],
    )


def test_wait_until_awake_polls_with_the_injected_clock() -> None:
    clock = [0.0]
    answers = iter([httpx.ReadTimeout("asleep"), httpx.ReadTimeout("asleep"), None])

    def handler(request: httpx.Request) -> httpx.Response:
        error = next(answers)
        if error:
            raise error
        return httpx.Response(200, json={})

    transport = _clocked_transport(httpx.MockTransport(handler), clock)
    woke: list[bool] = []

    assert transport.wait_until_awake(lambda: woke.append(True), 60.0, 2.0)
    assert woke == [True]
    assert clock[0] == 4.0


def test_wait_until_awake_gives_up_after_the_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("asleep")

    transport = _clocked_transport(httpx.MockTransport(handler), [0.0])

    assert not transport.wait_until_awake(lambda: None, 10.0, 2.0)
