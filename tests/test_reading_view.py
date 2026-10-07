"""ReadingView: highlight, pause/resume, theme switch, shortcuts, texts."""

from collections.abc import Iterator

import pytest
from fakes import EngineSource, FakeEngine
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import FormattedDocument, TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import READING_FONT_FAMILY, load_reading_fonts
from clearread.ui.strings import Language
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.reading_view import PlaybackState, ReadingView

TEXT = "El niño leyó una canción.\n\nSegundo párrafo con cinco palabras."
TIMEOUT_MS = 5000


def format_text(theme: ThemeId) -> FormattedDocument:
    formatter = TextFormatter(SpanishSyllabifier(), syllable_palette(THEMES[theme]))
    return formatter.format_document(TEXT)


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource(word_delay_s=0.04)


@pytest.fixture
def tts(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=engines)
    yield controller
    controller.shutdown()


@pytest.fixture
def view(tts: TTSController, qtbot: QtBot) -> ReadingView:
    widget = ReadingView(tts)
    qtbot.addWidget(widget)
    widget.load_document(format_text(ThemeId.LIGHT))
    return widget


def test_the_real_reading_font_is_bundled_and_loadable(qapp: object) -> None:
    assert load_reading_fonts() == READING_FONT_FAMILY


def test_highlighted_word_is_the_one_of_the_received_event(view: ReadingView) -> None:
    for index, token in enumerate(view.token_map):
        view._tts.word_spoken.emit(index)
        assert view.editor.highlighted_range() == (
            token.doc_start_pos,
            token.doc_end_pos,
        )
        plain = view.editor.toPlainText()
        assert plain[token.doc_start_pos : token.doc_end_pos] == token.spoken_text


def test_event_outside_the_document_is_ignored(view: ReadingView) -> None:
    view._on_word_spoken(999)
    assert view.editor.highlighted_range() is None


def test_play_speaks_the_whole_script_and_highlights_along(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    seen: list[tuple[int, int] | None] = []
    view._tts.word_spoken.connect(
        lambda _i: seen.append(view.editor.highlighted_range())
    )
    view.toggle_play()
    assert view.state is PlaybackState.PLAYING
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert engines.created[0].said[0] == view.tts_script
    assert len(seen) == len(view.token_map)
    assert view.editor.highlighted_range() is None  # cleared at the end


def test_pause_then_resume_continues_from_the_word_that_was_playing(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    qtbot.waitUntil(lambda: True)  # let the worker thread initialise the engine
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 2, timeout=TIMEOUT_MS)
    view.toggle_play()  # pause
    assert view.state is PlaybackState.PAUSED
    paused_at = view.current_word_idx
    paused_range = view.editor.highlighted_range()
    qtbot.wait(300)  # nothing moves while paused
    assert view.current_word_idx == paused_at
    assert view.editor.highlighted_range() == paused_range

    resumed: list[int] = []
    view._tts.word_spoken.connect(resumed.append)
    view.toggle_play()  # resume
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    expected_script = " ".join(t.spoken_text for t in view.token_map[paused_at:])
    assert engines.latest.said[-1] == expected_script
    assert resumed[0] == paused_at
    assert resumed[-1] == len(view.token_map) - 1


def test_stop_resets_to_the_beginning(view: ReadingView, qtbot: QtBot) -> None:
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 1, timeout=TIMEOUT_MS)
    view.stop_reading()
    assert view.state is PlaybackState.IDLE
    assert view.current_word_idx == 0
    assert view.editor.highlighted_range() is None
    qtbot.wait(300)
    assert view.state is PlaybackState.IDLE  # no stale event restarts the highlight


