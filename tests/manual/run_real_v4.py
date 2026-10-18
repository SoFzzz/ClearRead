"""Real captures of the library (folders) and My words (topics), Light and Dark.

Run from the repo root (add QT_QPA_PLATFORM=offscreen to keep the desktop untouched):

    .\\.venv\\Scripts\\python tests\\manual\\run_real_v4.py DIR

Builds the real MainWindow with a temporary user data folder, adds six PDFs made from the
public tests/samples/sample_page_digital.pdf through the real opening flow, groups them in
three folders, adds glossary words in three topics, and saves for each theme the library
(all documents, then one folder) and My words (all, then one topic). Nothing here uses
tests/samples/private or the real %APPDATA% folder.
"""

import sys
import tempfile
import time
from pathlib import Path

import pypdfium2 as pdfium
from PySide6.QtWidgets import QApplication

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.services.groups import GroupStore
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "tests" / "samples" / "sample_page_digital.pdf"
WINDOW_SIZE = (1280, 800)
TIMEOUT_S = 60.0
DOCUMENTS = (
    ("Algebra lineal.pdf", 1, "Matemáticas"),
    ("Geometria del plano.pdf", 2, "Matemáticas"),
    (
        "Informe-de-biologia-celular-y-molecular-primer-parcial-2026-version-final.pdf",
        3,
        "Ciencias",
    ),
    ("Fotosintesis.pdf", 4, "Ciencias"),
    ("Revolucion industrial.pdf", 5, "Historia"),
    ("Apuntes sueltos.pdf", 6, ""),
)
WORDS = (
    ("célula", "La parte más pequeña de un ser vivo.", "Ciencias"),
    (
        "clorofila",
        "El pigmento verde que ayuda a las plantas a fabricar su comida.",
        "Ciencias",
    ),
    ("fracción", "Un número que representa una parte de un entero.", "Matemáticas"),
    ("ecuación", "Una igualdad con un valor que hay que descubrir.", "Matemáticas"),
    ("burguesía", "Grupo social de personas con comercios y fábricas.", "Historia"),
    ("sinónimo", "Una palabra que significa casi lo mismo que otra.", ""),
)


def pump(app: QApplication, seconds: float = 0.2) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def make_pdf(folder: Path, name: str, pages: int) -> Path:
    document = pdfium.PdfDocument.new()
    source = pdfium.PdfDocument(str(SAMPLE))
    for _ in range(pages):
        document.import_pages(source)
    path = folder / name
    document.save(str(path))
    return path


def open_and_leave(app: QApplication, window: MainWindow, path: Path) -> None:
    window.open_document(str(path))
    deadline = time.perf_counter() + TIMEOUT_S
    while window.screen_shown is not Screen.READING:
        if time.perf_counter() > deadline:
            raise SystemExit(f"{path.name} did not open")
        app.processEvents()
        time.sleep(0.01)
    while window._retired_workers:
        app.processEvents()
    window.go_back()
    pump(app, 0.1)


def scroll_home_to_library(window: MainWindow) -> None:
    bar = window.home_view.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())


def save(app: QApplication, window: MainWindow, out_dir: Path, name: str) -> None:
    pump(app)
    path = out_dir / name
    window.grab().save(str(path))
    print(f"saved {path}")


def fill_library(app: QApplication, window: MainWindow, work: Path) -> None:
    folders = window._folders
    ids = {
        name: folders.create(name).id
        for name in ("Matemáticas", "Ciencias", "Historia")
    }
    ids[""] = ""
    for name, pages, folder in DOCUMENTS:
        open_and_leave(app, window, make_pdf(work, name, pages))
        window.move_document(window._library.recents()[0].key, ids[folder])
    window.open_sample()
    window.go_back()
    window._library.set_position(window._library.recents()[2].key, 40)


def fill_words(window: MainWindow) -> None:
    for name in ("Matemáticas", "Ciencias", "Historia"):
        window._topics.create(name)
    for word, explanation, topic in WORDS:
        found = window._topics.find_by_name(topic) if topic else None
        window._glossary.add(
            GlossaryEntry(
                word, explanation, "Apuntes", "2026-10-12", found.id if found else ""
            )
        )


def capture_theme(app: QApplication, theme: str, out_dir: Path) -> None:
    work = Path(tempfile.mkdtemp())
    window = MainWindow(
        AppConfig(theme=theme),
        LazyOCREngine(),
        TTSController(),
        DocumentLibrary(work / "cache"),
        config_dir=work / "config",
        glossary=GlossaryStore(work / "glossary.json"),
        folders=GroupStore(work / "folders.json"),
        topics=GroupStore(work / "topics.json"),
    )
    window.resize(*WINDOW_SIZE)
    window.show()
    fill_library(app, window, work)
    fill_words(window)
    window.show_screen(Screen.HOME)
    pump(app)
    scroll_home_to_library(window)
    save(app, window, out_dir, f"biblioteca_todos_{theme}.png")
    science = window._folders.find_by_name("Ciencias")
    assert science is not None
    window.home_view.folder_filter.chips[science.id].click()
    pump(app)
    scroll_home_to_library(window)
    save(app, window, out_dir, f"biblioteca_carpeta_{theme}.png")
    window.resize(1024, 700)
    pump(app)
    scroll_home_to_library(window)
    save(app, window, out_dir, f"biblioteca_carpeta_1024_{theme}.png")
    window.resize(*WINDOW_SIZE)

    window.open_words()
    save(app, window, out_dir, f"mis_palabras_temas_{theme}.png")
    topic = window._topics.find_by_name("Matemáticas")
    assert topic is not None
    window.words_view.topic_filter.chips[topic.id].click()
    save(app, window, out_dir, f"mis_palabras_tema_{theme}.png")
    window.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    load_reading_font()
    for theme in ("light", "dark"):
        capture_theme(app, theme, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
