"""Configuration read from environment variables (and backend/.env in development)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_DAILY_CALL_LIMIT = 45
DEFAULT_USER_DAILY_CALL_LIMIT = 15
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    client_token: str
    daily_call_limit: int
    firebase_api_key: str = ""
    firebase_project_id: str = ""
    user_daily_call_limit: int = DEFAULT_USER_DAILY_CALL_LIMIT
    google_client_id: str = ""
    google_client_secret: str = ""
    public_base_url: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        return cls(
            deepseek_api_key=values.get("DEEPSEEK_API_KEY", ""),
            deepseek_model=values.get("DEEPSEEK_MODEL") or DEFAULT_MODEL,
            deepseek_base_url=values.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL,
            client_token=values.get("CLIENT_TOKEN", ""),
            daily_call_limit=int(
                values.get("DAILY_CALL_LIMIT") or DEFAULT_DAILY_CALL_LIMIT
            ),
            firebase_api_key=values.get("FIREBASE_API_KEY", ""),
            firebase_project_id=values.get("FIREBASE_PROJECT_ID", ""),
            user_daily_call_limit=int(
                values.get("USER_DAILY_CALL_LIMIT") or DEFAULT_USER_DAILY_CALL_LIMIT
            ),
            google_client_id=values.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            google_client_secret=values.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            public_base_url=(
                values.get("PUBLIC_BASE_URL") or values.get("RENDER_EXTERNAL_URL", "")
            )
            .strip()
            .rstrip("/"),
        )

    @property
    def google_configured(self) -> bool:
        return bool(
            self.google_client_id and self.google_client_secret and self.public_base_url
        )

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url}/v1/auth/google/callback"

    @property
    def auth_configured(self) -> bool:
        return bool(self.firebase_api_key and self.firebase_project_id)


def load_env_file(path: Path = ENV_FILE) -> None:
    """Put ``KEY=value`` lines of a local .env into the environment.

    Real environment variables win, so the hosting panel overrides a stray file.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