def test_changing_theme_regenerates_html_but_not_the_token_map(
    view: ReadingView,
) -> None:
    light_map = list(view.token_map)
    light_html = view.editor.toHtml()
    dark = format_text(ThemeId.DARK)
    assert dark.token_map == light_map

    view._tts.word_spoken.emit(3)
    view.state = PlaybackState.PAUSED
    highlighted = view.editor.highlighted_range()
    view.apply_theme(ThemeId.DARK, dark.html_content)

    assert view.token_map == light_map
    assert view.editor.toHtml() != light_html
    assert view.editor.highlighted_range() == highlighted
    assert view.editor.toPlainText()[slice(*highlighted)] == light_map[3].spoken_text


def test_theme_colours_reach_the_syllables_and_the_highlight(view: ReadingView) -> None:
    dark = format_text(ThemeId.DARK)
    view.apply_theme(ThemeId.DARK, dark.html_content)
    html = view.editor.toHtml().lower()
    assert THEMES[ThemeId.DARK].syllable_even.lower() in html
    assert THEMES[ThemeId.DARK].syllable_odd.lower() in html
    view._tts.word_spoken.emit(0)
    selection = view.editor.extraSelections()[-1]
    assert selection.format.background().color().name().upper() == (
        THEMES[ThemeId.DARK].word_highlight_bg
    )
    assert selection.format.fontUnderline()


def test_space_and_escape_shortcuts(view: ReadingView, qtbot: QtBot) -> None:
    view.show()
    view.activateWindow()
    qtbot.waitActive(view)
    view.editor.setFocus()
    qtbot.waitUntil(view.editor.hasFocus, timeout=TIMEOUT_MS)
    qtbot.keyClick(view.editor, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: view.state is PlaybackState.PLAYING, timeout=TIMEOUT_MS)
    qtbot.keyClick(view.editor, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: view.state is PlaybackState.PAUSED, timeout=TIMEOUT_MS)
    qtbot.keyClick(view.editor, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)


def test_play_button_text_and_tooltip_follow_the_language_and_state(
    tts: TTSController, qtbot: QtBot
) -> None:
    english = ReadingView(tts, language=Language.EN)
    qtbot.addWidget(english)
    english.load_document(format_text(ThemeId.LIGHT))
    assert english.play_button.text() == "Play"
    assert english.play_button.toolTip() == "Play (Space)"
    english._set_state(PlaybackState.PLAYING)
    assert english.play_button.text() == "Pause"
    english._set_state(PlaybackState.PAUSED)
    assert english.play_button.text() == "Resume"


def test_spanish_texts_come_from_the_catalog(view: ReadingView) -> None:
    assert view.play_button.text() == "Reproducir"
    assert view.stop_button.text() == "Detener"
    assert view.speed_label.text() == "Velocidad"
    assert view.speed_value_label.text() == "150 palabras/min"
    assert view.counter_label.text() == f"Palabra 0 de {len(view.token_map)}"
    assert "Espacio" in view.play_button.toolTip()


def test_speed_slider_updates_the_label_and_the_engine_rate(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    view.speed_slider.setValue(200)
    assert view.speed_value_label.text() == "200 palabras/min"
    view.toggle_play()
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert engines.latest.properties["rate"] == 200


def test_tts_failure_is_shown_in_the_view_and_returns_to_idle(
    qtbot: QtBot,
) -> None:
    def broken() -> FakeEngine:
        raise OSError("no SAPI")

    controller = TTSController(engine_factory=broken)
    widget = ReadingView(controller)
    qtbot.addWidget(widget)
    widget.load_document(format_text(ThemeId.LIGHT))
    try:
        qtbot.waitUntil(lambda: not widget.status_label.isHidden(), timeout=TIMEOUT_MS)
        assert "voz" in widget.status_label.text()
        assert widget.state is PlaybackState.IDLE
    finally:
        controller.shutdown()


def test_toggle_without_a_document_does_nothing(
    tts: TTSController, qtbot: QtBot
) -> None:
    empty = ReadingView(tts)
    qtbot.addWidget(empty)
    empty.toggle_play()
    assert empty.state is PlaybackState.IDLE
