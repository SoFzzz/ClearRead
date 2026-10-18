"""Yellow text selection, voice that follows the interface language, syllable toggle."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit
from pytestqt.qtbot import QtBot
from samples.make_samples import SAMPLES_DIR

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.tts_controller import (
    TTSController,
    VoiceInfo,
    choose_voice,
    sort_voices,
)
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet
from clearread.ui.views.reader_widget import ReaderWidget

DIGITAL = SAMPLES_DIR / "sample_page_digital.pdf"
TIMEOUT_MS = 60000
ACTIVE = QPalette.ColorGroup.Active
INACTIVE = QPalette.ColorGroup.Inactive
HIGHLIGHT = QPalette.ColorRole.Highlight
HIGHLIGHTED_TEXT = QPalette.ColorRole.HighlightedText
TOKENS_KEY = "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\"
ZIRA = VoiceInfo(
    TOKENS_KEY + "TTS_MS_EN-US_ZIRA_11.0",
    "Microsoft Zira Desktop - English (United States)",
)
DAVID = VoiceInfo(
    TOKENS_KEY + "TTS_MS_EN-US_DAVID_11.0",
    "Microsoft David Desktop - English (United States)",
)
HELENA = VoiceInfo(
    TOKENS_KEY + "TTS_MS_ES-ES_HELENA_11.0",
    "Microsoft Helena Desktop - Spanish (Spain)",
)
HARUKA = VoiceInfo(
    TOKENS_KEY + "TTS_MS_JA-JP_HARUKA_11.0",
    "Microsoft Haruka Desktop - Japanese",
)


class NoOCR:
    def process_image(self, image: object, page_number: int = 1) -> None:
        raise AssertionError("the digital sample never needs OCR")


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(tmp_path / "cache")


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    config_dir: Path,
    config: AppConfig | None = None,
) -> MainWindow:
    load_reading_font()
    window = MainWindow(
        config or AppConfig(),
        NoOCR(),  # type: ignore[arg-type]
        tts,
        library,
        config_dir=config_dir,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def open_sample(qtbot: QtBot, window: MainWindow) -> None:
    window.open_document(str(DIGITAL))
    qtbot.waitUntil(lambda: window.screen_shown is Screen.READING, timeout=TIMEOUT_MS)


# ---- selection colours ---------------------------------------------------


@pytest.mark.parametrize("theme", list(ThemeId))
def test_reader_selection_is_yellow_in_active_and_inactive_groups(
    qtbot: QtBot, theme: ThemeId
) -> None:
    tokens = THEMES[theme]
    reader = ReaderWidget(tokens)
    qtbot.addWidget(reader)
    palette = reader.palette()
    for group in (ACTIVE, INACTIVE):
        assert palette.color(group, HIGHLIGHT) == QColor(tokens.selection_bg)
        assert palette.color(group, HIGHLIGHTED_TEXT) == QColor(tokens.selection_fg)


@pytest.mark.parametrize("theme", list(ThemeId))
def test_selection_ignores_the_system_accent_colour(
    qtbot: QtBot, theme: ThemeId
) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = app.palette()
    accent = app.palette()
    accent.setColor(HIGHLIGHT, QColor("#C62828"))  # a red Windows accent colour
    app.setPalette(accent)
    try:
        tokens = THEMES[theme]
        app.setStyleSheet(build_stylesheet(tokens))
        widgets = [ReaderWidget(tokens), QLabel("texto"), QLineEdit("texto")]
        for widget in widgets:
            qtbot.addWidget(widget)
            widget.show()
            for group in (ACTIVE, INACTIVE):
                shown = widget.palette().color(group, HIGHLIGHT)
                assert shown == QColor(tokens.selection_bg), type(widget).__name__
    finally:
        app.setStyleSheet("")
        app.setPalette(original)


# ---- voice follows the interface language --------------------------------


def test_voice_language_comes_from_the_id_then_from_the_name() -> None:
    assert HELENA.language == "es"
    assert ZIRA.language == "en"
    assert HARUKA.language is None
    assert VoiceInfo("x", "Sabina - Spanish (Mexico)").language == "es"
    assert VoiceInfo("x", "Some English voice").language == "en"
    assert VoiceInfo("MSTTS_V110_enGB_HazelM", "Hazel").language == "en"


def test_the_voice_of_the_current_language_is_kept() -> None:
    voices = [HELENA, DAVID, ZIRA]
    assert choose_voice(voices, "es", HELENA.id) == HELENA.id
    assert choose_voice(voices, "en", ZIRA.id) == ZIRA.id


def test_each_ui_language_takes_the_first_voice_that_speaks_it() -> None:
    voices = [HELENA, ZIRA, HARUKA, DAVID]
    assert choose_voice(voices, "en", HELENA.id) == DAVID.id
    assert choose_voice(voices, "en", "") == DAVID.id
    assert choose_voice(voices, "es", ZIRA.id) == HELENA.id
    assert choose_voice(voices, "es", "") == HELENA.id


def test_a_voice_of_another_language_or_an_unknown_one_is_replaced() -> None:
    assert choose_voice([HELENA, DAVID], "en", "gone") == DAVID.id
    assert choose_voice([HELENA, DAVID], "en", HARUKA.id) == DAVID.id


def test_the_current_voice_stays_when_none_matches_the_language() -> None:
    assert choose_voice([HELENA, HARUKA], "en", HELENA.id) == HELENA.id
    assert choose_voice([HELENA], "en", "") == ""
    assert choose_voice([], "es", "kept") == "kept"


def test_sort_voices_puts_the_language_asked_first() -> None:
    voices = [HELENA, ZIRA, HARUKA, DAVID]
    assert sort_voices(voices, "en") == [DAVID, ZIRA, HARUKA, HELENA]
    assert sort_voices(voices) == [HELENA, DAVID, HARUKA, ZIRA]


def wait_for_voices(qtbot: QtBot, tts: TTSController) -> None:
    qtbot.waitUntil(lambda: bool(tts.voices), timeout=TIMEOUT_MS)


def test_english_ui_replaces_a_spanish_voice_with_an_english_one_and_saves_it(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config = AppConfig(ui_language="en", voice_id="es-1")
    window = make_window(qtbot, tts, library, config_dir, config)
    wait_for_voices(qtbot, tts)
    window.follow_language_voice()
    qtbot.waitUntil(lambda: AppConfig.load(config_dir).voice_id == "en-1")
    combo = window.settings_view.voice_combo
    assert combo.currentData() == "en-1"
    assert "English" in combo.itemText(0)  # the interface language comes first


def test_spanish_ui_keeps_its_spanish_voice_and_writes_nothing(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    window = make_window(qtbot, tts, library, config_dir, AppConfig(voice_id="es-1"))
    wait_for_voices(qtbot, tts)
    window.follow_language_voice()
    assert not (config_dir / "config.json").exists()
    assert window.settings_view.config.voice_id == "es-1"


def test_no_saved_voice_gets_one_for_the_language(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config = AppConfig(ui_language="en")
    window = make_window(qtbot, tts, library, tmp_path / "config", config)
    window.follow_language_voice()  # voices may still be unlisted: it waits for them
    qtbot.waitUntil(lambda: window.settings_view.config.voice_id == "en-1")


def test_the_voice_stays_when_no_installed_voice_speaks_the_ui_language(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config = AppConfig(ui_language="en", voice_id="es-1")
    window = make_window(qtbot, tts, library, config_dir, config)
    window._adopt_language_voice([VoiceInfo("es-1", "Helena - Spanish (Spain)")])
    assert window.settings_view.config.voice_id == "es-1"
    assert not (config_dir / "config.json").exists()


# ---- syllable colours toggle ---------------------------------------------


def spans_of(window: MainWindow) -> int:
    return window.reading_view.editor.toHtml().lower().count("<span")


def one_span_per_word(window: MainWindow) -> int:
    """Spans Qt reports for the open text when every word is one span."""
    assert window._raw_text is not None
    html = window._format(window._raw_text).html_content
    probe = ReaderWidget(window.tokens)
    probe.setHtml(html)
    return probe.toHtml().lower().count("<span")


def test_the_bar_button_shows_the_saved_setting(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    on = make_window(qtbot, tts, library, tmp_path / "a")
    off = make_window(
        qtbot, tts, library, tmp_path / "b", AppConfig(syllables_enabled=False)
    )
    assert on.reading_view.syllables_button.isChecked()
    assert not off.reading_view.syllables_button.isChecked()


def test_bar_button_updates_settings_saves_and_rerenders_keeping_the_place(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    view = window.reading_view
    start = len(view.token_map) // 2
    view._move_start_to(start)
    tokens_before = list(view.token_map)
    text_before = view.editor.toPlainText()
    range_before = view.editor.highlighted_range()
    coloured_spans = spans_of(window)

    view.syllables_button.click()

    assert not window.settings_view.syllables_check.isChecked()
    assert not window.settings_view.config.syllables_enabled
    assert AppConfig.load(config_dir).syllables_enabled is False
    assert view.token_map == tokens_before
    assert view.editor.toPlainText() == text_before
    assert view.current_word_idx == start
    assert view.editor.highlighted_range() == range_before
    assert spans_of(window) < coloured_spans


def test_without_syllables_each_word_is_one_span_in_the_text_colour(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config = AppConfig(syllables_enabled=False, theme="dark")
    window = make_window(qtbot, tts, library, tmp_path / "config", config)
    open_sample(qtbot, window)
    html = window.reading_view.editor.toHtml().lower()
    dark = THEMES[ThemeId.DARK]
    assert window._raw_text is not None
    plain_html = window._format(window._raw_text).html_content
    assert plain_html.count("<span") == len(window.reading_view.token_map)
    assert dark.text.lower() in html
    assert dark.syllable_even.lower() not in html


def test_settings_switch_moves_the_bar_button_and_back(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    with_colours = spans_of(window)
    window.settings_view.syllables_check.setChecked(False)
    assert not window.reading_view.syllables_button.isChecked()
    assert spans_of(window) < with_colours
    window.reading_view.syllables_button.click()
    assert window.settings_view.syllables_check.isChecked()
    assert spans_of(window) == with_colours
    assert AppConfig.load(config_dir).syllables_enabled is True


def test_a_cached_document_is_formatted_again_when_the_setting_changed(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path / "config")
    open_sample(qtbot, window)
    key = library.recents()[0].key
    window.reading_view.syllables_button.click()
    window._show_cached(key, "x")
    assert spans_of(window) == one_span_per_word(window)


def test_s_shortcut_toggles_the_syllables(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path / "config")
    open_sample(qtbot, window)
    qtbot.keyClick(window.reading_view.editor, "s")
    assert not window.reading_view.syllables_button.isChecked()
    assert not window.settings_view.config.syllables_enabled
