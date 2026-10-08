"""ReadingView: highlight, pause/resume, theme switch, shortcuts, texts."""

from collections.abc import Iterator

import pytest
from fakes import EngineSource, FakeEngine
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut, QShortcutEvent, QTextCursor
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FormattedDocument,
    ReadingStyle,
    TextFormatter,
    speech_from,
)
from clearread.services.tts_controller import TTSController, sapi_rate_for
from clearread.ui.fonts import READING_FONT_FAMILY, load_reading_font
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


def test_the_single_weight_reading_font_is_bundled_and_loadable(qapp: object) -> None:
    assert load_reading_font() == READING_FONT_FAMILY


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
    assert (
        engines.created[0].said[0]
        == speech_from(view.tts_script, view.token_map, 0).text
    )
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
    expected_script = speech_from(view.tts_script, view.token_map, paused_at).text
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
    view.apply_appearance(ThemeId.DARK, ReadingStyle(), 1.8, dark.html_content)

    assert view.token_map == light_map
    assert view.editor.toHtml() != light_html
    assert view.editor.highlighted_range() == highlighted
    assert view.editor.toPlainText()[slice(*highlighted)] == light_map[3].spoken_text


def test_theme_colours_reach_the_syllables_and_the_highlight(view: ReadingView) -> None:
    dark = format_text(ThemeId.DARK)
    view.apply_appearance(ThemeId.DARK, ReadingStyle(), 1.8, dark.html_content)
    html = view.editor.toHtml().lower()
    assert THEMES[ThemeId.DARK].syllable_even.lower() in html
    assert THEMES[ThemeId.DARK].syllable_odd.lower() in html
    view._tts.word_spoken.emit(0)
    selection = view.editor.extraSelections()[-1]
    assert selection.format.background().color().name().upper() == (
        THEMES[ThemeId.DARK].word_highlight_bg
    )
    assert selection.format.fontUnderline()


def press_shortcut(view: ReadingView, key: Qt.Key) -> None:
    """Fire the QShortcut bound to ``key`` through Qt's own shortcut event.

    Real key presses reach a QShortcut only while the window is the active one, which
    on Windows depends on what the desktop does with the foreground; the shortcut
    event is what the shortcut map sends once that check has passed.
    """
    sequence = QKeySequence(key)
    shortcut = next(s for s in view.findChildren(QShortcut) if s.key() == sequence)
    assert shortcut.context() is Qt.ShortcutContext.WidgetWithChildrenShortcut
    QApplication.sendEvent(shortcut, QShortcutEvent(sequence, shortcut.id()))


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_space_and_escape_shortcuts(view: ReadingView, qtbot: QtBot) -> None:
    press_shortcut(view, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: view.state is PlaybackState.PLAYING, timeout=TIMEOUT_MS)
    press_shortcut(view, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: view.state is PlaybackState.PAUSED, timeout=TIMEOUT_MS)
    press_shortcut(view, Qt.Key.Key_Escape)
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
    assert engines.latest.properties["rate"] == sapi_rate_for(200)


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


# ---- click on a word (UI-F02) ------------------------------------------------


def shown(view: ReadingView, qtbot: QtBot) -> ReadingView:
    view.resize(900, 500)
    view.show()
    qtbot.waitExposed(view)
    return view


def x_of(view: ReadingView, position: int) -> tuple[int, int]:
    cursor = QTextCursor(view.editor.document())
    cursor.setPosition(position)
    rect = view.editor.cursorRect(cursor)
    return rect.x(), rect.center().y()


def click_at(view: ReadingView, qtbot: QtBot, x: int, y: int) -> None:
    qtbot.mouseClick(
        view.editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, y)
    )


def click_word(view: ReadingView, qtbot: QtBot, index: int) -> None:
    token = view.token_map[index]
    start_x, y = x_of(view, token.doc_start_pos)
    end_x, end_y = x_of(view, token.doc_end_pos)
    assert y == end_y, "the test text must not wrap in the middle of the word"
    click_at(view, qtbot, (start_x + end_x) // 2, y)


def record_words(view: ReadingView) -> list[int]:
    events: list[int] = []
    view._tts.word_spoken.connect(events.append)
    return events


def test_click_on_a_word_reads_from_it_and_the_first_event_is_that_word(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    events = record_words(view)
    target = 6
    click_word(view, qtbot, target)
    assert view.state is PlaybackState.PLAYING
    assert view.current_word_idx == target
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert events[0] == target
    assert events == list(range(target, len(view.token_map)))
    script = speech_from(view.tts_script, view.token_map, target).text
    assert engines.latest.said[-1] == script


def test_click_while_playing_restarts_from_that_word_without_two_voices(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    events = record_words(view)
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 3, timeout=TIMEOUT_MS)
    target = 1
    already = len(events)
    click_word(view, qtbot, target)
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    after_click = events[already:]
    assert after_click == list(range(target, len(view.token_map)))
    assert engines.voices.peak == 1


def test_click_while_paused_reads_from_the_clicked_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 2, timeout=TIMEOUT_MS)
    view.toggle_play()
    assert view.state is PlaybackState.PAUSED
    events = record_words(view)
    click_word(view, qtbot, 7)
    assert view.state is PlaybackState.PLAYING
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert events[0] == 7


def test_click_on_a_space_or_punctuation_chooses_the_next_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    plain = view.editor.toPlainText()
    events = record_words(view)
    for position in (plain.index("."), plain.index(" ")):  # period, first space
        expected = next(
            t.word_index for t in view.token_map if t.doc_start_pos > position
        )
        x, y = x_of(view, position)
        click_at(view, qtbot, x + 2, y)  # inside the left half of that character
        assert view.current_word_idx == expected
        qtbot.waitUntil(lambda: bool(events), timeout=TIMEOUT_MS)
        assert events[0] == expected
        events.clear()


def test_click_on_the_right_half_of_a_last_letter_still_picks_that_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    token = view.token_map[1]
    end_x, y = x_of(view, token.doc_end_pos)
    click_at(view, qtbot, end_x - 2, y)
    assert view.current_word_idx == token.word_index


def test_double_click_selects_no_text_and_words_show_a_hand_cursor(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    token = view.token_map[2]
    x, y = x_of(view, token.doc_start_pos)
    qtbot.mouseDClick(
        view.editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x + 6, y)
    )
    assert not view.editor.textCursor().hasSelection()
    view.editor.viewport().setCursor(Qt.CursorShape.IBeamCursor)
    qtbot.mouseMove(view.editor.viewport(), QPoint(x + 6, y))
    assert view.editor.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    view.editor.enable_char_clicks()
    assert view.editor.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_click_without_a_document_does_nothing(
    tts: TTSController, qtbot: QtBot
) -> None:
    empty = ReadingView(tts)
    qtbot.addWidget(empty)
    empty._on_char_clicked(3)
    assert empty.state is PlaybackState.IDLE


def test_the_voice_receives_the_punctuation_and_the_paragraph_break(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    view.toggle_play()
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert engines.created[0].said[0] == (
        "El niño leyó una canción.\nSegundo párrafo con cinco palabras."
    )


def test_resuming_in_the_middle_of_a_sentence_keeps_the_indices_of_the_document(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    events = record_words(view)
    view._speak_from(3)  # "una canción." of the first paragraph
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert engines.latest.said[-1].startswith("una canción.\nSegundo")
    assert events == list(range(3, len(view.token_map)))
