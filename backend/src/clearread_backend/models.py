"""Request and response models of the account and profile endpoints."""

from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PASSWORD_MIN_CHARS = 8
PASSWORD_MAX_CHARS = 128
DISPLAY_NAME_MAX_CHARS = 40

# Passwords are never stripped: surrounding spaces are part of the secret.
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=EMAIL_PATTERN),
]
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
