"""Filesystem locations that behave the same from source and from the frozen .exe."""

import os
import re
import sys
from pathlib import Path

APP_DIR_NAME = "ClearRead"
PROFILES_DIR_NAME = "profiles"
# Firebase uids; anything else could escape the profiles folder.
_UID_PATTERN = re.compile(r"[A-Za-z0-9]{1,128}")
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


def is_valid_uid(uid: str) -> bool:
    return _UID_PATTERN.fullmatch(uid) is not None


def get_profile_dir(uid: str) -> Path:
    """Return the folder of one account's local data, creating it if needed."""
    if not is_valid_uid(uid):
        raise ValueError("invalid uid")
    profile_dir = get_user_data_dir() / PROFILES_DIR_NAME / uid
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir
