"""BE-F03: no log carries the received texts, DeepSeek's replies or the key."""

import logging

import httpx
import pytest
from conftest import FAKE_KEY, HEADERS, FakeDeepSeek, completion, make_client

from clearread_backend.settings import Settings

SECRET_WORD = "zorbalimento"
SECRET_CONTEXT = "El zorbalimento ocurre en la casa de Marta Ejemplo."
SECRET_REPLY = "Respuesta confidencial del modelo."
SECRET_TEXT = "Texto privado de prueba sobre Marta Ejemplo y su cuaderno."


def all_log_text(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def assert_nothing_leaked(caplog: pytest.LogCaptureFixture) -> None:
    logged = all_log_text(caplog)
    for secret in (SECRET_WORD, SECRET_CONTEXT, SECRET_REPLY, SECRET_TEXT, FAKE_KEY):
        assert secret not in logged
    assert "Marta" not in logged


def test_a_successful_request_logs_no_text(
    caplog: pytest.LogCaptureFixture, deepseek: FakeDeepSeek
) -> None:
    deepseek.handler = lambda r: completion(SECRET_REPLY)
    client = make_client(deepseek)
    caplog.set_level(logging.DEBUG)
    body = {"word": SECRET_WORD, "context_sentence": SECRET_CONTEXT, "lang": "es"}
    assert client.post("/v1/explain", json=body, headers=HEADERS).status_code == 200
    assert (
        client.post(
            "/v1/simplify", json={"text": SECRET_TEXT, "lang": "es"}, headers=HEADERS
        ).status_code
        == 200
    )
    assert_nothing_leaked(caplog)


def test_error_paths_log_only_our_code(
    caplog: pytest.LogCaptureFixture, deepseek: FakeDeepSeek
) -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text=f"{SECRET_REPLY} {SECRET_TEXT}")

    deepseek.handler = failing
    client = make_client(deepseek)
    caplog.set_level(logging.DEBUG)
    body = {"word": SECRET_WORD, "context_sentence": SECRET_CONTEXT, "lang": "es"}
    assert client.post("/v1/explain", json=body, headers=HEADERS).status_code == 502
    assert (
        client.post(
            "/v1/explain", json=body | {"word": "x" * 41}, headers=HEADERS
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/v1/explain", json=body | {"lang": "fr"}, headers=HEADERS
        ).status_code
        == 422
    )
    assert client.post("/v1/explain", json=body).status_code == 401
    assert_nothing_leaked(caplog)
    assert "upstream_no_balance" in all_log_text(caplog)


def test_the_key_is_not_in_the_docs_or_the_openapi_schema(
    deepseek: FakeDeepSeek,
) -> None:
    client = make_client(deepseek)
    assert FAKE_KEY not in client.get("/openapi.json").text
    assert FAKE_KEY not in client.get("/docs").text


def test_settings_read_the_documented_variables_with_safe_defaults() -> None:
    defaults = Settings.from_env({})
    assert (defaults.deepseek_model, defaults.daily_call_limit) == (
        "deepseek-flash",
        45,
    )
    assert defaults.deepseek_base_url == "https://api.deepseek.com"
    given = Settings.from_env(
        {
            "DEEPSEEK_API_KEY": "k",
            "DEEPSEEK_MODEL": "m",
            "DEEPSEEK_BASE_URL": "https://example.test",
            "CLIENT_TOKEN": "t",
            "DAILY_CALL_LIMIT": "3",
        }
    )
    assert given == Settings("k", "m", "https://example.test", "t", 3)
