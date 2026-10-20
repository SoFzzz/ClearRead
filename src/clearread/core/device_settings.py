"""Per-computer look of the screens shown before anyone is signed in (v1.6).

Not part of the synced profile: the login screens need a theme and a language before
any profile is open, so the last profile's choice is remembered here.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from clearread.core.config import THEME_IDS, UI_LANGUAGES, AppConfig
from clearread.services.atomic_json import write_json_atomic

DEVICE_FILE = "device.json"


@dataclass(frozen=True)
class DeviceSettings:
    theme: str = "light"
    ui_language: str = "es"

    @classmethod
    def from_config(cls, config: AppConfig) -> "DeviceSettings":
        return cls(theme=config.theme, ui_language=config.ui_language)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DeviceSettings":
        defaults = cls()
        theme, language = data.get("theme"), data.get("ui_language")
        return cls(
            theme=theme if theme in THEME_IDS else defaults.theme,
            ui_language=language if language in UI_LANGUAGES else defaults.ui_language,
        )


class DeviceSettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> DeviceSettings:
        """Safe defaults when the file is missing or damaged."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return DeviceSettings()
        return (
            DeviceSettings.from_dict(data)
            if isinstance(data, dict)
            else DeviceSettings()
        )

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, settings: DeviceSettings) -> None:
        try:
            write_json_atomic(self._path, asdict(settings))
        except OSError:
            pass  # the login screens just fall back to the defaults next time


def seed_from_legacy_config(store: DeviceSettingsStore, data_dir: Path) -> None:
    """First run of v1.6: the login screens inherit the look of the pre-accounts config."""
    if not store.exists():
        store.save(DeviceSettings.from_config(AppConfig.load(data_dir)))
