"""What the account section of Settings shows; no Qt dependency."""

from dataclasses import dataclass
from enum import Enum

from clearread.services.account_client import AccountErrorKind
from clearread.services.session_store import Session, StoredSession


class AccountBusy(Enum):
    """What the account section is doing, so each action shows only its own text."""

    SIGNING_OUT = "signing_out"
    DELETING = "deleting"


class SyncStatus(Enum):
    OK = "ok"
    PENDING = "pending"  # a change waits for the network or the next try
    FAILED = "failed"  # the account refused or errored; it is tried again


@dataclass(frozen=True)
class AccountInfo:
    name: str
    email: str
    verified: bool | None = None  # None until the account has been asked
    google_linked: bool | None = None  # None until the account has been asked

    @classmethod
    def from_session(cls, session: Session) -> "AccountInfo":
        return cls(
            session.display_name or session.email,
            session.email,
            session.email_verified,
            session.google_linked,
        )

    @classmethod
    def from_identity(cls, identity: StoredSession) -> "AccountInfo":
        return cls(identity.display_name or identity.email, identity.email)


def error_text_key(kind: AccountErrorKind) -> str:
    """Catalog key of the message for an account error."""
    return f"auth.error.{kind.name.lower()}"
