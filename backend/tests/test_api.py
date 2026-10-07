"""Endpoints, input guards, daily cap, cache and error translation (BE-F01, BE-F02)."""

from datetime import date, timedelta

import httpx
import pytest
from conftest import FAKE_KEY, HEADERS, FakeDeepSeek, completion, make_client
from fastapi.testclient import TestClient

from clearread_backend.deepseek import ResponseCache, trim_to_last_sentence
from clearread_backend.main import EXPLAIN_MAX_TOKENS, SIMPLIFY_MAX_TOKENS
from clearread_backend.prompts import EXPLAIN_SYSTEM_PROMPTS, SIMPLIFY_SYSTEM_PROMPTS
from clearread_backend.quota import DailyQuota

EXPLAIN = {
    "word": "fotosíntesis",
    "context_sentence": "Las plantas la usan.",
    "lang": "es",
}
SIMPLIFY = {"text": "El mecanismo es complejo y requiere atención.", "lang": "es"}


def post(client: TestClient, path: str, body: object, headers: dict | None = None):
    return client.post(path, json=body, headers=HEADERS if headers is None else headers)


# ---- endpoints ---------------------------------------------------------------


def test_health_and_docs_are_open(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200


def test_explain_returns_the_model_text_and_sends_the_right_request(
    client: TestClient, deepseek: FakeDeepSeek
) -> None:
    response = post(client, "/v1/explain", EXPLAIN)
    assert response.status_code == 200
    assert response.json() == {"text": "Respuesta simple."}
    sent = deepseek.requests[0]
    assert sent["model"] == "deepseek-flash"
    assert sent["max_tokens"] == EXPLAIN_MAX_TOKENS == 80
    assert sent["messages"][0] == {
        "role": "system",
        "content": EXPLAIN_SYSTEM_PROMPTS["es"],
    }
    assert "fotosíntesis" in sent["messages"][1]["content"]
    assert deepseek.headers[0]["authorization"] == f"Bearer {FAKE_KEY}"


def test_thinking_mode_is_disabled_so_max_tokens_go_to_the_answer(
    client: TestClient, deepseek: FakeDeepSeek
) -> None:
    post(client, "/v1/explain", EXPLAIN)
    assert deepseek.requests[0]["thinking"] == {"type": "disabled"}


def test_simplify_returns_the_model_text_with_its_own_limits(
    client: TestClient, deepseek: FakeDeepSeek
) -> None:
    response = post(client, "/v1/simplify", SIMPLIFY)
    assert response.json() == {"text": "Respuesta simple."}
    sent = deepseek.requests[0]
    assert sent["max_tokens"] == SIMPLIFY_MAX_TOKENS == 250
    assert sent["messages"][1]["content"] == SIMPLIFY["text"]


def test_the_system_prompt_follows_the_language(
    client: TestClient, deepseek: FakeDeepSeek
) -> None:
    post(client, "/v1/explain", EXPLAIN | {"lang": "en"})
    post(client, "/v1/simplify", SIMPLIFY | {"lang": "en"})
    post(client, "/v1/simplify", SIMPLIFY)
    systems = [r["messages"][0]["content"] for r in deepseek.requests]
    assert systems == [
        EXPLAIN_SYSTEM_PROMPTS["en"],
        SIMPLIFY_SYSTEM_PROMPTS["en"],
        SIMPLIFY_SYSTEM_PROMPTS["es"],
    ]
    assert "2 sentences" in EXPLAIN_SYSTEM_PROMPTS["en"]
    assert "máximo 4 frases" in SIMPLIFY_SYSTEM_PROMPTS["es"]


# ---- guards ------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, body", [("/v1/explain", EXPLAIN), ("/v1/simplify", SIMPLIFY)]
)
@pytest.mark.parametrize("headers", [{}, {"X-Client-Token": "wrong"}])
def test_missing_or_wrong_token_is_401(
    client: TestClient, deepseek: FakeDeepSeek, path: str, body: dict, headers: dict
) -> None:
    response = post(client, path, body, headers)
    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client_token"}
    assert deepseek.requests == []


def test_token_is_checked_before_the_body(client: TestClient) -> None:
    assert post(client, "/v1/explain", {"nonsense": 1}, {}).status_code == 401


