"""App icon: the bundled .ico loads with every size and the taskbar id is set."""

import sys

import pytest
from PySide6.QtWidgets import QApplication

from clearread.ui.app_icon import APP_USER_MODEL_ID, load_app_icon, set_windows_app_id

ICON_SIZES = {16, 24, 32, 48, 64, 128, 256}


def test_icon_has_every_size(qtbot: object) -> None:
    icon = load_app_icon()

    assert not icon.isNull()
    assert ICON_SIZES <= {size.width() for size in icon.availableSizes()}


def test_icon_is_used_by_the_application(qtbot: object) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    app.setWindowIcon(load_app_icon())

    assert not app.windowIcon().isNull()


@pytest.mark.skipif(sys.platform != "win32", reason="AppUserModelID is Windows-only")
def test_windows_app_id_is_accepted() -> None:
    assert set_windows_app_id(APP_USER_MODEL_ID)
