"""Real captures of the page features: continuous and page mode, Light and Dark.

Run from the repo root (add QT_QPA_PLATFORM=offscreen to keep the desktop untouched):

    .\\.venv\\Scripts\\python tests\\manual\\run_real_v3.py DIR

Builds the real MainWindow (real fonts, theme, ingestion and token map; no OCR is needed
because the sample is a digital PDF) around a 4-page PDF made from the public
tests/samples/sample_page_digital.pdf, and saves for each theme: the continuous view, the
continuous view with a word of page 2 highlighted, and the page view on page 2. It also
sends real key presses (PageDown, Ctrl+Right, Ctrl++) and prints whether they worked.
Nothing here uses tests/samples/private.
"""

import sys
import tempfile
import time
from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.views.reading_view import PlaybackState, ViewMode

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "samples" / "sample_page_digital.pdf"
WINDOW_SIZE = (1280, 800)
PAGES = 4
TIMEOUT_S = 60.0
FONT_SIZE_PT = 24  # larger than the default so the four short pages need scrolling


def pump(app: QApplication, seconds: float = 0.2) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def make_pdf(folder: Path) -> Path:
    document = pdfium.PdfDocument.new()
    source = pdfium.PdfDocument(str(SAMPLE))
    for _ in range(PAGES):
        document.import_pages(source)
    path = folder / "four_pages.pdf"
    document.save(str(path))
    return path


def open_pdf(app: QApplication, window: MainWindow, path: Path) -> None:
    window.open_document(str(path))
    deadline = time.perf_counter() + TIMEOUT_S
    while window.screen_shown is not Screen.READING:
        if time.perf_counter() > deadline:
            raise SystemExit("the document did not open")
        app.processEvents()
        time.sleep(0.01)
    while window._retired_workers:
        app.processEvents()
    pump(app)


def save(app: QApplication, window: MainWindow, out_dir: Path, name: str) -> None:
    pump(app)
    path = out_dir / name
    window.grab().save(str(path))
    print(f"saved {path}")


def check_real_keys(app: QApplication, window: MainWindow) -> None:
    view = window.reading_view
    window.activateWindow()
    view.editor.setFocus()
    pump(app)
    print(f"window active: {window.isActiveWindow()}")
    bar = view.editor.verticalScrollBar()
    QTest.keyClick(view.editor, Qt.Key.Key_PageDown)
    print(f"PageDown moved the scroll: {bar.value() > 0} (value {bar.value()})")
    QTest.keyClick(view.editor, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    print(f"Ctrl+Right went to page {view.current_page + 1}")
    before = window._config.font_size_pt
    QTest.keyClick(view.editor, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    print(f"Ctrl++ size {before} -> {window._config.font_size_pt}")
    print(f"voice state after all of it: {view.state.value}")


def capture_theme(app: QApplication, theme: str, out_dir: Path, pdf: Path) -> None:
    work = Path(tempfile.mkdtemp())
    config = AppConfig(theme=theme, font_size_pt=FONT_SIZE_PT)
    window = MainWindow(
        config,
        LazyOCREngine(),
        TTSController(),
        DocumentLibrary(work / "cache"),
        config_dir=work / "config",
    )
    window.resize(*WINDOW_SIZE)
    window.show()
    open_pdf(app, window, pdf)
    view = window.reading_view
    print(f"{theme}: pages={view.page_count} words={len(view.token_map)}")
    save(app, window, out_dir, f"paginas_continua_{theme}.png")

    view.go_to_page(1)
    view._move_start_to(
        next(
            i
            for i, t in enumerate(view.token_map)
            if t.doc_start_pos >= view.page_starts[1]
        )
        + 6
    )
    save(app, window, out_dir, f"paginas_continua_pagina2_{theme}.png")

    view.paged_button.click()
    assert view.view_mode is ViewMode.PAGED and view.state is PlaybackState.PAUSED
    save(app, window, out_dir, f"paginas_por_paginas_{theme}.png")

    view.continuous_button.click()
    check_real_keys(app, window)
    window.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    load_reading_font()
    pdf = make_pdf(Path(tempfile.mkdtemp()))
    for theme in ("light", "dark"):
        capture_theme(app, theme, out_dir, pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
