"""Request and response models of the account and profile endpoints."""

from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
EMAIL_MAX_CHARS = 64
PASSWORD_MIN_CHARS = 8
PASSWORD_MAX_CHARS = 32
DISPLAY_NAME_MAX_CHARS = 32

# Firebase treats emails case-insensitively, so every spelling is folded to one.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=EMAIL_MAX_CHARS,
        pattern=EMAIL_PATTERN,
    ),
]
# Passwords are never stripped: surrounding spaces are part of the secret.
Password = Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_CHARS)]


class RegisterRequest(BaseModel):
    email: Email
    password: Password
    display_name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=DISPLAY_NAME_MAX_CHARS
        ),
    ]


class LoginRequest(BaseModel):
    email: Email
    password: Password


class DeleteAccountRequest(BaseModel):
    password: Password


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1, max_length=4096)]


class PasswordResetRequest(BaseModel):
    email: Email


class SessionResponse(BaseModel):
    uid: str
    email: str
    display_name: str
    email_verified: bool
    id_token: str
    refresh_token: str
    expires_in: int
    google_linked: bool


class Profile(BaseModel):
    settings: dict[str, Any]
    words: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    updated_at: AwareDatetime
