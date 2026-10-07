"""Configuration read from environment variables (and backend/.env in development)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_DAILY_CALL_LIMIT = 45
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    client_token: str
    daily_call_limit: int

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
        )


def load_env_file(path: Path = ENV_FILE) -> None:
    """Put ``KEY=value`` lines of a local .env into the environment.

    Real environment variables win, so the hosting panel overrides a stray file.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
