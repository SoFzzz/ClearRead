"""Entry point for `python -m clearread` and the `clearread` script."""

import sys

from PySide6.QtWidgets import QApplication

from clearread.core.config import AppConfig
from clearread.core.paths import get_user_data_dir
from clearread.services.document_library import DocumentLibrary
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_fonts
from clearread.ui.main_window import MainWindow

CACHE_DIR_NAME = "cache"


def main() -> int:
    """Start ClearRead Desktop and return the process exit code."""
    app = QApplication(sys.argv)
    app.setApplicationName("ClearRead")
    load_reading_fonts()
    window = MainWindow(
        config=AppConfig.load(),
        ocr_engine=LazyOCREngine(),
        tts=TTSController(),
        library=DocumentLibrary(get_user_data_dir() / CACHE_DIR_NAME),
    )
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
