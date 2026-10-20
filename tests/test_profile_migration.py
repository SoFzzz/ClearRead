"""The first profile adopts the legacy root files; a marker blocks any second one."""

import json
from pathlib import Path

import pytest

from clearread.core import paths
from clearread.services.profile_migration import (
    ADOPTION_MARKER,
    LEGACY_ITEMS,
    adopt_legacy_data,
)


def make_legacy(data_dir: Path, names: tuple[str, ...] = LEGACY_ITEMS) -> None:
    for name in names:
        if name == "cache":
            (data_dir / "cache").mkdir()
            (data_dir / "cache" / "doc.json").write_text("{}", encoding="utf-8")
        else:
            (data_dir / name).write_text(f'"{name}"', encoding="utf-8")


def test_first_profile_moves_every_legacy_item(tmp_path: Path) -> None:
    make_legacy(tmp_path)
    profile = tmp_path / "profiles" / "uid1"

    assert adopt_legacy_data(tmp_path, profile, "uid1")

    for name in LEGACY_ITEMS:
        assert not (tmp_path / name).exists()
        assert (profile / name).exists()
    assert (profile / "cache" / "doc.json").is_file()
    marker = json.loads((tmp_path / ADOPTION_MARKER).read_text(encoding="utf-8"))
    assert marker == {"uid": "uid1"}


def test_second_profile_gets_nothing(tmp_path: Path) -> None:
    make_legacy(tmp_path)
    adopt_legacy_data(tmp_path, tmp_path / "profiles" / "uid1", "uid1")
    make_legacy(tmp_path, ("config.json",))
    second = tmp_path / "profiles" / "uid2"

    assert not adopt_legacy_data(tmp_path, second, "uid2")

    assert (tmp_path / "config.json").exists()
    assert not (second / "config.json").exists()


def test_missing_files_are_fine_and_still_claim_the_marker(tmp_path: Path) -> None:
    make_legacy(tmp_path, ("config.json", "glossary.json"))
    profile = tmp_path / "profiles" / "uid1"

    assert adopt_legacy_data(tmp_path, profile, "uid1")

    assert sorted(p.name for p in profile.iterdir()) == ["config.json", "glossary.json"]


def test_clean_install_claims_the_marker_with_nothing_to_move(tmp_path: Path) -> None:
    assert adopt_legacy_data(tmp_path, tmp_path / "profiles" / "uid1", "uid1")

    assert (tmp_path / ADOPTION_MARKER).is_file()


def test_failed_move_leaves_no_marker_so_the_next_sign_in_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_legacy(tmp_path, ("config.json",))

    def refuse(source: str, target: str) -> None:
        raise OSError("locked")

    monkeypatch.setattr("clearread.services.profile_migration.shutil.move", refuse)
    profile = tmp_path / "profiles" / "uid1"

    assert not adopt_legacy_data(tmp_path, profile, "uid1")
    assert not (tmp_path / ADOPTION_MARKER).exists()

    monkeypatch.undo()
    assert adopt_legacy_data(tmp_path, profile, "uid1")
    assert (profile / "config.json").exists()


def test_existing_target_is_never_overwritten(tmp_path: Path) -> None:
    make_legacy(tmp_path, ("config.json",))
    profile = tmp_path / "profiles" / "uid1"
    profile.mkdir(parents=True)
    (profile / "config.json").write_text('"mine"', encoding="utf-8")

    adopt_legacy_data(tmp_path, profile, "uid1")

    assert (profile / "config.json").read_text(encoding="utf-8") == '"mine"'


def test_profile_dir_is_created_under_profiles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    profile = paths.get_profile_dir("AbC123")

    assert profile == tmp_path / "ClearRead" / "profiles" / "AbC123"
    assert profile.is_dir()


@pytest.mark.parametrize("uid", ["", "..", "a/b", "a\\b", "a b", "ñ", "x" * 129, "a.b"])
def test_invalid_uid_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, uid: str
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    with pytest.raises(ValueError):
        paths.get_profile_dir(uid)

    assert not (tmp_path / "ClearRead" / "profiles").exists()


def test_uid_of_128_characters_is_valid() -> None:
    assert paths.is_valid_uid("a" * 128)
