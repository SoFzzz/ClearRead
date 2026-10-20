"""device.json: the look of the login screens, read with safe defaults and written whole."""

import json
from pathlib import Path

from clearread.core.config import AppConfig
from clearread.core.device_settings import (
    DeviceSettings,
    DeviceSettingsStore,
    seed_from_legacy_config,
)


def test_missing_file_gives_the_defaults(tmp_path: Path) -> None:
    assert DeviceSettingsStore(tmp_path / "device.json").load() == DeviceSettings(
        "light", "es"
    )


def test_damaged_or_wrong_files_give_the_defaults(tmp_path: Path) -> None:
    path = tmp_path / "device.json"
    store = DeviceSettingsStore(path)
    for content in ("{not json", "[1, 2]", '"dark"', ""):
        path.write_text(content, encoding="utf-8")
        assert store.load() == DeviceSettings()


def test_unknown_values_fall_back_one_by_one(tmp_path: Path) -> None:
    path = tmp_path / "device.json"
    path.write_text(
        json.dumps({"theme": "neon", "ui_language": "en"}), encoding="utf-8"
    )
    assert DeviceSettingsStore(path).load() == DeviceSettings("light", "en")
    path.write_text(json.dumps({"theme": "dark", "ui_language": 7}), encoding="utf-8")
    assert DeviceSettingsStore(path).load() == DeviceSettings("dark", "es")


def test_round_trip_and_no_temporary_file_left(tmp_path: Path) -> None:
    store = DeviceSettingsStore(tmp_path / "device.json")
    store.save(DeviceSettings("dark", "en"))
    assert store.load() == DeviceSettings("dark", "en")
    assert [p.name for p in tmp_path.iterdir()] == ["device.json"]


def test_saving_into_a_missing_folder_creates_it(tmp_path: Path) -> None:
    store = DeviceSettingsStore(tmp_path / "new" / "device.json")
    store.save(DeviceSettings("dark", "es"))
    assert store.load().theme == "dark"


def test_a_refused_write_is_not_fatal(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a folder should be", encoding="utf-8")
    DeviceSettingsStore(blocker / "device.json").save(DeviceSettings("dark", "en"))


def test_first_run_inherits_the_look_of_the_old_config(tmp_path: Path) -> None:
    AppConfig(theme="dark", ui_language="en").save(tmp_path)
    store = DeviceSettingsStore(tmp_path / "device.json")
    seed_from_legacy_config(store, tmp_path)
    assert store.load() == DeviceSettings("dark", "en")


def test_seeding_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    AppConfig(theme="dark", ui_language="en").save(tmp_path)
    store = DeviceSettingsStore(tmp_path / "device.json")
    store.save(DeviceSettings("light", "es"))
    seed_from_legacy_config(store, tmp_path)
    assert store.load() == DeviceSettings("light", "es")
