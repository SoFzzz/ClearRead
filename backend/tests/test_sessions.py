"""Token verification: the Bearer dependency and its in-memory cache."""

import asyncio
import base64
import json

import httpx
import pytest
from conftest import BEARER
from fake_firebase import DEFAULT_TOKEN, DEFAULT_UID, FakeFirebase, firebase_error
from fastapi.testclient import TestClient

from clearread_backend.errors import ApiError
from clearread_backend.firebase import AccountInfo, FirebaseAuthGateway
from clearread_backend.sessions import (
    MAX_CACHE_TTL_S,
    UNKNOWN_EXPIRY_TTL_S,
    TokenVerifier,
    bearer_token,
    token_expiry,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def jwt_expiring_at(expiry: float) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode())
    return f"header.{payload.decode().rstrip('=')}.signature"


def verify(verifier: TokenVerifier, token: str) -> AccountInfo:
    return asyncio.run(verifier.verify(token))


def make_verifier(
    firebase: FakeFirebase, clock: Clock, max_entries: int = 1000
) -> TokenVerifier:
    gateway = FirebaseAuthGateway("key", httpx.MockTransport(firebase))
    return TokenVerifier(gateway, clock, max_entries)


def test_a_verified_token_is_looked_up_once_until_the_ttl_ends(
    firebase: FakeFirebase,
) -> None:
    clock = Clock()
    verifier = make_verifier(firebase, clock)
    for _ in range(3):
        info = verify(verifier, DEFAULT_TOKEN)
    assert info.uid == DEFAULT_UID
    assert len(firebase.calls_to("lookup")) == 1
    clock.now += UNKNOWN_EXPIRY_TTL_S + 1
    verify(verifier, DEFAULT_TOKEN)
    assert len(firebase.calls_to("lookup")) == 2


def test_the_ttl_follows_the_token_expiry_and_never_exceeds_one_hour(
    firebase: FakeFirebase,
) -> None:
    clock = Clock()
    verifier = make_verifier(firebase, clock)
    short = jwt_expiring_at(clock.now + 120)
    long = jwt_expiring_at(clock.now + 86_400)
    firebase.id_tokens |= {short: DEFAULT_UID, long: DEFAULT_UID}
    verify(verifier, short)
    verify(verifier, long)
    assert len(firebase.calls_to("lookup")) == 2
    clock.now += 121
    verify(verifier, short)
    verify(verifier, long)
    assert len(firebase.calls_to("lookup")) == 3
    clock.now += MAX_CACHE_TTL_S
    verify(verifier, long)
    assert len(firebase.calls_to("lookup")) == 4


def test_the_cache_is_bounded_and_drops_the_oldest(
    firebase: FakeFirebase,
) -> None:
    verifier = make_verifier(firebase, Clock(), max_entries=2)
    tokens = ["t1", "t2", "t3"]
    firebase.id_tokens |= {token: DEFAULT_UID for token in tokens}
    for token in tokens:
        verify(verifier, token)
    verify(verifier, "t3")
    verify(verifier, "t1")
    assert len(firebase.calls_to("lookup")) == 4


def test_a_rejected_token_is_not_cached(firebase: FakeFirebase) -> None:
    verifier = make_verifier(firebase, Clock())
    for _ in range(2):
        with pytest.raises(ApiError) as caught:
            verify(verifier, "forged")
        assert (caught.value.status_code, caught.value.code) == (401, "invalid_session")
    assert len(firebase.calls_to("lookup")) == 2


def test_forget_drops_a_cached_token(firebase: FakeFirebase) -> None:
    verifier = make_verifier(firebase, Clock())
    verify(verifier, DEFAULT_TOKEN)
    verifier.forget(DEFAULT_TOKEN)
    verify(verifier, DEFAULT_TOKEN)
    assert len(firebase.calls_to("lookup")) == 2


def test_the_cache_key_is_a_hash_not_the_token(firebase: FakeFirebase) -> None:
    verifier = make_verifier(firebase, Clock())
    assert DEFAULT_TOKEN not in vars(verifier)["_entries"]


def test_token_expiry_reads_the_exp_claim_or_nothing() -> None:
    assert token_expiry(jwt_expiring_at(1234.0)) == 1234.0
    assert token_expiry("opaque") is None
    assert token_expiry("a.b.c") is None


@pytest.mark.parametrize(
    "header, expected",
    [("Bearer abc", "abc"), ("bearer  abc ", "abc"), ("BEARER abc", "abc")],
)
def test_bearer_token_extracts_the_token(header: str, expected: str) -> None:
    assert bearer_token(header) == expected


@pytest.mark.parametrize("header", ["", "abc", "Bearer", "Bearer   ", "Basic abc"])
def test_bearer_token_rejects_anything_else(header: str) -> None:
    with pytest.raises(ApiError) as caught:
        bearer_token(header)
    assert caught.value.code == "invalid_session"


def test_requests_with_the_same_token_look_it_up_once(
    client: TestClient, firebase: FakeFirebase
) -> None:
    for _ in range(3):
        assert client.get("/v1/profile", headers=BEARER).status_code == 404
    assert len(firebase.calls_to("lookup")) == 1


def test_firebase_failing_during_verification_is_reported_as_a_gateway_error(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["lookup"] = httpx.Response(500)
    response = client.get("/v1/profile", headers=BEARER)
    assert (response.status_code, response.json()) == (
        502,
        {"error": "auth_upstream_error"},
    )


@pytest.mark.parametrize(
    "code", ["INVALID_ID_TOKEN", "USER_NOT_FOUND", "TOKEN_EXPIRED"]
)
def test_every_rejected_token_is_invalid_session(
    client: TestClient, firebase: FakeFirebase, code: str
) -> None:
    firebase.failures["lookup"] = firebase_error(code)
    response = client.get("/v1/profile", headers=BEARER)
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_session"},
    )
