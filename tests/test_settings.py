"""Settings view and its effect on the window (CFG-F01, CFG-F02, I18N-F01, Day 7)."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QMessageBox,
    QWidget,
)
from pytestqt.qtbot import QtBot
from samples.make_samples import SAMPLES_DIR

from clearread.core.config import DEFAULT_BACKEND_URL, AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.tts_controller import (
    TTSController,
    VoiceInfo,
    sort_voices,
)
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.strings import CATALOG
from clearread.ui.theme import THEMES, ThemeId
from clearread.ui.views.reading_view import PlaybackState
from clearread.workers.ocr_worker import ProcessingErrorKind

DIGITAL = SAMPLES_DIR / "sample_page_digital.pdf"
TIMEOUT_MS = 60000
AUTONYMS = {"settings.language.es", "settings.language.en"}


class NoOCR:
    def process_image(self, image: object, page_number: int = 1) -> None:
        raise AssertionError("the digital sample never needs OCR")


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource(word_delay_s=0.02)


@pytest.fixture
def tts(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=engines)
    yield controller
    controller.shutdown()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path / "config"


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


def wait_for_voices(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: window.settings_view.voice_combo.count() > 1)


# ---- persistence ---------------------------------------------------------


def test_every_setting_changed_in_the_view_is_saved_and_reloaded(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    wait_for_voices(qtbot, window)
    view = window.settings_view
    view.theme_buttons["dark"].setChecked(True)
    view.sliders["font_size_pt"].setValue(22)
    view.sliders["line_spacing"].setValue(22)  # 2.2
    view.sliders["letter_spacing"].setValue(5)  # 2.5 px
    view.sliders["word_spacing"].setValue(8)
    view.sliders["reading_speed_wpm"].setValue(210)
    view.syllables_check.setChecked(False)
    view.voice_combo.setCurrentIndex(view.voice_combo.findData("en-1"))
    view.language_combo.setCurrentIndex(view.language_combo.findData("en"))
    view.advanced_toggle.setChecked(True)
    view.url_edit.setText("https://example.test/api")
    view.url_edit.editingFinished.emit()

    saved = AppConfig.load(config_dir)
    assert saved == AppConfig(
        theme="dark",
        font_size_pt=22,
        line_spacing=2.2,
        letter_spacing=2.5,
        word_spacing=8,
        syllables_enabled=False,
        reading_speed_wpm=210,
        voice_id="en-1",
        backend_url="https://example.test/api",
        ui_language="en",
    )

    reopened = make_window(qtbot, tts, library, config_dir, AppConfig.load(config_dir))
    wait_for_voices(qtbot, reopened)
    again = reopened.settings_view
    assert again.theme_buttons["dark"].isChecked()
    assert again.sliders["font_size_pt"].value() == 22
    assert again.sliders["line_spacing"].value() == 22
    assert again.sliders["letter_spacing"].value() == 5
    assert again.sliders["word_spacing"].value() == 8
    assert again.sliders["reading_speed_wpm"].value() == 210
    assert not again.syllables_check.isChecked()
    assert again.voice_combo.currentData() == "en-1"
    assert again.language_combo.currentData() == "en"
    assert again.url_edit.text() == "https://example.test/api"


def test_a_failed_save_is_reported_and_the_change_still_applies(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
) -> None:
    blocked = tmp_path / "not-a-folder"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    window = make_window(qtbot, tts, library, blocked)
    window.settings_view.theme_buttons["dark"].setChecked(True)
    assert window.tokens is THEMES[ThemeId.DARK]
    assert not window.settings_view.save_error_label.isHidden()


def test_reset_restores_the_defaults_but_keeps_voice_language_and_address(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    config = AppConfig(
        theme="dark",
        font_size_pt=24,
        voice_id="x",
        ui_language="en",
        backend_url="http://a.b",
    )
    window = make_window(qtbot, tts, library, config_dir, config)
    window.settings_view.reset_button.click()
    saved = AppConfig.load(config_dir)
    assert saved == AppConfig(voice_id="x", ui_language="en", backend_url="http://a.b")


def test_an_invalid_address_is_refused_and_the_old_one_stays(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    view = window.settings_view
    view.advanced_toggle.setChecked(True)
    view.url_edit.setText("not an address")
    view.url_edit.editingFinished.emit()
    assert view.url_edit.text() == DEFAULT_BACKEND_URL
    assert not view.url_error_label.isHidden()
    view.url_edit.setText("https://other.test")
    view.url_edit.editingFinished.emit()
    view.url_reset_button.click()
    assert view.url_edit.text() == DEFAULT_BACKEND_URL
    assert AppConfig.load(config_dir).backend_url == DEFAULT_BACKEND_URL


# ---- navigation ----------------------------------------------------------


def test_settings_open_from_home_and_reading_and_back_returns_to_the_origin(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    window.settings_button.click()
    assert window.screen_shown is Screen.SETTINGS
    window.back_button.click()
    assert window.screen_shown is Screen.HOME

    open_sample(qtbot, window)
    window.settings_button.click()
    assert window.screen_shown is Screen.SETTINGS
    window.settings_view.back_requested.emit()
    assert window.screen_shown is Screen.READING


def test_the_settings_button_is_off_while_processing(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    window.show_screen(Screen.PROCESSING)
    assert not window.settings_button.isEnabled()
    window.open_settings()
    assert window.screen_shown is Screen.PROCESSING


# ---- live effect on the reading view -------------------------------------


def test_changing_the_theme_with_a_document_open_keeps_the_current_word(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    reading = window.reading_view
    token_map = list(reading.token_map)
    reading._on_word_spoken(4)
    reading._set_state(PlaybackState.PAUSED)
    highlighted = reading.editor.highlighted_range()
    light_html = reading.editor.toHtml()

    window.settings_view.theme_buttons["dark"].setChecked(True)

    assert reading.token_map == token_map
    assert reading.current_word_idx == 4
    assert reading.editor.highlighted_range() == highlighted
    assert highlighted is not None
    assert reading.editor.toPlainText()[slice(*highlighted)] == token_map[4].spoken_text
    assert reading.editor.toHtml() != light_html
    assert THEMES[ThemeId.DARK].syllable_odd.lower() in reading.editor.toHtml().lower()
    assert THEMES[ThemeId.DARK].bg.lower() in window.styleSheet().lower()


def test_size_and_spacing_changes_reach_the_open_document_without_losing_the_word(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    reading = window.reading_view
    token_map = list(reading.token_map)
    reading._on_word_spoken(2)
    reading._set_state(PlaybackState.PLAYING)
    view = window.settings_view

    view.sliders["font_size_pt"].setValue(24)
    view.sliders["letter_spacing"].setValue(4)
    view.sliders["word_spacing"].setValue(10)
    view.sliders["line_spacing"].setValue(24)

    assert reading.editor.reading_font.pointSize() == 24
    cursor = QTextCursor(reading.editor.document())
    cursor.setPosition(token_map[2].doc_start_pos + 1)
    font = cursor.charFormat().font()
    assert font.pointSize() == 24
    assert font.letterSpacing() == 2.0
    assert font.wordSpacing() == 10.0
    assert reading.token_map == token_map
    highlighted = reading.editor.highlighted_range()
    assert highlighted is not None
    assert reading.editor.toPlainText()[slice(*highlighted)] == token_map[2].spoken_text


def test_turning_syllable_colours_off_leaves_one_colour_per_word(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    reading = window.reading_view
    odd = THEMES[ThemeId.LIGHT].syllable_odd.lower()
    assert odd in reading.editor.toHtml().lower()
    window.settings_view.syllables_check.setChecked(False)
    assert odd not in reading.editor.toHtml().lower()
    assert reading.token_map


def test_a_document_opened_later_uses_the_saved_look(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    window.settings_view.sliders["font_size_pt"].setValue(20)
    open_sample(qtbot, window)
    assert "20pt" in window.reading_view.editor.toHtml()
    window.go_back()
    window.settings_view.theme_buttons["high_contrast"].setChecked(True)
    window.open_recent(library.recents()[0].key)
    assert window.screen_shown is Screen.READING
    assert "20pt" in window.reading_view.editor.toHtml()
    assert THEMES[ThemeId.HIGH_CONTRAST].syllable_odd.lower() in (
        window.reading_view.editor.toHtml().lower()
    )


def test_the_preview_follows_the_controls(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    preview = window.settings_view.preview
    window.settings_view.sliders["font_size_pt"].setValue(26)
    assert preview.reading_font.pointSize() == 26
    assert preview.highlighted_range() is not None
    window.settings_view.theme_buttons["dark"].setChecked(True)
    assert THEMES[ThemeId.DARK].syllable_odd.lower() in preview.toHtml().lower()


# ---- voice and speed -----------------------------------------------------


def test_voices_are_listed_with_the_spanish_ones_first(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    wait_for_voices(qtbot, window)
    combo = window.settings_view.voice_combo
    names = [combo.itemText(i) for i in range(combo.count())]
    assert "Spanish" in names[0]
    assert "English" in names[1]


def test_sort_voices_puts_spanish_first_then_alphabetical() -> None:
    voices = [
        VoiceInfo("1", "Zira - English"),
        VoiceInfo("2", "Sabina - Spanish (Mexico)"),
        VoiceInfo("3", "David - English"),
        VoiceInfo("4", "Helena - Spanish (Spain)"),
    ]
    assert [v.id for v in sort_voices(voices)] == ["4", "2", "3", "1"]


def test_the_chosen_voice_is_the_one_the_engine_speaks_with(
    qtbot: QtBot,
    tts: TTSController,
    engines: EngineSource,
    library: DocumentLibrary,
    config_dir: Path,
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    wait_for_voices(qtbot, window)
    open_sample(qtbot, window)
    combo = window.settings_view.voice_combo
    combo.setCurrentIndex(combo.findData("en-1"))
    window.reading_view.toggle_play()
    qtbot.waitUntil(lambda: bool(engines.latest.said), timeout=TIMEOUT_MS)
    assert engines.latest.properties["voice"] == "en-1"
    window.reading_view.stop_reading()


def test_the_saved_voice_is_used_at_start_up(
    qtbot: QtBot,
    tts: TTSController,
    engines: EngineSource,
    library: DocumentLibrary,
    config_dir: Path,
) -> None:
    window = make_window(qtbot, tts, library, config_dir, AppConfig(voice_id="en-1"))
    wait_for_voices(qtbot, window)
    assert window.settings_view.voice_combo.currentData() == "en-1"
    open_sample(qtbot, window)
    window.reading_view.toggle_play()
    qtbot.waitUntil(lambda: bool(engines.latest.said), timeout=TIMEOUT_MS)
    assert engines.latest.properties["voice"] == "en-1"
    window.reading_view.stop_reading()


def test_speed_is_shared_between_settings_and_the_reading_bar(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    window.settings_view.sliders["reading_speed_wpm"].setValue(200)
    assert window.reading_view.speed_slider.value() == 200
    window.reading_view.speed_slider.setValue(120)
    assert window.settings_view.sliders["reading_speed_wpm"].value() == 120
    assert AppConfig.load(config_dir).reading_speed_wpm == 120


def test_the_saved_speed_is_in_the_reading_bar_at_start_up(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(
        qtbot, tts, library, config_dir, AppConfig(reading_speed_wpm=300)
    )
    assert window.reading_view.speed_slider.value() == 300
    assert window.reading_view.speed_slider.maximum() == 320
    assert window.reading_view.speed_slider.minimum() == 80


# ---- privacy and recents -------------------------------------------------


def test_clearing_recents_asks_first_and_then_empties_the_cache(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, window)
    window.go_back()
    assert library.recents()
    cache_root = library._root
    assert any(cache_root.glob("*.json"))

    window.open_settings()
    window.settings_view.clear_button.click()
    box = window.settings_view.dialog
    assert isinstance(box, QMessageBox)
    cancel = next(b for b in box.buttons() if b.text() == "Cancelar")
    cancel.click()
    assert library.recents()  # Cancel keeps everything

    window.settings_view.clear_button.click()
    box = window.settings_view.dialog
    assert isinstance(box, QMessageBox)
    yes = next(b for b in box.buttons() if b.text() == "Sí, borrar")
    yes.click()

    assert library.recents() == []
    assert not any(cache_root.glob("*.json"))
    assert window.home_view.recent_items == []
    assert window.settings_view.clear_status_label.text() == (
        "Documentos recientes borrados."
    )


def test_privacy_notice_says_what_is_sent_and_where_the_cache_lives(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir)
    texts = " ".join(
        label.text() for label in window.settings_view.findChildren(QLabel)
    )
    assert "solo recibe el texto que seleccionas" in texts
    assert "%APPDATA%\\ClearRead\\cache" in texts


# ---- language (I18N-F01) -------------------------------------------------


def spanish_fragments() -> set[str]:
    """Literal pieces of Spanish catalog texts that do not also occur in English ones."""
    english = " ".join(entry["en"] for entry in CATALOG.values()).lower()
    fragments: set[str] = set()
    for key, entry in CATALOG.items():
        if key in AUTONYMS:
            continue
        for piece in re.split(r"\{[^}]*\}", entry["es"]):
            piece = piece.strip(" ·")
            if len(piece) >= 5 and piece.lower() not in english:
                fragments.add(piece)
    return fragments


def visible_texts(root: QWidget) -> list[str]:
    texts: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        texts += [widget.toolTip(), widget.accessibleName()]
        if isinstance(widget, QLabel | QAbstractButton):
            texts.append(widget.text())
        if isinstance(widget, QComboBox):
            texts += [widget.itemText(i) for i in range(widget.count())]
    return [text for text in texts if text]


def spanish_leaks(root: QWidget) -> list[str]:
    fragments = spanish_fragments()
    return [
        text
        for text in visible_texts(root)
        if any(fragment in text for fragment in fragments)
    ]


def test_in_english_no_screen_shows_spanish_catalog_text_after_a_restart(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    config_dir: Path,
) -> None:
    first = make_window(qtbot, tts, library, config_dir)
    open_sample(qtbot, first)
    first.go_back()
    first.open_settings()
    combo = first.settings_view.language_combo
    combo.setCurrentIndex(combo.findData("en"))
    notice = first.settings_view.dialog
    assert isinstance(notice, QMessageBox)
    assert notice.windowTitle() == "Restart ClearRead to change the language"
    first.close()

    config = AppConfig.load(config_dir)
    assert config.ui_language == "en"
    window = make_window(qtbot, tts, library, config_dir, config)
    wait_for_voices(qtbot, window)
    assert spanish_fragments()  # the check below is not vacuous

    for screen in (Screen.HOME, Screen.PROCESSING, Screen.SETTINGS):
        window.show_screen(screen)
        assert spanish_leaks(window) == [], screen
    open_sample(qtbot, window)
    assert spanish_leaks(window) == []
    window.reading_view._set_state(PlaybackState.PLAYING)
    assert spanish_leaks(window) == []
    window.reading_view._set_state(PlaybackState.PAUSED)
    assert spanish_leaks(window) == []

    window.open_settings()
    window.settings_view.clear_button.click()
    assert window.settings_view.dialog is not None
    assert spanish_leaks(window.settings_view.dialog) == []
    window.settings_view.dialog.close()
    window.settings_view.url_edit.setText("nope")
    window.settings_view.url_edit.editingFinished.emit()
    assert spanish_leaks(window.settings_view) == []

    window.show_screen(Screen.HOME)
    window._show_error(ProcessingErrorKind.PASSWORD)
    assert window.error_dialog is not None
    assert spanish_leaks(window.error_dialog) == []
    assert window.settings_button.text() == "Settings"
    assert window.home_view.choose_button.text() == "Choose file"


def test_the_leak_check_catches_spanish_in_an_english_window(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, config_dir: Path
) -> None:
    window = make_window(qtbot, tts, library, config_dir, AppConfig(ui_language="en"))
    window.back_button.setText("← Inicio")
    assert spanish_leaks(window) == ["← Inicio"]