def test_an_unconfigured_token_rejects_everything(deepseek: FakeDeepSeek) -> None:
    client = make_client(deepseek, client_token="")
    assert post(client, "/v1/explain", EXPLAIN, {}).status_code == 401
    assert (
        post(client, "/v1/explain", EXPLAIN, {"X-Client-Token": ""}).status_code == 401
    )


@pytest.mark.parametrize(
    "body",
    [
        EXPLAIN | {"word": "a" * 41},
        EXPLAIN | {"context_sentence": "a" * 301},
    ],
)
def test_explain_inputs_over_the_limit_are_413(
    client: TestClient, deepseek: FakeDeepSeek, body: dict
) -> None:
    response = post(client, "/v1/explain", body)
    assert response.status_code == 413
    assert response.json() == {"error": "input_too_long"}
    assert deepseek.requests == []


def test_limits_are_inclusive(client: TestClient) -> None:
    ok = EXPLAIN | {"word": "a" * 40, "context_sentence": "b" * 300}
    assert post(client, "/v1/explain", ok).status_code == 200
    assert (
        post(client, "/v1/simplify", {"text": "c" * 1500, "lang": "en"}).status_code
        == 200
    )
    assert (
        post(client, "/v1/simplify", {"text": "c" * 1501, "lang": "en"}).status_code
        == 413
    )


@pytest.mark.parametrize(
    "path, body",
    [
        ("/v1/explain", EXPLAIN | {"lang": "fr"}),
        ("/v1/explain", {k: v for k, v in EXPLAIN.items() if k != "lang"}),
        ("/v1/explain", EXPLAIN | {"word": "   "}),
        ("/v1/explain", EXPLAIN | {"word": ""}),
        ("/v1/explain", EXPLAIN | {"word": "a" * 41, "lang": "fr"}),
        ("/v1/explain", "not an object"),
        ("/v1/simplify", SIMPLIFY | {"lang": "ES"}),
        ("/v1/simplify", {"lang": "es"}),
    ],
)
def test_malformed_bodies_are_422(
    client: TestClient, deepseek: FakeDeepSeek, path: str, body: object
) -> None:
    response = post(client, path, body)
    assert response.status_code == 422
    assert response.json() == {"error": "invalid_request"}
    assert deepseek.requests == []


# ---- daily cap ---------------------------------------------------------------


def test_the_global_daily_cap_answers_429_with_a_stable_code(
    deepseek: FakeDeepSeek,
) -> None:
    client = make_client(deepseek, daily_call_limit=2)
    for word in ("uno", "dos"):
        assert post(client, "/v1/explain", EXPLAIN | {"word": word}).status_code == 200
    blocked = post(client, "/v1/explain", EXPLAIN | {"word": "tres"})
    assert blocked.status_code == 429
    assert blocked.json() == {"error": "daily_limit_reached"}
    assert len(deepseek.requests) == 2


def test_the_cap_is_global_across_endpoints_and_clients(deepseek: FakeDeepSeek) -> None:
    client = make_client(deepseek, daily_call_limit=1)
    assert post(client, "/v1/explain", EXPLAIN).status_code == 200
    assert post(client, "/v1/simplify", SIMPLIFY).status_code == 429


def test_the_quota_restarts_when_the_utc_day_changes() -> None:
    today = [date(2026, 10, 7)]
    quota = DailyQuota(1, today=lambda: today[0])
    assert quota.try_consume()
    assert not quota.try_consume()
    today[0] += timedelta(days=1)
    assert quota.try_consume()


# ---- cache -------------------------------------------------------------------


def test_a_repeated_request_is_served_from_the_cache_without_using_the_cap(
    deepseek: FakeDeepSeek,
) -> None:
    client = make_client(deepseek, daily_call_limit=1)
    first = post(client, "/v1/explain", EXPLAIN)
    again = post(client, "/v1/explain", EXPLAIN | {"word": " Fotosíntesis "})
    assert first.json() == again.json()
    assert again.status_code == 200
    assert len(deepseek.requests) == 1


