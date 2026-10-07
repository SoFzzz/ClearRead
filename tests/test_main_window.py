"""MainWindow flow: Home -> Processing -> Reading, cancel, errors, recents, close."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest
from fakes import EngineSource
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot
from samples.make_samples import EXPECTED_TEXT, SAMPLES_DIR

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.ocr_engine import LazyOCREngine, OCRResult
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_fonts
from clearread.ui.main_window import MainWindow, Screen
from clearread.workers.ocr_worker import ProcessingErrorKind

DIGITAL = SAMPLES_DIR / "sample_page_digital.pdf"
SCANNED = SAMPLES_DIR / "sample_page_scanned.pdf"
PASSWORD = SAMPLES_DIR / "sample_page_password.pdf"
TIMEOUT_MS = 60000


class FakeOCR:
    """OCR double: counts calls and can block until the test lets it go."""

    def __init__(self, text: str = EXPECTED_TEXT, gated: bool = False) -> None:
        self.text = text
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        if not gated:
            self.release.set()

    def process_image(self, image: np.ndarray, page_number: int = 1) -> OCRResult:
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=30)
        return OCRResult(page_number, self.text)


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(tmp_path / "cache")


def make_window(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, ocr: object
) -> MainWindow:
    load_reading_fonts()
    window = MainWindow(AppConfig(), ocr, tts, library)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show()
    return window


def wait_for_screen(qtbot: QtBot, window: MainWindow, screen: Screen) -> None:
    qtbot.waitUntil(lambda: window.screen_shown is screen, timeout=TIMEOUT_MS)


def wait_for_idle(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: not window._retired_workers, timeout=TIMEOUT_MS)


def wait_for_dialog(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: window.error_dialog is not None, timeout=TIMEOUT_MS)


def multi_page_scan(tmp_path: Path, pages: int) -> Path:
    document = pdfium.PdfDocument.new()
    source = pdfium.PdfDocument(str(SCANNED))
    for _ in range(pages):
        document.import_pages(source)
    path = tmp_path / "multi.pdf"
    document.save(str(path))
    return path


def test_digital_sample_reaches_the_reading_view_without_ocr(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    ocr = FakeOCR()
    window = make_window(qtbot, tts, library, ocr)
    window.open_document(str(DIGITAL))
    wait_for_screen(qtbot, window, Screen.READING)
    assert ocr.calls == 0
    assert window.reading_view.token_map
    assert window.title_label.text() == DIGITAL.name
    assert [r.name for r in library.recents()] == [DIGITAL.name]


def test_scanned_sample_goes_through_the_real_ocr_engine(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    window = make_window(qtbot, tts, library, LazyOCREngine())
    window.open_document(str(SCANNED))
    wait_for_screen(qtbot, window, Screen.READING)
    spoken = " ".join(t.spoken_text for t in window.reading_view.token_map)
    assert "niño" in spoken.lower() or "nino" in spoken.lower()


def test_ocr_engine_is_built_once_and_reused(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    built: list[FakeOCR] = []

    def factory() -> FakeOCR:
        built.append(FakeOCR())
        return built[-1]

    window = make_window(qtbot, tts, library, LazyOCREngine(factory))
    window.open_document(str(SCANNED))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    window.go_back()
    window.open_document(str(multi_page_scan(tmp_path, 2)))
    wait_for_screen(qtbot, window, Screen.READING)
    assert len(built) == 1
    assert built[0].calls == 3


def test_cancel_in_the_middle_returns_home_and_stops_the_thread(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    ocr = FakeOCR(gated=True)
    window = make_window(qtbot, tts, library, ocr)
    window.open_document(str(multi_page_scan(tmp_path, 4)))
    qtbot.waitUntil(ocr.started.is_set, timeout=TIMEOUT_MS)
    worker = window.worker
    assert worker is not None
    assert window.screen_shown is Screen.PROCESSING

    qtbot.mouseClick(window.processing_view.cancel_button, Qt.MouseButton.LeftButton)
    assert window.screen_shown is Screen.HOME
    ocr.release.set()
    assert worker.wait(TIMEOUT_MS)
    wait_for_idle(qtbot, window)

    assert ocr.calls == 1
    assert library.recents() == []
    assert window.error_dialog is None


def test_password_pdf_shows_the_password_dialog(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(PASSWORD))
    wait_for_dialog(qtbot, window)
    assert window.screen_shown is Screen.HOME
    assert window.error_dialog is not None
    assert window.error_dialog.kind is ProcessingErrorKind.PASSWORD
    assert window.error_dialog.windowTitle() == "ClearRead"


def test_unsupported_format_shows_its_dialog(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hola", encoding="utf-8")
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(text_file))
    wait_for_dialog(qtbot, window)
    assert window.error_dialog is not None
    assert window.error_dialog.kind is ProcessingErrorKind.UNSUPPORTED_FORMAT


def test_missing_file_shows_its_dialog(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(tmp_path / "gone.pdf"))
    wait_for_dialog(qtbot, window)
    assert window.error_dialog is not None
    assert window.error_dialog.kind is ProcessingErrorKind.FILE_NOT_FOUND


def test_document_without_recognised_text_shows_its_dialog(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    window = make_window(qtbot, tts, library, FakeOCR(text=""))
    window.open_document(str(SCANNED))
    wait_for_dialog(qtbot, window)
    assert window.error_dialog is not None
    assert window.error_dialog.kind is ProcessingErrorKind.NO_TEXT
    assert library.recents() == []


def test_recent_opens_from_cache_without_calling_ocr(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    ocr = FakeOCR()
    window = make_window(qtbot, tts, library, ocr)
    copy = tmp_path / "copy.pdf"
    copy.write_bytes(SCANNED.read_bytes())
    window.open_document(str(copy))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    assert ocr.calls == 1
    window.go_back()
    assert [item.name for item in window.home_view.recent_items] == ["copy.pdf"]

    copy.unlink()  # the original is gone: the cache still lets the person read it
    started = time.perf_counter()
    window.open_recent(library.recents()[0].key)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert window.screen_shown is Screen.READING
    assert ocr.calls == 1
    assert window.reading_view.token_map
    assert elapsed_ms < 500, f"{elapsed_ms:.0f} ms"


def test_reopening_the_same_file_uses_the_cache(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    ocr = FakeOCR()
    window = make_window(qtbot, tts, library, ocr)
    window.open_document(str(SCANNED))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    window.go_back()
    window.open_document(str(SCANNED))
    assert window.screen_shown is Screen.READING
    assert ocr.calls == 1


def test_remove_recent_deletes_the_entry_and_its_cache(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary
) -> None:
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(DIGITAL))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    window.go_back()
    key = library.recents()[0].key
    window.remove_recent(key)
    assert window.home_view.recent_items == []
    assert not library.has(key)


def test_closing_while_processing_leaves_no_live_thread(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    ocr = FakeOCR(gated=True)
    window = make_window(qtbot, tts, library, ocr)
    window.open_document(str(multi_page_scan(tmp_path, 4)))
    qtbot.waitUntil(ocr.started.is_set, timeout=TIMEOUT_MS)
    worker = window.worker
    assert worker is not None
    threading.Timer(0.3, ocr.release.set).start()

    window.close()

    assert worker.isFinished()
    assert ocr.calls == 1
    assert all(w.isFinished() for w in window._retired_workers)
