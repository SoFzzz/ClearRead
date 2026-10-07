r"""Longest rendered line, in characters, of the reading column (design system 0, P3).

Run from the repo root:

    .\.venv\Scripts\python tests\manual\measure_line_width.py

Renders the synthetic sample at several font sizes and window widths and prints the
longest line of each case, measured with QTextLayout on the real reading font.
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import ReadingStyle, TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.reading_view import ReadingView

TEXT = " ".join([EXPECTED_TEXT] * 6)
WINDOW_WIDTHS = (1024, 1280, 1920)
FONT_SIZES_PT = (12, 16, 20, 28)


def longest_line(view: ReadingView) -> int:
    longest = 0
    plain = view.editor.toPlainText()
    block = view.editor.document().begin()
    while block.isValid():
        layout = block.layout()
        for index in range(layout.lineCount()):
            line = layout.lineAt(index)
            start = block.position() + line.textStart()
            longest = max(
                longest, len(plain[start : start + line.textLength()].rstrip())
            )
        block = block.next()
    return longest


def main() -> None:
    app = QApplication(sys.argv)
    load_reading_font()
    tts = TTSController()
    for size in FONT_SIZES_PT:
        style = ReadingStyle(font_size_pt=size)
        formatter = TextFormatter(
            SpanishSyllabifier(), syllable_palette(THEMES[ThemeId.LIGHT]), style
        )
        for width in WINDOW_WIDTHS:
            view = ReadingView(tts)
            view.resize(width, 800)
            view.load_document(formatter.format_document(TEXT))
            view.apply_appearance(
                ThemeId.LIGHT, style, 1.8, formatter.format_document(TEXT).html_content
            )
            view.show()
            app.processEvents()
            print(
                f"{size} pt, window {width} px: editor {view.editor.width()} px, "
                f"longest line {longest_line(view)} characters"
            )
            view.close()
    tts.shutdown()


if __name__ == "__main__":
    main()
