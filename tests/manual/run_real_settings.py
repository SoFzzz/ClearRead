r"""Real run of the Settings screen (Day 7): real window, real SAPI5 voice, real files.

Run from the repo root with APPDATA pointing at a throw-away folder, so the user's own
config and cache are never touched:

    $env:APPDATA = "$env:TEMP\clearread_real"
    .\.venv\Scripts\python tests\manual\run_real_settings.py es DIR   # drives the Spanish UI
    .\.venv\Scripts\python tests\manual\run_real_settings.py en DIR   # restarted: English UI

Phase ``es`` opens the synthetic sample, changes theme, size, voice and speed while it
reads aloud, saves captures of Settings (light and dark) and switches the language to
English. Phase ``en`` is a fresh process that must start in English. Only the synthetic
sample is used and only voice names are printed.
"""

import sys
import time
from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import SAMPLES_DIR
from test_settings import spanish_leaks

from clearread.core.config import AppConfig
from clearread.core.paths import get_user_data_dir
from clearread.services.document_library import DocumentLibrary
from clearread.services.ocr_engine import LazyOCREngine
from clearread.services.tts_controller import TTSController, create_sapi_engine
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.views.reading_view import PlaybackState

SAMPLE = SAMPLES_DIR / "sample_page_digital.pdf"
WINDOW_SIZE = (1280, 800)
TIMEOUT_S = 60.0
SPEED_SAMPLE_S = 6.0


def pump(app: QApplication, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def wait_until(app: QApplication, condition, what: str) -> None:  # type: ignore[no-untyped-def]
    end = time.perf_counter() + TIMEOUT_S
    while not condition():
        if time.perf_counter() > end:
            raise TimeoutError(what)
        pump(app, 0.02)


class RecordingEngine:
    """The real pyttsx3 engine; remembers which voice each utterance really used.

    pyttsx3 applies a property change when ``runAndWait()`` runs, so the voice is read
    back right after it returns (still on the speech thread).
    """

    used_voices: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self._engine = create_sapi_engine()

    def runAndWait(self) -> None:
        self._engine.runAndWait()
        self.used_voices.append(self._engine.getProperty("voice"))

    def __getattr__(self, name: str) -> object:
        return getattr(self._engine, name)


def build_window() -> MainWindow:
    load_reading_font()
    window = MainWindow(
        AppConfig.load(),
        LazyOCREngine(),
        TTSController(engine_factory=RecordingEngine),  # type: ignore[arg-type]
        DocumentLibrary(get_user_data_dir() / "cache"),
    )
    window.resize(*WINDOW_SIZE)
    window.show()
    return window


def save(window: MainWindow, out_dir: Path, name: str) -> None:
    path = out_dir / name
    window.grab().save(str(path))
    print(f"saved {path}")


def words_per_minute(app: QApplication, window: MainWindow) -> float:
    reading = window.reading_view
    reading.stop_reading()
    pump(app, 0.5)
    seen: list[float] = []
    reading._tts.word_spoken.connect(lambda _i: seen.append(time.perf_counter()))
    reading.toggle_play()
    pump(app, SPEED_SAMPLE_S)
    reading.stop_reading()
    reading._tts.word_spoken.disconnect()
    reading._tts.word_spoken.connect(reading._on_word_spoken)
    if len(seen) < 3:
        return 0.0
    return 60.0 * (len(seen) - 1) / (seen[-1] - seen[0])


def phase_spanish(app: QApplication, out_dir: Path) -> None:
    window = build_window()
    view = window.settings_view
    wait_until(app, lambda: window._tts.voices, "voices")
    names = [voice.name for voice in window._tts.voices]
    print(f"voices detected ({len(names)}):")
    for name in names:
        print(f"  - {name}")
    print("settings voice list == detected:", view.voice_combo.count() == len(names))

    window.open_document(str(SAMPLE))
    wait_until(app, lambda: window.screen_shown is Screen.READING, "reading")
    reading = window.reading_view
    tokens_before = list(reading.token_map)
    reading.toggle_play()
    wait_until(app, lambda: reading.current_word_idx >= 3, "playback")
    word_before = reading.current_word_idx
    reading.editor.grab()

    window.open_settings()
    view.theme_buttons["dark"].setChecked(True)
    view.sliders["font_size_pt"].setValue(22)
    pump(app, 0.5)
    print(
        "theme+size changed while reading: state",
        reading.state.value,
        "| word",
        word_before,
        "->",
        reading.current_word_idx,
        "| token map unchanged:",
        reading.token_map == tokens_before,
        "| highlight on a word:",
        reading.editor.highlighted_range() is not None,
    )
    pump(app, 1.0)
    save(window, out_dir, "ajustes_real_dark.png")
    view.theme_buttons["light"].setChecked(True)
    view.sliders["font_size_pt"].setValue(16)
    pump(app, 0.3)
    save(window, out_dir, "ajustes_real_light.png")
    window.go_back()
    assert window.screen_shown is Screen.READING
    reading.stop_reading()

    for wpm in (120, 300):
        view.sliders["reading_speed_wpm"].setValue(wpm)
        measured = words_per_minute(app, window)
        print(
            f"speed slider {wpm}: measured {measured:.0f} words/min over a {SPEED_SAMPLE_S:.0f} s listen"
        )

    for voice in window._tts.voices[:2]:
        view.voice_combo.setCurrentIndex(view.voice_combo.findData(voice.id))
        RecordingEngine.used_voices.clear()
        reading.toggle_play()
        pump(app, 2.0)
        reading.stop_reading()
        pump(app, 0.6)
        used = RecordingEngine.used_voices[-1:] == [voice.id]
        print(f"voice chosen: {voice.name!r} -> the speech engine used it: {used}")

    view.language_combo.setCurrentIndex(view.language_combo.findData("en"))
    pump(app, 0.5)
    print("restart notice shown:", view.dialog is not None)
    if view.dialog is not None:
        view.dialog.close()
    print("config.json language:", AppConfig.load().ui_language)
    window.close()


def phase_english(app: QApplication, out_dir: Path) -> None:
    window = build_window()
    print("ui language at start:", window._language.value)
    wait_until(app, lambda: window._tts.voices, "voices")
    save(window, out_dir, "inicio_real_en.png")
    window.open_document(str(SAMPLE))
    wait_until(app, lambda: window.screen_shown is Screen.READING, "reading")
    reading = window.reading_view
    reading._set_state(PlaybackState.PAUSED)
    save(window, out_dir, "lectura_real_en.png")
    window.open_settings()
    pump(app, 0.5)
    save(window, out_dir, "ajustes_real_en.png")
    leaks = 0
    for screen in (Screen.HOME, Screen.PROCESSING, Screen.READING, Screen.SETTINGS):
        window.show_screen(screen)
        leaks += len(spanish_leaks(window))
    print("Spanish catalog texts found in English screens:", leaks)
    print(
        "saved config theme/size after the Spanish run:",
        window._config.theme,
        window._config.font_size_pt,
    )
    QTimer.singleShot(0, window.close)
    window.close()


def main() -> int:
    phase, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setApplicationName("ClearRead")
    {"es": phase_spanish, "en": phase_english}[phase](app, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
