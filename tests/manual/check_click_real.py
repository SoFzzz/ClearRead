r"""Real check of click-to-position (UI-F02) with the SAPI5 voice: it speaks aloud on Play.

    .\.venv\Scripts\python tests\manual\check_click_real.py

Clicks (with a real mouse event) a word of the synthetic text: a click must stay silent,
Play must start at the clicked word, a click while playing must stop the voice, and
Pause must stop it at once. Only the synthetic sample text is used.
"""

import sys
import time
from collections.abc import Callable
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


def pump(
    app: QApplication, condition: Callable[[], bool], timeout_s: float = TIMEOUT_S
) -> bool:
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

    target = total // 2
    print(f"{total} words; clicking the one in the middle while idle")
    click_word(view, target)
    pump(app, lambda: bool(events), timeout_s=2.0)
    print(
        f"A. click idle: state={view.state.name}, word events={len(events)} "
        f"-> {'OK (silent)' if not events and view.state is PlaybackState.PAUSED else 'FAIL'}"
    )

    view.toggle_play()
    pump(app, lambda: bool(events))
    print(
        f"B. Play: first event word {events[0][1]} -> {'OK' if events[0][1] == target else 'MISMATCH'}"
    )

    pump(app, lambda: events[-1][1] >= target + 3)
    click_word(view, total // 4)
    seen = len(events)
    pump(app, lambda: False, timeout_s=1.5)
    print(
        f"C. click while playing: state={view.state.name}, new events after click="
        f"{len(events) - seen} (a few already in flight are dropped) "
        f"-> {'OK' if view.state is PlaybackState.PAUSED and len(events) == seen else 'FAIL'}"
    )

    view.toggle_play()
    pump(app, lambda: events[-1][1] > total // 4)
    view.toggle_play()
    seen = len(events)
    pump(app, lambda: False, timeout_s=1.5)
    print(
        f"D. pause: state={view.state.name}, events after pause={len(events) - seen} "
        f"-> {'OK' if view.state is PlaybackState.PAUSED and len(events) == seen else 'FAIL'}"
    )
    view.stop_reading()
    tts.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
