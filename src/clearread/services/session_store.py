"""The signed-in session and its encrypted copy on disk.

Only the identity and the refresh token are saved, protected with Windows DPAPI (tied
to the Windows user). The idToken lives in memory only and is never written.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from clearread.core.paths import is_valid_uid
from clearread.services.atomic_json import write_bytes_atomic

SESSION_FILE = "session.bin"
# Binds the encrypted blob to this use, so another DPAPI blob cannot be swapped in.
_ENTROPY = b"ClearRead.session.v1"


@dataclass(frozen=True)
class Session:
    uid: str
    email: str
    display_name: str
    email_verified: bool
    id_token: str
    refresh_token: str
    expires_at: float  # epoch seconds
    google_linked: bool = False


@dataclass(frozen=True)
class StoredSession:
    """What survives a restart: enough to open the profile offline and to refresh."""

    uid: str
    email: str
    display_name: str
    refresh_token: str


def dpapi_protect(data: bytes) -> bytes:
    import win32crypt

    return win32crypt.CryptProtectData(data, None, _ENTROPY, None, None, 0)


def dpapi_unprotect(data: bytes) -> bytes:
    import win32crypt

    return win32crypt.CryptUnprotectData(data, _ENTROPY, None, None, 0)[1]


class SessionStore:
    def __init__(
        self,
        path: Path,
        protect: Callable[[bytes], bytes] = dpapi_protect,
        unprotect: Callable[[bytes], bytes] = dpapi_unprotect,
    ) -> None:
        self._path = path
        self._protect = protect
        self._unprotect = unprotect

    def save(self, stored: StoredSession) -> None:
        """Raises ``OSError`` if the disk refuses; the caller keeps working in memory."""
        raw = json.dumps(asdict(stored)).encode("utf-8")
        try:
            protected = self._protect(raw)
        except Exception as exc:
            raise OSError("cannot encrypt the session") from exc
        write_bytes_atomic(self._path, protected)

    def load(self) -> StoredSession | None:
        """None when the file is missing, damaged or not decryptable by this user."""
        try:
            data = json.loads(self._unprotect(self._path.read_bytes()))
            stored = StoredSession(**data)
        except Exception:  # noqa: BLE001 - any failure just means "no saved session"
            return None
        return stored if _is_well_formed(stored) else None

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)


def _is_well_formed(stored: StoredSession) -> bool:
    texts = (stored.uid, stored.email, stored.display_name, stored.refresh_token)
    return (
        all(isinstance(value, str) for value in texts)
        and is_valid_uid(stored.uid)
        and bool(stored.refresh_token)
    )
