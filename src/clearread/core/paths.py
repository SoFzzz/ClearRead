"""Filesystem locations that behave the same from source and from the frozen .exe."""

import os
import sys
from pathlib import Path

APP_DIR_NAME = "ClearRead"
_SOURCE_ROOT = Path(__file__).resolve().parents[3]


def get_resource_path(relative: str | Path) -> Path:
    """Resolve a bundled resource (e.g. ``resources/models/x.onnx``).

    PyInstaller unpacks data files under ``sys._MEIPASS``; from source they
    live at the repository root.
    """
    bundle_root = getattr(sys, "_MEIPASS", None)
    base = Path(bundle_root) if bundle_root else _SOURCE_ROOT
    return base / relative


def get_user_data_dir() -> Path:
    """Return the ClearRead folder inside %APPDATA%, creating it if needed."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    data_dir = base / APP_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
