"""Application icon and the Windows taskbar identity."""

import ctypes
import sys

from PySide6.QtGui import QIcon

from clearread.core.paths import get_resource_path

APP_USER_MODEL_ID = "UCC.ClearRead.1"
APP_ICON_FILE = "resources/icons/app.ico"


def load_app_icon() -> QIcon:
    return QIcon(str(get_resource_path(APP_ICON_FILE)))


def set_windows_app_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """Give the process its own taskbar identity, so Windows shows our icon.

    Without it the taskbar groups the window under python.exe and shows its icon.
    Must run before the first window is created. Returns False off Windows.
    """
    if sys.platform != "win32":
        return False
    result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    return result == 0
