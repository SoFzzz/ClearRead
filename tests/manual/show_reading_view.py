"""Manual check of the reading view with the real OpenDyslexic font.

Run from the repo root:

    .\\.venv\\Scripts\\python tests\\manual\\show_reading_view.py                  # interactive, synthetic text
    .\\.venv\\Scripts\\python tests\\manual\\show_reading_view.py --theme dark
    .\\.venv\\Scripts\\python tests\\manual\\show_reading_view.py --ficha          # first page of a private card
    .\\.venv\\Scripts\\python tests\\manual\\show_reading_view.py --capture DIR    # PNG of the three themes, then exit

Captures use the synthetic text only, because they are committed to the repository.
Space plays/pauses with the real SAPI5 voice, Esc stops.
"""

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT, SAMPLES_DIR

from clearread.services.ingestor import DocumentIngestor
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FormattedDocument,
    TextFormatter,
)
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.theme import (
    THEMES,
    ThemeId,
    build_stylesheet,
    syllable_palette,
)
from clearread.ui.views.reading_view import PlaybackState, ReadingView

WINDOW_SIZE = (1280, 720)
HIGHLIGHT_WORD_INDEX = 9
SYNTHETIC_EXTRA = (
    "El maestro explicó la lección de geografía con un mapa grande. "
    "Los estudiantes escribieron en sus cuadernos las palabras difíciles: "
    "ahumado, desahucio, averiguáis, subrayar y construcción."
)


def synthetic_text() -> str:
    return f"{EXPECTED_TEXT}\n\n{SYNTHETIC_EXTRA}"


def ficha_text() -> str:
    pdfs = sorted((SAMPLES_DIR / "private").glob("*.pdf"))
    if not pdfs:
        raise SystemExit("No hay PDF en tests/samples/private/")
    page = next(iter(DocumentIngestor(dpi=72).load(pdfs[0])))
    return page.digital_text or ""


def format_for(theme: ThemeId, text: str) -> FormattedDocument:
    formatter = TextFormatter(SpanishSyllabifier(), syllable_palette(THEMES[theme]))
    return formatter.format_document(text)


def build_view(app: QApplication, theme: ThemeId, text: str) -> ReadingView:
    load_reading_font()
    app.setStyleSheet(build_stylesheet(THEMES[theme]))
    view = ReadingView(TTSController(), theme)
    view.resize(*WINDOW_SIZE)
    view.load_document(format_for(theme, text))
    return view


def capture(app: QApplication, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    text = synthetic_text()
    for theme in ThemeId:
        view = build_view(app, theme, text)
        view.show()
        app.processEvents()
        view._set_state(PlaybackState.PLAYING)  # bar shows "Pause"; no audio is started
        view._on_word_spoken(HIGHLIGHT_WORD_INDEX)
        app.processEvents()
        path = out_dir / f"lectura_real_{theme.value}.png"
        view.grab().save(str(path))
        print(f"saved {path}")
        view._tts.shutdown()
        view.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", choices=[t.value for t in ThemeId], default="light")
    parser.add_argument("--ficha", action="store_true")
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()

    app = QApplication(sys.argv)
    if args.capture:
        capture(app, args.capture)
        return 0
    text = ficha_text() if args.ficha else synthetic_text()
    view = build_view(app, ThemeId(args.theme), text)
    view.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
