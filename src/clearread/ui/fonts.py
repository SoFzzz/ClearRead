"""Loads the bundled reading fonts (all SIL OFL; origin in resources/fonts/README.md)."""

from PySide6.QtGui import QFontDatabase

from clearread.core.paths import get_resource_path

READING_FONT_FAMILY = "Lexend"  # the default one
# Family name as Qt sees it -> file under resources/fonts.
READING_FONT_FILES: dict[str, str] = {
    "Lexend": "Lexend-Regular.ttf",
    "Atkinson Hyperlegible": "AtkinsonHyperlegible-Regular.ttf",
    "OpenDyslexic": "opendyslexic.otf",
}


def load_reading_font() -> str:
    """Register every reading font with Qt and return the default family name."""
    for file_name in READING_FONT_FILES.values():
        path = get_resource_path(f"resources/fonts/{file_name}")
        if QFontDatabase.addApplicationFont(str(path)) == -1:
            raise FileNotFoundError(path)
    return READING_FONT_FAMILY
