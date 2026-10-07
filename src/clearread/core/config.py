"""Atomic configuration manager with crash-resilience (§4.6)."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from clearread.core.paths import get_user_data_dir

# The only URL allowed outside services/ai_client.py (NFR-OFF01 audit).
# Placeholder until the real Render URL exists (Day 10, §6.5).
DEFAULT_BACKEND_URL = "https://clearread-api.onrender.com"

THEME_IDS = ("light", "dark", "high_contrast")
UI_LANGUAGES = ("es", "en")
FONT_SIZE_RANGE_PT = (12, 28)
LINE_SPACING_RANGE = (1.4, 2.6)
LETTER_SPACING_RANGE_PX = (0.0, 4.0)
WORD_SPACING_RANGE_PX = (0, 12)
READING_SPEED_RANGE_WPM = (80, 320)
_URL_SCHEMES = ("https", "http")


def is_backend_url(text: str) -> bool:
    scheme, separator, rest = text.strip().partition(":" + "//")
    return scheme in _URL_SCHEMES and bool(separator) and bool(rest)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def _choice(value: object, allowed: tuple[str, ...], fallback: str) -> str:
    return value if isinstance(value, str) and value in allowed else fallback


def _boolean(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _number(
    value: object,
    bounds: tuple[float, float],
    default: float,
    kind: type[int] | type[float],
) -> Any:
    if not _is_number(value):
        return kind(default)
    clamped = _clamp(float(value), bounds)  # type: ignore[arg-type]
    return round(clamped) if kind is int else clamped


def _backend_url(value: object) -> str:
    if isinstance(value, str) and is_backend_url(value):
        return value.strip()
    return DEFAULT_BACKEND_URL


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
        try:
            with open(config_path, encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError):
            return cls()
        return cls.from_dict(data) if isinstance(data, dict) else cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        """Build a valid config: unknown keys are ignored, bad values fall back."""
        defaults = cls()
        known = {f.name for f in fields(cls)}
        merged = {**asdict(defaults), **{k: v for k, v in data.items() if k in known}}
        return cls(**merged).validated(defaults)

    def validated(self, fallback: "AppConfig | None" = None) -> "AppConfig":
        """Copy with every field inside its allowed range or type.

        Numbers out of range are clamped; values of the wrong type or unknown
        choices take the value from ``fallback`` (the defaults when omitted).
        """
        base = fallback or AppConfig()
        return AppConfig(
            theme=_choice(self.theme, THEME_IDS, base.theme),
            font_size_pt=_number(
                self.font_size_pt, FONT_SIZE_RANGE_PT, base.font_size_pt, int
            ),
            line_spacing=_number(
                self.line_spacing, LINE_SPACING_RANGE, base.line_spacing, float
            ),
            letter_spacing=_number(
                self.letter_spacing,
                LETTER_SPACING_RANGE_PX,
                base.letter_spacing,
                float,
            ),
            word_spacing=_number(
                self.word_spacing, WORD_SPACING_RANGE_PX, base.word_spacing, int
            ),
            syllables_enabled=_boolean(self.syllables_enabled, base.syllables_enabled),
            reading_speed_wpm=_number(
                self.reading_speed_wpm,
                READING_SPEED_RANGE_WPM,
                base.reading_speed_wpm,
                int,
            ),
            voice_id=self.voice_id if isinstance(self.voice_id, str) else "",
            voice_volume=base.voice_volume,
            ai_privacy_accepted=_boolean(self.ai_privacy_accepted, False),
            backend_url=_backend_url(self.backend_url),
            ui_language=_choice(self.ui_language, UI_LANGUAGES, base.ui_language),
        )

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
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_file, str(target_path))
        except BaseException:
            Path(temp_file).unlink(missing_ok=True)
            raise
