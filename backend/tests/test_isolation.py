"""Multi-tenant isolation: every Firestore access uses the uid of the verified token."""

import asyncio

import httpx
import pytest
from conftest import BEARER, FakeDeepSeek, make_client
from fake_firebase import DEFAULT_UID, FakeFirebase, User
from fastapi.testclient import TestClient
from test_google_auth import begin, callback, start

from clearread_backend.errors import ApiError
from clearread_backend.firebase import FirestoreGateway

OTHER_TOKEN = "other-id-token"
OTHER_HEADERS = {"Authorization": f"Bearer {OTHER_TOKEN}"}
OTHER_PASSWORD = {"password": "another horse"}


def profile(language: str, word: str) -> dict:
    return {
        "settings": {"ui_language": language},
        "words": [{"word": word}],
        "topics": [],
        "updated_at": "2026-10-20T12:00:00Z",
    }


@pytest.fixture
def other(firebase: FakeFirebase) -> User:
    user = firebase.add_user("other@example.test", "another horse", "Bea", "uid-other")
    firebase.id_tokens[OTHER_TOKEN] = user.uid
    return user


@pytest.fixture
def web(deepseek: FakeDeepSeek, firebase: FakeFirebase, other: User) -> TestClient:
    return make_client(deepseek, firebase)


def firestore_uids(firebase: FakeFirebase) -> set[str]:
    return {
        call.url.path.rsplit("/", 1)[1]
        for call in firebase.calls
        if call.url.host == "firestore.googleapis.com"
    }


def test_two_users_keep_separate_profiles(
    web: TestClient, firebase: FakeFirebase, other: User
) -> None:
    assert web.put("/v1/profile", json=profile("es", "uno"), headers=BEARER).is_success
    assert web.put(
        "/v1/profile", json=profile("en", "two"), headers=OTHER_HEADERS
    ).is_success
    mine = web.get("/v1/profile", headers=BEARER).json()
    theirs = web.get("/v1/profile", headers=OTHER_HEADERS).json()
    assert mine["words"] == [{"word": "uno"}]
    assert theirs["words"] == [{"word": "two"}]
    assert set(firebase.documents) == {DEFAULT_UID, other.uid}


def test_a_new_user_does_not_see_another_users_profile(
    web: TestClient, other: User
) -> None:
    web.put("/v1/profile", json=profile("es", "uno"), headers=BEARER)
    response = web.get("/v1/profile", headers=OTHER_HEADERS)
    assert (response.status_code, response.json()) == (
        404,
        {"error": "profile_not_found"},
    )


def test_a_uid_in_the_body_or_the_query_cannot_address_another_profile(
    web: TestClient, firebase: FakeFirebase, other: User
) -> None:
    web.put("/v1/profile", json=profile("es", "uno"), headers=BEARER)
    forged = profile("en", "evil") | {"uid": DEFAULT_UID, "id": DEFAULT_UID}
    response = web.put(
        f"/v1/profile?uid={DEFAULT_UID}", json=forged, headers=OTHER_HEADERS
    )
    assert response.is_success
    web.get(f"/v1/profile?uid={other.uid}", headers=BEARER)
    mine = web.get("/v1/profile", headers=BEARER).json()
    assert mine["words"] == [{"word": "uno"}]
    assert set(firebase.documents) == {DEFAULT_UID, other.uid}
    assert "uid" not in firebase.documents[other.uid]


def test_there_is_no_route_that_takes_a_uid_in_the_path(web: TestClient) -> None:
    for path in (f"/v1/profile/{DEFAULT_UID}", f"/v1/account/{DEFAULT_UID}"):
        assert web.get(path, headers=OTHER_HEADERS).status_code in (404, 405)
        assert web.delete(path, headers=OTHER_HEADERS).status_code in (404, 405)


def test_every_firestore_call_targets_the_uid_of_the_calling_token(
    web: TestClient, firebase: FakeFirebase, other: User
) -> None:
    web.put("/v1/profile", json=profile("es", "uno"), headers=BEARER)
    web.get("/v1/profile", headers=BEARER)
    assert firestore_uids(firebase) == {DEFAULT_UID}
    firebase.calls.clear()
    web.put("/v1/profile", json=profile("en", "two"), headers=OTHER_HEADERS)
    web.get("/v1/profile", headers=OTHER_HEADERS)
    web.request("DELETE", "/v1/account", json=OTHER_PASSWORD, headers=OTHER_HEADERS)
    assert firestore_uids(firebase) == {other.uid}


def test_deleting_one_account_leaves_the_other_untouched(
    web: TestClient, firebase: FakeFirebase, other: User
) -> None:
    web.put("/v1/profile", json=profile("es", "uno"), headers=BEARER)
    web.put("/v1/profile", json=profile("en", "two"), headers=OTHER_HEADERS)
    deleted = web.request(
        "DELETE", "/v1/account", json=OTHER_PASSWORD, headers=OTHER_HEADERS
    )
    assert deleted.status_code == 204
    assert other.email not in firebase.users
    assert other.uid not in firebase.documents
    assert DEFAULT_UID in firebase.documents
    assert web.get("/v1/profile", headers=BEARER).json()["words"] == [{"word": "uno"}]


def test_the_firestore_fake_enforces_the_owner_only_rule(
    firebase: FakeFirebase, other: User
) -> None:
    gateway = FirestoreGateway("fake-project", httpx.MockTransport(firebase))
    with pytest.raises(ApiError) as denied:
        asyncio.run(gateway.get_profile(DEFAULT_UID, OTHER_TOKEN))
    assert denied.value.code == "auth_upstream_error"


def test_the_google_marker_is_written_to_the_verified_user_only(
    web: TestClient, firebase: FakeFirebase, other: User
) -> None:
    other.email_verified = True
    attempt = start(web, "link", OTHER_HEADERS)
    assert begin(web, attempt).status_code == 302
    assert callback(web, attempt.state, code="code-bea").status_code == 200
    assert "google_linked_at" in firebase.documents[other.uid]
    assert DEFAULT_UID not in firebase.documents
    assert firestore_uids(firebase) == {other.uid}
