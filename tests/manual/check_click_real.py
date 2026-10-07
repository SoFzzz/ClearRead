r"""Real check of click-to-read (UI-F02) with the SAPI5 voice: it speaks aloud.

    .\.venv\Scripts\python tests\manual\check_click_real.py

Clicks (with a real mouse event) a word in the middle of the synthetic text while the
voice is idle and again while it is playing, and prints the index of the clicked word
against the first word event received. Only the synthetic sample text is used.
"""

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.reading_view import PlaybackState, ReadingView

TIMEOUT_S = 30.0


def pump(app: QApplication, condition, timeout_s: float = TIMEOUT_S) -> bool:
    deadline = time.perf_counter() + timeout_s
    while not condition():
        app.processEvents()
        if time.perf_counter() > deadline:
            return False
        time.sleep(0.005)
    return True


def click_word(view: ReadingView, index: int) -> None:
    token = view.token_map[index]
    points = []
    for position in (token.doc_start_pos, token.doc_end_pos):
        cursor = QTextCursor(view.editor.document())
        cursor.setPosition(position)
        rect = view.editor.cursorRect(cursor)
        points.append((rect.x(), rect.center().y()))
    middle = QPoint((points[0][0] + points[1][0]) // 2, points[0][1])
    QTest.mouseClick(view.editor.viewport(), Qt.MouseButton.LeftButton, pos=middle)


def main() -> int:
    app = QApplication(sys.argv)
    load_reading_font()
    tts = TTSController()
    view = ReadingView(tts)
    formatter = TextFormatter(
        SpanishSyllabifier(), syllable_palette(THEMES[ThemeId.LIGHT])
    )
    view.load_document(formatter.format_document(EXPECTED_TEXT))
    view.resize(1000, 600)
    view.show()
    pump(app, lambda: bool(tts.voices))
    total = len(view.token_map)
    events: list[tuple[float, int]] = []
    tts.word_spoken.connect(lambda i: events.append((time.perf_counter(), i)))

    def report(label: str, clicked: int) -> None:
        pump(app, lambda: bool(events))
        first = events[0][1]
        word = view.token_map[first].spoken_text
        print(
            f"{label}: clicked word {clicked}, first event word {first} ('{word}') "
            f"-> {'OK' if first == clicked else 'MISMATCH'}"
        )

    target = total // 2
    print(f"{total} words; clicking the one in the middle")
    click_word(view, target)
    report("A. idle", target)

    pump(app, lambda: events[-1][1] >= target + 3)
    events.clear()
    target_2 = total // 4
    click_word(view, target_2)
    report("B. while playing (jump back)", target_2)
    ordered = [i for _, i in events]
    print(
        f"   events after the second click are consecutive: "
        f"{ordered == list(range(ordered[0], ordered[0] + len(ordered)))}"
    )
    pump(app, lambda: view.state is PlaybackState.IDLE)
    tts.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
