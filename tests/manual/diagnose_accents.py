r"""Diagnostic for the displaced accent on "ó"/"é" (Day 6, part A).

Run from the repo root:

    .\.venv\Scripts\python tests\manual\diagnose_accents.py OUT_DIR

Prints the code points Qt keeps for "leyó" and renders "ó é á í ú ñ" with
OpenDyslexic and Segoe UI at letter-spacing 0 and 1.5 px.
"""

import sys
import unicodedata
from pathlib import Path

from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import SyllablePalette, TextFormatter
from clearread.ui.fonts import load_reading_fonts

SAMPLE = "ó é á í ú ñ  leyó explicó comió construcción Qué Dónde"


def codepoints(text: str) -> str:
    return " ".join(f"U+{ord(ch):04X}" for ch in text)


def report_normalisation() -> None:
    formatter = TextFormatter(SpanishSyllabifier(), SyllablePalette("#000", "#111"))
    document = formatter.format_document(EXPECTED_TEXT)
    qt_doc = QTextDocument()
    qt_doc.setHtml(document.html_content)
    plain = qt_doc.toPlainText()
    token = next(t for t in document.token_map if "ó" in t.spoken_text or "ó" in plain)
    print("source NFC?", unicodedata.is_normalized("NFC", EXPECTED_TEXT))
    print("plain NFC?", unicodedata.is_normalized("NFC", plain))
    word = next((t for t in document.token_map if t.spoken_text.endswith("ó")), token)
    print(word.spoken_text, codepoints(plain[word.doc_start_pos : word.doc_end_pos]))
    nfd = unicodedata.normalize("NFD", "leyó")
    qt_doc.setHtml(f"<p>{nfd}</p>")
    print("NFD in ->", codepoints(qt_doc.toPlainText()))


def render(out_dir: Path) -> None:
    rows = [
        ("OpenDyslexic", "OpenDyslexic", 0.0),
        ("OpenDyslexic", "OpenDyslexic", 1.5),
        ("Segoe UI", "Segoe UI", 0.0),
        ("Segoe UI", "Segoe UI", 1.5),
    ]
    widget = QWidget()
    layout = QVBoxLayout(widget)
    for name, family, spacing in rows:
        label = QLabel(f"{name} spacing={spacing}: {SAMPLE}")
        font = QFont(family, 24)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        label.setFont(font)
        layout.addWidget(label)
    widget.resize(1500, 400)
    widget.show()
    QApplication.processEvents()
    widget.grab().save(str(out_dir / "acentos_diagnostico.png"))


def main() -> None:
    app = QApplication(sys.argv)
    load_reading_fonts()
    report_normalisation()
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    render(out_dir)
    del app


if __name__ == "__main__":
    main()
