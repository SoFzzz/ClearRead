"""The synced profile endpoints and their Firestore storage."""

from copy import deepcopy
from typing import Any

import httpx
import pytest
from conftest import BEARER
from fake_firebase import DEFAULT_UID, FakeFirebase, firebase_error
from fastapi.testclient import TestClient

from clearread_backend.firestore_values import decode_fields
from clearread_backend.profile import PROFILE_MAX_BYTES, PROFILE_MAX_WORDS

PROFILE: dict[str, Any] = {
    "settings": {"ui_language": "es", "font_size": 18, "high_contrast": False},
    "words": [{"word": "fotosíntesis", "explanation": "Cómo comen las plantas."}],
    "topics": [{"name": "Biología", "words": 3}],
    "updated_at": "2026-10-19T12:00:00Z",
}


def put(client: TestClient, body: object) -> httpx.Response:
    return client.put("/v1/profile", json=body, headers=BEARER)


def test_get_without_a_stored_profile_is_404(client: TestClient) -> None:
    response = client.get("/v1/profile", headers=BEARER)
    assert (response.status_code, response.json()) == (
        404,
        {"error": "profile_not_found"},
    )


def test_put_then_get_returns_the_same_profile(client: TestClient) -> None:
    saved = put(client, PROFILE)
    assert saved.status_code == 200
    fetched = client.get("/v1/profile", headers=BEARER)
    assert fetched.status_code == 200
    assert fetched.json() == saved.json()
    assert fetched.json()["words"] == PROFILE["words"]
    assert fetched.json()["settings"] == PROFILE["settings"]
    assert fetched.json()["updated_at"].startswith("2026-10-19T12:00:00")


def test_the_profile_is_stored_with_the_documented_firestore_fields(
    client: TestClient, firebase: FakeFirebase
) -> None:
    put(client, PROFILE)
    fields = firebase.documents[DEFAULT_UID]
    assert set(fields) == {
        "settings",
        "words",
        "topics",
        "updated_at",
        "schema_version",
    }
    assert fields["updated_at"] == {"timestampValue": "2026-10-19T12:00:00Z"}
    assert fields["schema_version"] == {"integerValue": "1"}
    assert "mapValue" in fields["settings"]
    assert "arrayValue" in fields["words"]
    assert decode_fields(fields)["settings"]["font_size"] == 18
    assert decode_fields(fields)["settings"]["high_contrast"] is False


def test_firestore_is_called_as_the_user_on_their_own_document(
    client: TestClient, firebase: FakeFirebase
) -> None:
    put(client, PROFILE)
    call = firebase.calls_to("firestore")[0]
    assert call.method == "PATCH"
    assert call.url.path.endswith(
        f"/projects/fake-project/databases/(default)/documents/profiles/{DEFAULT_UID}"
    )
    assert call.headers["authorization"] == BEARER["Authorization"]


def test_a_second_put_replaces_the_first(
    client: TestClient, firebase: FakeFirebase
) -> None:
    put(client, PROFILE)
    newer = PROFILE | {"words": [], "updated_at": "2026-10-20T08:00:00+02:00"}
    assert put(client, newer).status_code == 200
    body = client.get("/v1/profile", headers=BEARER).json()
    assert body["words"] == []
    assert body["updated_at"].startswith("2026-10-20T06:00:00")


def test_a_profile_is_private_to_its_owner(
    client: TestClient, firebase: FakeFirebase
) -> None:
    put(client, PROFILE)
    other = firebase.add_user("other@example.test", "another pass")
    firebase.id_tokens["other-token"] = other.uid
    response = client.get(
        "/v1/profile", headers={"Authorization": "Bearer other-token"}
    )
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["get", "put"])
@pytest.mark.parametrize(
    "header",
    [
        {},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer unknown"},
    ],
)
def test_the_profile_needs_a_valid_bearer_token(
    client: TestClient, path: str, header: dict
) -> None:
    response = (
        client.get("/v1/profile", headers=header)
        if path == "get"
        else client.put("/v1/profile", json=PROFILE, headers=header)
    )
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_session"},
    )


def test_a_profile_with_too_many_words_is_413(
    client: TestClient, firebase: FakeFirebase
) -> None:
    words = [{"w": str(i)} for i in range(PROFILE_MAX_WORDS + 1)]
    response = put(client, PROFILE | {"words": words})
    assert (response.status_code, response.json()) == (
        413,
        {"error": "profile_too_large"},
    )
    assert firebase.documents == {}


def test_the_word_limit_is_inclusive(client: TestClient) -> None:
    words = [{"w": str(i)} for i in range(PROFILE_MAX_WORDS)]
    assert put(client, PROFILE | {"words": words}).status_code == 200


def test_a_profile_over_900_kb_is_413(
    client: TestClient, firebase: FakeFirebase
) -> None:
    big = PROFILE | {"settings": {"blob": "x" * (PROFILE_MAX_BYTES + 1)}}
    response = put(client, big)
    assert (response.status_code, response.json()) == (
        413,
        {"error": "profile_too_large"},
    )
    assert firebase.documents == {}


def test_a_profile_just_under_900_kb_is_accepted(client: TestClient) -> None:
    ok = PROFILE | {"settings": {"blob": "x" * (PROFILE_MAX_BYTES - 1000)}}
    assert put(client, ok).status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"settings": []},
        {"words": {}},
        {"words": ["not an object"]},
        {"topics": None},
        {"updated_at": "yesterday"},
        {"updated_at": "2026-10-19T12:00:00"},
    ],
)
def test_a_malformed_profile_is_422(client: TestClient, change: dict) -> None:
    response = put(client, PROFILE | change)
    assert (response.status_code, response.json()) == (
        422,
        {"error": "invalid_request"},
    )


def test_a_missing_field_is_422(client: TestClient) -> None:
    body = deepcopy(PROFILE)
    del body["topics"]
    assert put(client, body).status_code == 422


def test_a_stored_document_that_cannot_be_read_is_an_upstream_error(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.documents[DEFAULT_UID] = {"settings": {"stringValue": "not a map"}}
    response = client.get("/v1/profile", headers=BEARER)
    assert (response.status_code, response.json()) == (
        502,
        {"error": "auth_upstream_error"},
    )


@pytest.mark.parametrize(
    "forced, status, code",
    [
        (httpx.ReadTimeout("slow"), 504, "auth_upstream_timeout"),
        (httpx.ConnectError("down"), 502, "auth_upstream_error"),
        (httpx.Response(500), 502, "auth_upstream_error"),
        (
            httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}),
            502,
            "auth_upstream_error",
        ),
        (httpx.Response(401), 401, "invalid_session"),
    ],
)
def test_firestore_failures_become_stable_codes(
    client: TestClient,
    firebase: FakeFirebase,
    forced: httpx.Response | Exception,
    status: int,
    code: str,
) -> None:
    client.get("/v1/profile", headers=BEARER)  # warm the token cache
    firebase.failures["firestore"] = forced
    for response in (
        client.get("/v1/profile", headers=BEARER),
        put(client, PROFILE),
    ):
        assert (response.status_code, response.json()) == (status, {"error": code})


def test_a_failing_token_check_is_reported_before_the_profile_is_touched(
    client: TestClient, firebase: FakeFirebase
) -> None:
    firebase.failures["lookup"] = firebase_error("TOKEN_EXPIRED")
    response = client.get("/v1/profile", headers=BEARER)
    assert (response.status_code, response.json()) == (
        401,
        {"error": "invalid_session"},
    )
    assert firebase.calls_to("firestore") == []
