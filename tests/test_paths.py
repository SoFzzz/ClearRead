import sys
from pathlib import Path

import pytest

from clearread.core import paths


def test_resource_path_from_source_points_into_repo() -> None:
    model = paths.get_resource_path("resources/models/latin_PP-OCRv5_rec_mobile.onnx")
    assert model.is_file()


def test_resource_path_uses_pyinstaller_bundle_when_frozen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.get_resource_path("resources/fonts") == tmp_path / "resources/fonts"


def test_user_data_dir_is_clearread_under_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data_dir = paths.get_user_data_dir()
    assert data_dir == tmp_path / "ClearRead"
    assert data_dir.is_dir()


def test_user_data_dir_falls_back_to_home_without_appdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert paths.get_user_data_dir() == tmp_path / "AppData" / "Roaming" / "ClearRead"