def test_the_cache_distinguishes_language_and_endpoint(
    client: TestClient, deepseek
) -> None:
    post(client, "/v1/explain", EXPLAIN)
    post(client, "/v1/explain", EXPLAIN | {"lang": "en"})
    post(client, "/v1/simplify", {"text": EXPLAIN["word"], "lang": "es"})
    assert len(deepseek.requests) == 3


def test_failures_are_not_cached(deepseek: FakeDeepSeek) -> None:
    client = make_client(deepseek)
    deepseek.handler = lambda request: httpx.Response(500)
    assert post(client, "/v1/explain", EXPLAIN).status_code == 502
    deepseek.handler = lambda request: completion("Ahora sí.")
    assert post(client, "/v1/explain", EXPLAIN).json() == {"text": "Ahora sí."}


def test_the_cache_is_bounded_and_drops_the_oldest() -> None:
    cache = ResponseCache(max_entries=2)
    for index in range(3):
        cache.put(("s", str(index)), str(index))
    assert cache.get(("s", "0")) is None
    assert cache.get(("s", "2")) == "2"


# ---- DeepSeek errors -----------------------------------------------------------


def raise_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


def raise_connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.mark.parametrize(
    "handler, status, code",
    [
        (
            lambda r: httpx.Response(401, json={"error": "bad key"}),
            502,
            "upstream_auth_failed",
        ),
        (lambda r: httpx.Response(402), 502, "upstream_no_balance"),
        (raise_timeout, 504, "upstream_timeout"),
        (raise_connect_error, 502, "upstream_bad_response"),
        (lambda r: httpx.Response(500, text="boom"), 502, "upstream_bad_response"),
        (lambda r: httpx.Response(429), 502, "upstream_bad_response"),
        (
            lambda r: httpx.Response(200, text="<html>not json"),
            502,
            "upstream_bad_response",
        ),
        (
            lambda r: httpx.Response(200, json={"choices": []}),
            502,
            "upstream_bad_response",
        ),
        (
            lambda r: httpx.Response(200, json={"unexpected": 1}),
            502,
            "upstream_bad_response",
        ),
        (lambda r: httpx.Response(200, json=[1, 2]), 502, "upstream_bad_response"),
        (lambda r: completion("   "), 502, "upstream_bad_response"),
        (lambda r: completion(""), 502, "upstream_bad_response"),
    ],
)
def test_deepseek_failures_become_stable_codes_without_upstream_text(
    deepseek: FakeDeepSeek, handler, status: int, code: str
) -> None:
    deepseek.handler = handler
    client = make_client(deepseek)
    response = post(client, "/v1/explain", EXPLAIN)
    assert response.status_code == status
    assert response.json() == {"error": code}
    assert "bad key" not in response.text
    assert FAKE_KEY not in response.text


def test_the_request_to_deepseek_has_a_20_second_timeout() -> None:
    from clearread_backend.deepseek import TIMEOUT_S

    assert TIMEOUT_S == 20.0


# ---- truncated replies -----------------------------------------------------------


def test_a_reply_cut_by_the_token_limit_ends_at_the_last_complete_sentence(
    deepseek: FakeDeepSeek,
) -> None:
    deepseek.handler = lambda r: completion(
        "Es un proceso. Las plantas lo usan. Además la luz y el", "length"
    )
    client = make_client(deepseek)
    reply = post(client, "/v1/explain", EXPLAIN).json()
    assert reply == {"text": "Es un proceso. Las plantas lo usan."}


def test_a_complete_reply_is_not_trimmed(deepseek: FakeDeepSeek) -> None:
    deepseek.handler = lambda r: completion("Una frase. Otra sin punto", "stop")
    client = make_client(deepseek)
    assert (
        post(client, "/v1/explain", EXPLAIN).json()["text"]
        == "Una frase. Otra sin punto"
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hola. Adiós y", "Hola."),
        ("¿Qué es? Sí es.. y", "¿Qué es? Sí es.."),
        ('Dijo "sí." Luego', 'Dijo "sí."'),
        ("Sin punto final", "Sin punto final"),
    ],
)
def test_trim_to_last_sentence(text: str, expected: str) -> None:
    assert trim_to_last_sentence(text) == expected
