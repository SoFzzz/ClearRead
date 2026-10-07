"""Entry point for `python -m clearread` and the `clearread` script."""

import sys

from PySide6.QtWidgets import QApplication

from clearread.core.config import AppConfig, load_client_token
from clearread.core.paths import get_user_data_dir
from clearread.services.ai_client import BackendAIClient, DiskResponseCache
from clearread.services.document_library import DocumentLibrary
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow

CACHE_DIR_NAME = "cache"
AI_CACHE_FILE = "ai_cache.json"


def main() -> int:
    """Start ClearRead Desktop and return the process exit code."""
    app = QApplication(sys.argv)
    app.setApplicationName("ClearRead")
    load_reading_font()
    config = AppConfig.load()
    ai_client = BackendAIClient(
        config.backend_url,
        load_client_token(),
        DiskResponseCache(get_user_data_dir() / AI_CACHE_FILE),
        config.ui_language,
    )
    window = MainWindow(
        config=config,
        ocr_engine=LazyOCREngine(),
        tts=TTSController(),
        library=DocumentLibrary(get_user_data_dir() / CACHE_DIR_NAME),
        ai_client=ai_client,
        network=NetworkMonitor.from_system(),
    )
    window.resize(1280, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
