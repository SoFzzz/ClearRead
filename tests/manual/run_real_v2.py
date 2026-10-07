"""Real captures of the redesigned app (Day 12), with the bundled example document only.

Run from the repo root:

    .\\.venv\\Scripts\\python tests\\manual\\run_real_v2.py DIR

Builds the real MainWindow (real fonts, real theme, real SAPI5 controller) in Light and
Dark at 1280 x 800 and saves: home empty (and with the keyboard focus ring), home with data, reading (normal and focus
mode, with syllables), AI panel with a real answer, My words and Settings.

The assistant answers come from the deployed backend with three words of the example
text (the token is read like in run_real_ai_panel.py and never printed). The numbers in
the statistics cards of "home with data" are illustrative values written by this script,
not something measured; the position of the "continue reading" card comes from the
reading position the script sets in the open example.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QApplication

from clearread.core.config import DEFAULT_BACKEND_URL, AppConfig
from clearread.services.ai_client import BackendAIClient, DiskResponseCache
from clearread.services.document_library import DocumentLibrary
from clearread.services.glossary import GlossaryStore
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.reading_stats import StatsStore
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.views.ai_panel import PanelState
from clearread.ui.views.reading_view import PlaybackState

ROOT = Path(__file__).resolve().parents[2]
WINDOW_SIZE = (1280, 800)
TIMEOUT_S = 120.0
READ_WORDS = 55
EXPLAINED = ("cloroplastos", "clorofila", "fotosíntesis")
DEMO_STATS = (1860, 47 * 60)  # words, seconds: illustrative values, see the docstring


def read_client_token() -> str:
    from_env = os.environ.get("CLEARREAD_CLIENT_TOKEN", "").strip()
    if from_env:
        return from_env
    for line in (ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("CLIENT_TOKEN="):
            return line.partition("=")[2].strip().strip("\"'")
    raise SystemExit("No hay CLIENT_TOKEN en el entorno ni en backend/.env")


def pump(app: QApplication, seconds: float = 0.2) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_answer(app: QApplication, window: MainWindow) -> None:
    deadline = time.perf_counter() + TIMEOUT_S
    panel = window.reading_view.ai_panel
    while time.perf_counter() < deadline:
        app.processEvents()
        if panel.state in (PanelState.ANSWER, PanelState.ERROR):
            break
        time.sleep(0.01)
    pump(app)


def save(app: QApplication, window: MainWindow, out_dir: Path, name: str) -> None:
    pump(app)
    path = out_dir / name
    window.grab().save(str(path))
    print(f"saved {path}")


def explain(app: QApplication, window: MainWindow, word: str) -> None:
    reading = window.reading_view
    reading.explain_at(reading.editor.toPlainText().index(word))
    wait_answer(app, window)
    print(f"explain {word}: {reading.ai_panel.state.value}")


def capture_theme(
    app: QApplication, theme: str, out_dir: Path, client: BackendAIClient
) -> None:
    work = Path(tempfile.mkdtemp())
    stats = StatsStore(work / "stats.json")
    window = MainWindow(
        AppConfig(theme=theme, ai_privacy_accepted=True),
        LazyOCREngine(),
        TTSController(),
        DocumentLibrary(work / "cache"),
        config_dir=work / "config",
        ai_client=client,
        glossary=GlossaryStore(work / "glossary.json"),
        stats=stats,
    )
    window.resize(*WINDOW_SIZE)
    window.show()
    save(app, window, out_dir, f"inicio_vacio_{theme}.png")
    # The ring only shows for keyboard focus: send the event a Tab key press produces.
    tab = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.TabFocusReason)
    QApplication.sendEvent(window.home_view.sample_button, tab)
    save(app, window, out_dir, f"foco_teclado_{theme}.png")
    focus_out = QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason)
    QApplication.sendEvent(window.home_view.sample_button, focus_out)

    window.open_sample()
    reading = window.reading_view
    reading._set_state(PlaybackState.PLAYING)  # the bar shows "Pause"; no audio starts
    reading._on_word_spoken(READ_WORDS)
    save(app, window, out_dir, f"lectura_{theme}.png")
    reading.set_focus_mode(True)
    save(app, window, out_dir, f"lectura_foco_{theme}.png")
    reading.set_focus_mode(False)

    explain(app, window, EXPLAINED[0])
    save(app, window, out_dir, f"panel_ia_{theme}.png")
    for word in EXPLAINED[1:]:
        explain(app, window, word)
    window.toggle_assistant()

    window.open_words()
    save(app, window, out_dir, f"mis_palabras_{theme}.png")
    window.go_back()
    window.open_settings()
    save(app, window, out_dir, f"ajustes_{theme}.png")
    window.go_back()

    reading._on_word_spoken(READ_WORDS)
    window.go_back()
    stats.add(*DEMO_STATS)
    window.show_screen(Screen.HOME)
    save(app, window, out_dir, f"inicio_datos_{theme}.png")
    window.close()


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    load_reading_font()
    cache = DiskResponseCache(Path(tempfile.mkdtemp()) / "ai_cache.json")
    client = BackendAIClient(DEFAULT_BACKEND_URL, read_client_token(), cache, "es")
    for theme in ("light", "dark"):
        capture_theme(app, theme, out_dir, client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
