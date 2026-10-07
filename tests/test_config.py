"""AppConfig: persistence, atomic writes, corrupt files and value ranges (CFG-F01, §4.6)."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from clearread.core.config import (
    CLIENT_TOKEN_ENV_VAR,
    DEFAULT_BACKEND_URL,
    AppConfig,
    load_client_token,
)

CHANGED = {
    "theme": "dark",
    "font_size_pt": 22,
    "line_spacing": 2.2,
    "letter_spacing": 2.5,
    "word_spacing": 8,
    "syllables_enabled": False,
    "reading_speed_wpm": 210,
    "voice_id": "HKEY_VOICE_7",
    "backend_url": "https://example.test/api",
    "ui_language": "en",
}


@pytest.mark.parametrize(("field", "value"), sorted(CHANGED.items()))
def test_each_setting_persists_and_reloads(
    tmp_path: Path, field: str, value: Any
) -> None:
    config = AppConfig()
    setattr(config, field, value)
    config.save(tmp_path)
    assert getattr(AppConfig.load(tmp_path), field) == value


def test_all_settings_together_round_trip(tmp_path: Path) -> None:
    config = AppConfig(**CHANGED)
    config.save(tmp_path)
    assert AppConfig.load(tmp_path) == config


def test_missing_file_gives_the_defaults(tmp_path: Path) -> None:
    assert AppConfig.load(tmp_path) == AppConfig()


@pytest.mark.parametrize(
    "content", ["", "{not json", "[1, 2, 3]", '"text"', "null", "\x00\x01\x02"]
)
def test_corrupt_config_loads_the_defaults(tmp_path: Path, content: str) -> None:
    (tmp_path / "config.json").write_text(content, encoding="utf-8")
    assert AppConfig.load(tmp_path) == AppConfig()


def test_undecodable_bytes_load_the_defaults(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_bytes(b"\xff\xfe\x00{")
    assert AppConfig.load(tmp_path) == AppConfig()


def test_unknown_fields_are_ignored_and_known_ones_kept(tmp_path: Path) -> None:
    data = {"theme": "dark", "removed_in_v2": 1, "font_size_pt": 20}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    loaded = AppConfig.load(tmp_path)
    assert (loaded.theme, loaded.font_size_pt) == ("dark", 20)
    assert not hasattr(loaded, "removed_in_v2")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("font_size_pt", 5, 12),
        ("font_size_pt", 99, 28),
        ("line_spacing", 0.2, 1.4),
        ("line_spacing", 9, 2.6),
        ("letter_spacing", -3, 0.0),
        ("letter_spacing", 50, 4.0),
        ("word_spacing", -1, 0),
        ("word_spacing", 40, 12),
        ("reading_speed_wpm", 10, 80),
        ("reading_speed_wpm", 900, 320),
        ("reading_speed_wpm", 80, 80),
        ("reading_speed_wpm", 320, 320),
    ],
)
def test_numbers_out_of_range_are_clamped(
    tmp_path: Path, field: str, value: float, expected: float
) -> None:
    (tmp_path / "config.json").write_text(json.dumps({field: value}), encoding="utf-8")
    assert getattr(AppConfig.load(tmp_path), field) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("theme", "neon"),
        ("theme", 3),
        ("font_size_pt", "big"),
        ("font_size_pt", True),
        ("line_spacing", None),
        ("syllables_enabled", "yes"),
        ("reading_speed_wpm", [150]),
        ("ui_language", "fr"),
        ("backend_url", "ftp://somewhere"),
        ("backend_url", ""),
        ("backend_url", 12),
    ],
)
def test_values_of_the_wrong_kind_fall_back_to_the_default(
    tmp_path: Path, field: str, value: Any
) -> None:
    (tmp_path / "config.json").write_text(json.dumps({field: value}), encoding="utf-8")
    assert getattr(AppConfig.load(tmp_path), field) == getattr(AppConfig(), field)


def test_backend_url_must_be_http_or_https() -> None:
    assert AppConfig(backend_url="  https://a.test  ").validated().backend_url == (
        "https://a.test"
    )
    assert AppConfig(backend_url="javascript:x").validated().backend_url == (
        DEFAULT_BACKEND_URL
    )


def test_validation_keeps_the_values_that_are_fine() -> None:
    config = AppConfig(**CHANGED)
    assert config.validated() == config


def test_a_failure_in_the_final_rename_keeps_the_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    AppConfig(font_size_pt=20).save(tmp_path)
    before = (tmp_path / "config.json").read_bytes()

    def failing_replace(source: str, target: str) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError):
        AppConfig(font_size_pt=26).save(tmp_path)

    assert (tmp_path / "config.json").read_bytes() == before
    assert AppConfig.load(tmp_path).font_size_pt == 20
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_failure_halfway_through_writing_keeps_the_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    AppConfig(theme="dark").save(tmp_path)
    before = (tmp_path / "config.json").read_bytes()

    def dump_that_dies(obj: object, file: Any, **kwargs: Any) -> None:
        file.write('{"theme": "high_con')  # half a document, then the crash
        raise OSError("power cut")

    monkeypatch.setattr(json, "dump", dump_that_dies)
    with pytest.raises(OSError):
        AppConfig(theme="high_contrast").save(tmp_path)

    assert (tmp_path / "config.json").read_bytes() == before
    assert AppConfig.load(tmp_path).theme == "dark"
    assert list(tmp_path.glob("*.tmp")) == []


def test_saved_file_holds_every_field_as_utf8_json(tmp_path: Path) -> None:
    AppConfig(voice_id="voz-ñ").save(tmp_path)
    data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert data == asdict(AppConfig(voice_id="voz-ñ"))


def test_client_token_prefers_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(CLIENT_TOKEN_ENV_VAR, "  from-env ")
    monkeypatch.setattr(
        "clearread.core.config.get_resource_path", lambda relative: tmp_path / "x"
    )
    assert load_client_token() == "from-env"


def test_client_token_reads_build_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(CLIENT_TOKEN_ENV_VAR, raising=False)
    token_file = tmp_path / "token.json"
    token_file.write_text('{"client_token": "from-file"}', encoding="utf-8")
    monkeypatch.setattr(
        "clearread.core.config.get_resource_path", lambda relative: token_file
    )
    assert load_client_token() == "from-file"


@pytest.mark.parametrize("content", [None, "{broken", "[1]", '{"client_token": 3}'])
def test_client_token_is_empty_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str | None
) -> None:
    monkeypatch.delenv(CLIENT_TOKEN_ENV_VAR, raising=False)
    token_file = tmp_path / "token.json"
    if content is not None:
        token_file.write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        "clearread.core.config.get_resource_path", lambda relative: token_file
    )
    assert load_client_token() == ""
