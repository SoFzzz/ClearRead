"""Loads the bundled reading font (OpenDyslexic, SIL OFL; see resources/fonts/README.md)."""

from PySide6.QtGui import QFontDatabase

from clearread.core.paths import get_resource_path

READING_FONT_FAMILY = "OpenDyslexic"
_FONT_FILE = "opendyslexic.otf"


def load_reading_font() -> str:
    """Register the single-weight reading font with Qt and return the family name."""
    path = get_resource_path(f"resources/fonts/{_FONT_FILE}")
    if QFontDatabase.addApplicationFont(str(path)) == -1:
        raise FileNotFoundError(path)
    return READING_FONT_FAMILY
