"""/v1/explain and /v1/simplify need a signed-in user and respect a per-user cap."""

import pytest
from conftest import BEARER, HEADERS, TOKEN, FakeDeepSeek, make_client
from fake_firebase import FakeFirebase
from fastapi.testclient import TestClient

EXPLAIN = {"word": "casa", "context_sentence": "La casa es azul.", "lang": "es"}
SIMPLIFY = {"text": "El mecanismo es complejo.", "lang": "es"}
CLIENT_TOKEN = {"X-Client-Token": TOKEN}
OTHER = {"Authorization": "Bearer other-token"}

ENDPOINTS = [("/v1/explain", EXPLAIN), ("/v1/simplify", SIMPLIFY)]


@pytest.mark.parametrize("path, body", ENDPOINTS)
@pytest.mark.parametrize(
    "bearer", [{}, {"Authorization": "Bearer forged"}, {"Authorization": "Token x"}]
)
def test_a_missing_or_unknown_bearer_is_401_invalid_session(
    client: TestClient, deepseek: FakeDeepSeek, path: str, body: dict, bearer: dict
) -> None:
    response = client.post(path, json=body, headers=CLIENT_TOKEN | bearer)
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_session"},
    )
    assert deepseek.requests == []


@pytest.mark.parametrize("path, body", ENDPOINTS)
def test_a_valid_bearer_without_the_client_token_is_still_rejected(
    client: TestClient, path: str, body: dict
) -> None:
    response = client.post(path, json=body, headers=BEARER)
    assert response.json() == {"error": "invalid_client_token"}


@pytest.mark.parametrize("path, body", ENDPOINTS)
def test_the_per_user_cap_answers_429_with_its_own_code(
    deepseek: FakeDeepSeek, path: str, body: dict
) -> None:
    client = make_client(deepseek, user_daily_call_limit=2)
    for word in ("uno", "dos"):
        sent = body | ({"word": word} if "word" in body else {"text": word})
        assert client.post(path, json=sent, headers=HEADERS).status_code == 200
    blocked = client.post(path, json=body, headers=HEADERS)
    assert (blocked.status_code, blocked.json()) == (
        429,
        {"error": "user_daily_limit_reached"},
    )
    assert len(deepseek.requests) == 2


def test_the_per_user_cap_is_checked_before_the_global_one(
    deepseek: FakeDeepSeek,
) -> None:
    client = make_client(deepseek, user_daily_call_limit=1, daily_call_limit=1)
    client.post("/v1/explain", json=EXPLAIN, headers=HEADERS)
    blocked = client.post(
        "/v1/explain", json=EXPLAIN | {"word": "luz"}, headers=HEADERS
    )
    assert blocked.json() == {"error": "user_daily_limit_reached"}


def test_the_cap_is_per_user_and_the_global_cap_still_applies(
    deepseek: FakeDeepSeek, firebase: FakeFirebase
) -> None:
    client = make_client(
        deepseek, firebase, user_daily_call_limit=1, daily_call_limit=2
    )
    other = firebase.add_user("other@example.test", "another pass")
    firebase.id_tokens["other-token"] = other.uid
    first = client.post("/v1/explain", json=EXPLAIN | {"word": "a"}, headers=HEADERS)
    second = client.post(
        "/v1/explain",
        json=EXPLAIN | {"word": "b"},
        headers=CLIENT_TOKEN | OTHER,
    )
    assert (first.status_code, second.status_code) == (200, 200)
    third = client.post(
        "/v1/explain", json=EXPLAIN | {"word": "c"}, headers=CLIENT_TOKEN | OTHER
    )
    assert third.json() == {"error": "user_daily_limit_reached"}


def test_the_global_cap_is_still_reported_with_its_own_code(
    deepseek: FakeDeepSeek, firebase: FakeFirebase
) -> None:
    client = make_client(deepseek, firebase, daily_call_limit=1)
    other = firebase.add_user("other@example.test", "another pass")
    firebase.id_tokens["other-token"] = other.uid
    client.post("/v1/explain", json=EXPLAIN | {"word": "a"}, headers=HEADERS)
    blocked = client.post(
        "/v1/explain", json=EXPLAIN | {"word": "b"}, headers=CLIENT_TOKEN | OTHER
    )
    assert blocked.json() == {"error": "daily_limit_reached"}


def test_a_cache_hit_consumes_neither_cap(deepseek: FakeDeepSeek) -> None:
    client = make_client(deepseek, user_daily_call_limit=1, daily_call_limit=1)
    for _ in range(3):
        assert (
            client.post("/v1/explain", json=EXPLAIN, headers=HEADERS).status_code == 200
        )
    assert len(deepseek.requests) == 1


def test_a_failed_upstream_call_does_not_cache_but_does_count(
    deepseek: FakeDeepSeek,
) -> None:
    import httpx

    deepseek.handler = lambda request: httpx.Response(500)
    client = make_client(deepseek, user_daily_call_limit=1)
    assert client.post("/v1/explain", json=EXPLAIN, headers=HEADERS).status_code == 502
    again = client.post("/v1/explain", json=EXPLAIN, headers=HEADERS)
    assert again.json() == {"error": "user_daily_limit_reached"}
