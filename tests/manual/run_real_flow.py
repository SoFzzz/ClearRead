"""Real end-to-end run of the main window (Day 6): real OCR, real SAPI5 voice, real cache.

Run from the repo root:

    .\\.venv\\Scripts\\python tests\\manual\\run_real_flow.py captures DIR   # synthetic samples only
    .\\.venv\\Scripts\\python tests\\manual\\run_real_flow.py timings        # private card + scanned sample

``captures`` saves the three Home screens (empty, with recents, processing).
``timings`` prints times measured with ``time.perf_counter()``; it never prints
text from the private card, only its file name and counts.
"""

import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import SAMPLES_DIR

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.ocr_engine import LazyOCREngine, OCRResult
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_fonts
from clearread.ui.main_window import MainWindow, Screen

WAIT_STEP_S = 0.01
TIMEOUT_S = 120.0
READ_SECONDS = 5.0
WINDOW_SIZE = (1280, 800)


class CountingOCR:
    """Wraps the shared OCR engine to report how many pages went through OCR."""

    def __init__(self) -> None:
        self.engine = LazyOCREngine()
        self.pages = 0

    def process_image(self, image: object, page_number: int = 1) -> OCRResult:
        self.pages += 1
        return self.engine.process_image(image, page_number)  # type: ignore[arg-type]


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(WAIT_STEP_S)


def wait_until(app: QApplication, condition: object) -> None:
    end = time.perf_counter() + TIMEOUT_S
    while not condition():  # type: ignore[operator]
        if time.perf_counter() > end:
            raise TimeoutError
        app.processEvents()
        time.sleep(WAIT_STEP_S)


def build(app: QApplication, cache: Path) -> tuple[MainWindow, CountingOCR]:
    load_reading_fonts()
    ocr = CountingOCR()
    window = MainWindow(AppConfig(), ocr, TTSController(), DocumentLibrary(cache))
    window.resize(*WINDOW_SIZE)
    window.show()
    app.processEvents()
    return window, ocr


def timed_open(app: QApplication, window: MainWindow, path: Path) -> float:
    started = time.perf_counter()
    window.open_document(str(path))
    wait_until(app, lambda: window.screen_shown is Screen.READING)
    return (time.perf_counter() - started) * 1000


def capture(app: QApplication, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as cache:
        window, _ = build(app, Path(cache))
        window.grab().save(str(out_dir / "inicio_real_vacio.png"))
        for sample in ("sample_page_digital.pdf", "sample_page_scanned.pdf"):
            window.open_document(str(SAMPLES_DIR / sample))
            if sample.endswith("scanned.pdf"):
                wait_until(
                    app, lambda: bool(window.processing_view.status_label.text())
                )
                app.processEvents()
                window.grab().save(str(out_dir / "procesando_real.png"))
            wait_until(app, lambda: window.screen_shown is Screen.READING)
            window.go_back()
            wait_until(app, lambda: not window._retired_workers)
        app.processEvents()
        window.grab().save(str(out_dir / "inicio_real_recientes.png"))
        window.close()


def timings(app: QApplication) -> None:
    private = sorted((SAMPLES_DIR / "private").glob("*.pdf"))
    if not private:
        raise SystemExit("No hay PDF en tests/samples/private/")
    ficha = private[0]
    with tempfile.TemporaryDirectory() as cache:
        window, ocr = build(app, Path(cache))
        ms = timed_open(app, window, ficha)
        words = len(window.reading_view.token_map)
        print(
            f"ficha privada {ficha.name}: {ms:.0f} ms, OCR en {ocr.pages} paginas, {words} palabras"
        )
        window.go_back()
        wait_until(app, lambda: not window._retired_workers)

        before = ocr.pages
        ms = timed_open(app, window, SAMPLES_DIR / "sample_page_scanned.pdf")
        print(
            f"muestra escaneada (1.a vez, incluye cargar modelos): {ms:.0f} ms, OCR en {ocr.pages - before} paginas"
        )
        spoken: list[int] = []
        window.reading_view._tts.word_spoken.connect(spoken.append)
        window.reading_view.toggle_play()
        pump(app, READ_SECONDS)
        window.reading_view.stop_reading()
        print(
            f"voz real SAPI5: {len(spoken)} palabras resaltadas en {READ_SECONDS:.0f} s"
        )
        window.go_back()
        wait_until(app, lambda: not window._retired_workers)

        recents = window.home_view.recent_items
        print("recientes:", [r.name for r in recents])
        for entry in recents:
            started = time.perf_counter()
            window.open_recent(entry.key)
            elapsed = (time.perf_counter() - started) * 1000
            print(
                f"reabrir {entry.name} desde cache: {elapsed:.1f} ms, OCR sigue en {ocr.pages} paginas"
            )
            window.go_back()
        window.close()


def main() -> int:
    app = QApplication(sys.argv)
    if sys.argv[1] == "captures":
        capture(app, Path(sys.argv[2]))
    else:
        timings(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
