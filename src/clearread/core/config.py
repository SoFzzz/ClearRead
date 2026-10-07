"""Atomic configuration manager with crash-resilience (§4.6)."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from clearread.core.paths import get_user_data_dir

# The only URL allowed outside services/ai_client.py (NFR-OFF01 audit).
# Placeholder until the real Render URL exists (Day 10, §6.5).
DEFAULT_BACKEND_URL = "https://clearread-api.onrender.com"


@dataclass
class AppConfig:
    theme: str = "light"  # ThemeId value: "light" | "dark" | "high_contrast"
    font_size_pt: int = 16
    line_spacing: float = 1.8
    letter_spacing: float = 1.5  # px
    word_spacing: int = 4  # px
    syllables_enabled: bool = True
    reading_speed_wpm: int = 150
    voice_id: str = ""  # SAPI5 voice id; empty means the system default voice
    voice_volume: float = 1.0  # fixed: no UI control, the Windows volume applies
    ai_privacy_accepted: bool = False  # privacy notice before the first AI call
    backend_url: str = DEFAULT_BACKEND_URL  # editable in advanced settings (CFG-F02)
    ui_language: str = "es"  # "es" | "en": interface language only (I18N-F01)

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "AppConfig":
        config_path = (config_dir or get_user_data_dir()) / "config.json"
        if not config_path.exists():
            return cls()
        try:
            with open(config_path, encoding="utf-8") as file:
                data = json.load(file)
            return cls(
                **{k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            )
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, config_dir: Path | None = None) -> None:
        target_path = (config_dir or get_user_data_dir()) / "config.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file and rename: a crash never leaves a half-written config.
        temp_fd, temp_file = tempfile.mkstemp(
            dir=str(target_path.parent), prefix="cfg_", suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as file:
                json.dump(asdict(self), file, indent=2, ensure_ascii=False)
            os.replace(temp_file, str(target_path))
        except OSError:
            if os.path.exists(temp_file):
                os.remove(temp_file)
            raise
