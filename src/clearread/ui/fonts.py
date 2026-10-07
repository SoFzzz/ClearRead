"""Loads the bundled reading font (OpenDyslexic, SIL OFL; see resources/fonts/README.md)."""

from PySide6.QtGui import QFontDatabase

from clearread.core.paths import get_resource_path

READING_FONT_FAMILY = "OpenDyslexic"
_FONT_FILES = ("OpenDyslexic-Regular.otf", "OpenDyslexic-Bold.otf")


def load_reading_fonts() -> str:
    """Register Regular and Bold with Qt and return the family name."""
    for file_name in _FONT_FILES:
        path = get_resource_path(f"resources/fonts/{file_name}")
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            raise FileNotFoundError(path)
    return READING_FONT_FAMILY
