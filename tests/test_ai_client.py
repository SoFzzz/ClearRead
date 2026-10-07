"""BackendAIClient against an in-process fake backend (httpx.MockTransport), §4.10."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from clearread.services.ai_client import (
    AIErrorKind,
    AIUnavailableError,
    BackendAIClient,
    DiskResponseCache,
)

BASE = "https://backend.test"
TOKEN = "test-token"


class FakeBackend:
    """Routes requests to a handler and records them."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


class Clock:
    """Fake time: sleeping advances it, so the 60 s wait costs nothing."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def ok(text: str = "Respuesta.") -> httpx.Response:
    return httpx.Response(200, json={"text": text})


def make_client(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    lang: str = "es",
    clock: Clock | None = None,
) -> tuple[BackendAIClient, FakeBackend]:
    backend = FakeBackend(handler)
    clock = clock or Clock()
    client = BackendAIClient(
        BASE,
        TOKEN,
        DiskResponseCache(tmp_path / "cache.json"),
        lang,
        transport=httpx.MockTransport(backend),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    return client, backend


def test_explain_success_sends_token_and_language(tmp_path: Path) -> None:
    client, backend = make_client(tmp_path, lambda r: ok("Dura poco."))

    response = client.explain_word("efímero", "Fue un éxito efímero.")

    assert response.text == "Dura poco."
    assert not response.from_cache
    request = backend.requests[0]
    assert request.url.path == "/v1/explain"
    assert request.headers["X-Client-Token"] == TOKEN
    assert json.loads(request.content) == {
        "word": "efímero",
        "context_sentence": "Fue un éxito efímero.",
        "lang": "es",
    }


def test_simplify_success_uses_interface_language(tmp_path: Path) -> None:
    client, backend = make_client(tmp_path, lambda r: ok(), lang="en")

    client.simplify_paragraph("Un texto largo.")

    assert backend.requests[0].url.path == "/v1/simplify"
    assert json.loads(backend.requests[0].content) == {
        "text": "Un texto largo.",
        "lang": "en",
    }


@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        (401, "invalid_client_token", AIErrorKind.SERVICE_UNAVAILABLE),
        (413, "input_too_long", AIErrorKind.INPUT_TOO_LONG),
        (422, "invalid_request", AIErrorKind.BAD_RESPONSE),
        (429, "daily_limit_reached", AIErrorKind.DAILY_LIMIT),
        (502, "upstream_auth_failed", AIErrorKind.SERVICE_UNAVAILABLE),
        (502, "upstream_no_balance", AIErrorKind.SERVICE_UNAVAILABLE),
        (502, "upstream_bad_response", AIErrorKind.SERVICE_UNAVAILABLE),
        (504, "upstream_timeout", AIErrorKind.TIMEOUT),
    ],
)
def test_backend_error_codes_map_to_kinds(
    tmp_path: Path, status: int, code: str, kind: AIErrorKind
) -> None:
    client, _ = make_client(
        tmp_path, lambda r: httpx.Response(status, json={"error": code})
    )

    with pytest.raises(AIUnavailableError) as raised:
        client.simplify_paragraph("texto")

    assert raised.value.kind is kind


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (429, AIErrorKind.DAILY_LIMIT),
        (503, AIErrorKind.SERVICE_UNAVAILABLE),
        (504, AIErrorKind.TIMEOUT),
        (500, AIErrorKind.BAD_RESPONSE),
    ],
)
def test_unknown_body_falls_back_to_status(
    tmp_path: Path, status: int, kind: AIErrorKind
) -> None:
    client, _ = make_client(tmp_path, lambda r: httpx.Response(status, text="<html>"))

    with pytest.raises(AIUnavailableError) as raised:
        client.simplify_paragraph("texto")

    assert raised.value.kind is kind


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"other": "x"}),
        httpx.Response(200, json={"text": "   "}),
        httpx.Response(200, json=["text"]),
    ],
)
def test_unexpected_success_body_is_bad_response(
    tmp_path: Path, response: httpx.Response
) -> None:
    client, _ = make_client(tmp_path, lambda r: response)

    with pytest.raises(AIUnavailableError) as raised:
        client.simplify_paragraph("texto")

    assert raised.value.kind is AIErrorKind.BAD_RESPONSE


def test_request_timeout(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client, _ = make_client(tmp_path, handler)

    with pytest.raises(AIUnavailableError) as raised:
        client.explain_word("a", "b")

    assert raised.value.kind is AIErrorKind.TIMEOUT


def test_connection_failure_is_no_network(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client, _ = make_client(tmp_path, handler)

    with pytest.raises(AIUnavailableError) as raised:
        client.explain_word("a", "b")
    assert raised.value.kind is AIErrorKind.NO_NETWORK

    with pytest.raises(AIUnavailableError) as raised_health:
        client.ensure_awake(lambda: None)
    assert raised_health.value.kind is AIErrorKind.NO_NETWORK


def test_awake_backend_does_not_signal_waking(tmp_path: Path) -> None:
    client, backend = make_client(tmp_path, lambda r: httpx.Response(200, json={}))
    woke: list[bool] = []

    client.ensure_awake(lambda: woke.append(True))

    assert woke == []
    assert [r.url.path for r in backend.requests] == ["/health"]


def test_waking_then_success(tmp_path: Path) -> None:
    probes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        probes.append(1)
        if len(probes) < 3:
            raise httpx.ReadTimeout("asleep", request=request)
        return httpx.Response(200, json={"status": "ok"})

    clock = Clock()
    client, _ = make_client(tmp_path, handler, clock=clock)
    woke: list[bool] = []

    client.ensure_awake(lambda: woke.append(True))

    assert woke == [True]
    assert len(probes) == 3
    assert clock.now < BackendAIClient.WAKE_TIMEOUT_SECONDS


def test_waking_never_answers_is_server_waking(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("asleep", request=request)

    clock = Clock()
    client, _ = make_client(tmp_path, handler, clock=clock)
    woke: list[bool] = []

    with pytest.raises(AIUnavailableError) as raised:
        client.ensure_awake(lambda: woke.append(True))

    assert raised.value.kind is AIErrorKind.SERVER_WAKING
    assert woke == [True]
    assert clock.now >= BackendAIClient.WAKE_TIMEOUT_SECONDS


def test_cache_hit_skips_backend_and_normalizes_text(tmp_path: Path) -> None:
    client, backend = make_client(tmp_path, lambda r: ok("Hola."))
    client.simplify_paragraph("Un  Texto")

    again = client.simplify_paragraph("un texto")

    assert again.from_cache
    assert again.text == "Hola."
    assert len(backend.requests) == 1


def test_cache_survives_a_new_client(tmp_path: Path) -> None:
    first, _ = make_client(tmp_path, lambda r: ok("Guardado."))
    first.explain_word("casa", "Mi casa.")
    second, backend = make_client(tmp_path, lambda r: ok("Otro."))

    response = second.explain_word("casa", "Mi casa.")

    assert response.from_cache
    assert response.text == "Guardado."
    assert backend.requests == []


def test_cache_is_per_language(tmp_path: Path) -> None:
    spanish, _ = make_client(tmp_path, lambda r: ok("es"), lang="es")
    spanish.simplify_paragraph("same")
    english, backend = make_client(tmp_path, lambda r: ok("en"), lang="en")

    assert english.simplify_paragraph("same").text == "en"
    assert len(backend.requests) == 1


def test_damaged_cache_file_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "cache.json").write_text("{broken", encoding="utf-8")
    client, _ = make_client(tmp_path, lambda r: ok("Bien."))

    assert client.simplify_paragraph("x").text == "Bien."


def test_cache_drops_oldest_entry(tmp_path: Path) -> None:
    cache = DiskResponseCache(tmp_path / "c.json", max_entries=2)
    cache.set(("a",), "1")
    cache.set(("b",), "2")
    cache.set(("c",), "3")

    assert cache.get(("a",)) is None
    assert cache.get(("c",)) == "3"


def test_session_limit_blocks_new_calls_but_not_cached_ones(tmp_path: Path) -> None:
    client, backend = make_client(tmp_path, lambda r: ok())
    for index in range(BackendAIClient.MAX_CALLS_PER_SESSION):
        client.simplify_paragraph(f"text {index}")

    with pytest.raises(AIUnavailableError) as raised:
        client.simplify_paragraph("one more")

    assert raised.value.kind is AIErrorKind.SESSION_LIMIT
    assert client.simplify_paragraph("text 0").from_cache
    assert len(backend.requests) == BackendAIClient.MAX_CALLS_PER_SESSION


def test_failed_answers_are_not_cached(tmp_path: Path) -> None:
    answers = iter([httpx.Response(502, json={"error": "upstream_timeout"}), ok("Ya.")])
    client, backend = make_client(tmp_path, lambda r: next(answers))

    with pytest.raises(AIUnavailableError):
        client.simplify_paragraph("x")

    assert client.simplify_paragraph("x").text == "Ya."
    assert len(backend.requests) == 2
