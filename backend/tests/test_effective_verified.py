"""A linked Google account with the same email counts as a confirmed email."""

import asyncio

import httpx
import pytest
from fake_firebase import DEFAULT_EMAIL, DEFAULT_TOKEN, FakeFirebase

from clearread_backend.firebase import FirebaseAuthGateway


def verified_after_lookup(
    firebase: FakeFirebase, google_email: str | None, *, firebase_flag: bool
) -> bool:
    user = firebase.users[DEFAULT_EMAIL]
    user.email_verified = firebase_flag
    if google_email is not None:
        user.providers.append("google.com")
        user.google_email = google_email
    gateway = FirebaseAuthGateway("key", httpx.MockTransport(firebase))
    return asyncio.run(gateway.lookup(DEFAULT_TOKEN)).email_verified


@pytest.mark.parametrize(
    ("google_email", "flag", "expected"),
    [
        (" Student@Example.TEST ", False, True),
        (DEFAULT_EMAIL, False, True),
        ("other@example.test", False, False),
        ("other@example.test", True, True),
        (None, False, False),
        (None, True, True),
        ("", False, False),
    ],
)
def test_effective_verified(
    google_email: str | None, flag: bool, expected: bool
) -> None:
    result = verified_after_lookup(FakeFirebase(), google_email, firebase_flag=flag)
    assert result is expected


def test_google_without_an_email_falls_back_to_the_firebase_flag() -> None:
    firebase = FakeFirebase()
    firebase.users[DEFAULT_EMAIL].providers.append("google.com")
    gateway = FirebaseAuthGateway("key", httpx.MockTransport(firebase))
    assert asyncio.run(gateway.lookup(DEFAULT_TOKEN)).email_verified is False
