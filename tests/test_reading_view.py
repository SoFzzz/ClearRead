"""ReadingView: highlight, pause/resume, theme switch, shortcuts, texts."""

from collections.abc import Iterator

import pytest
from fakes import EngineSource, FakeEngine
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QKeySequence,
    QPalette,
    QShortcut,
    QShortcutEvent,
    QTextCursor,
)
from PySide6.QtWidgets import QApplication, QWidget
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
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet, syllable_palette
from clearread.ui.views.reader_widget import READER_MARGIN_X
from clearread.ui.views.reading_view import PlaybackState, ReadingView, ViewMode

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


def spoken_anything(engines: EngineSource) -> bool:
    return any(engine.said for engine in engines.created)


def test_click_on_a_word_only_moves_the_start_point_and_stays_silent(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    events = record_words(view)
    target = 6
    click_word(view, qtbot, target)
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == target
    token = view.token_map[target]
    assert view.editor.highlighted_range() == (token.doc_start_pos, token.doc_end_pos)
    qtbot.wait(300)
    assert events == []
    assert not spoken_anything(engines)


def test_click_while_playing_stops_the_voice_and_moves_the_start_point(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    events = record_words(view)
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 3, timeout=TIMEOUT_MS)
    target = 1
    click_word(view, qtbot, target)
    assert view.state is PlaybackState.PAUSED
    qtbot.wait(300)  # words still in flight must not move anything
    already = len(events)
    qtbot.wait(300)
    assert len(events) == already
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == target
    assert engines.voices.peak == 1


def test_play_after_a_click_reads_from_the_clicked_word(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    events = record_words(view)
    target = 7
    click_word(view, qtbot, target)
    assert events == []
    view.toggle_play()
    assert view.state is PlaybackState.PLAYING
    qtbot.waitUntil(lambda: view.state is PlaybackState.IDLE, timeout=TIMEOUT_MS)
    assert events == list(range(target, len(view.token_map)))
    script = speech_from(view.tts_script, view.token_map, target).text
    assert engines.latest.said[-1] == script


def test_click_while_paused_moves_the_start_point_without_sound(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 2, timeout=TIMEOUT_MS)
    view.toggle_play()
    assert view.state is PlaybackState.PAUSED
    qtbot.wait(300)
    events = record_words(view)
    click_word(view, qtbot, 7)
    qtbot.wait(300)
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == 7
    assert events == []


def test_pause_stops_at_once_and_late_signals_cannot_restart_the_highlight(
    view: ReadingView, qtbot: QtBot
) -> None:
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx >= 2, timeout=TIMEOUT_MS)
    view.toggle_play()
    paused_at = view.current_word_idx
    paused_range = view.editor.highlighted_range()
    view._on_word_spoken(paused_at + 3)
    view._on_playback_ended()
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == paused_at
    assert view.editor.highlighted_range() == paused_range
    assert view.play_button.text() == "Reanudar"


def test_the_play_button_shows_pause_only_while_the_voice_is_playing(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    assert view.play_button.text() == "Reproducir"
    click_word(view, qtbot, 3)
    assert view.play_button.text() == "Reanudar"
    view.toggle_play()
    assert view.play_button.text() == "Pausar"
    assert view.play_button.toolTip() == "Pausar (Espacio)"
    view.toggle_play()
    assert view.play_button.text() == "Reanudar"


def test_an_assistant_answer_read_aloud_does_not_resume_the_document(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    click_word(view, qtbot, 3)
    view.speak_aside("Respuesta corta")
    qtbot.waitUntil(lambda: engines.latest.said[-1:] == ["Respuesta corta"])
    qtbot.wait(400)
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == 3
    assert view.editor.highlighted_range() == (
        view.token_map[3].doc_start_pos,
        view.token_map[3].doc_end_pos,
    )


def test_click_on_a_space_or_punctuation_chooses_the_next_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    plain = view.editor.toPlainText()
    for position in (plain.index("."), plain.index(" ")):  # period, first space
        expected = next(
            t.word_index for t in view.token_map if t.doc_start_pos > position
        )
        x, y = x_of(view, position)
        click_at(view, qtbot, x + 2, y)  # inside the left half of that character
        assert view.current_word_idx == expected
        assert view.state is PlaybackState.PAUSED


def test_click_on_the_right_half_of_a_last_letter_still_picks_that_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    token = view.token_map[1]
    end_x, y = x_of(view, token.doc_end_pos)
    click_at(view, qtbot, end_x - 2, y)
    assert view.current_word_idx == token.word_index


def double_click_word(view: ReadingView, qtbot: QtBot, index: int) -> None:
    click_word(view, qtbot, index)  # a real double click starts with a click
    x, y = x_of(view, view.token_map[index].doc_start_pos)
    qtbot.mouseDClick(
        view.editor.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x + 6, y)
    )


def test_double_click_selects_the_word_and_offers_the_menu_without_speaking(
    view: ReadingView, engines: EngineSource, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    # The real slot opens a blocking menu; only the request itself is checked here.
    view.editor.context_menu_requested.disconnect(view._show_context_menu)
    view.set_assistant_available(True)
    events = record_words(view)
    with qtbot.waitSignal(
        view.editor.context_menu_requested, timeout=TIMEOUT_MS
    ) as hit:
        double_click_word(view, qtbot, 2)
    token = view.token_map[2]
    assert token.doc_start_pos <= hit.args[0] < token.doc_end_pos
    assert view.editor.textCursor().selectedText() == token.spoken_text
    qtbot.wait(300)
    assert view.state is PlaybackState.PAUSED
    assert events == []
    assert not spoken_anything(engines)


def test_double_click_without_the_assistant_only_selects_the_word(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    view.set_assistant_available(False)
    with qtbot.assertNotEmitted(view.editor.context_menu_requested):
        double_click_word(view, qtbot, 2)
    assert view.editor.textCursor().selectedText() == view.token_map[2].spoken_text
    assert view.state is PlaybackState.PAUSED


def test_dragging_the_mouse_selects_text_and_keeps_the_start_point(
    view: ReadingView, qtbot: QtBot
) -> None:
    shown(view, qtbot)
    first, last = view.token_map[1], view.token_map[3]
    start_x, y = x_of(view, first.doc_start_pos)
    end_x, _ = x_of(view, last.doc_end_pos)
    click_word(view, qtbot, 0)
    viewport = view.editor.viewport()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=QPoint(start_x + 2, y))
    qtbot.mouseMove(viewport, QPoint(end_x - 2, y))
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=QPoint(end_x - 2, y))
    assert view.editor.textCursor().hasSelection()
    assert view.current_word_idx == 0


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


# ---- the page sheet -------------------------------------------------------


def pixel(widget: QWidget, point: QPoint) -> str:
    return widget.grab().toImage().pixelColor(point).name().upper()


@pytest.mark.parametrize("theme_id", list(ThemeId))
def test_the_reader_text_sits_on_the_page_colour(
    view: ReadingView, theme_id: ThemeId
) -> None:
    tokens = THEMES[theme_id]
    view.editor.apply_theme(tokens)
    base = view.editor.palette().color(QPalette.ColorRole.Base)
    assert base.name().upper() == tokens.page_bg.upper()
    assert tokens.page_bg != tokens.bg


@pytest.mark.parametrize("theme_id", list(ThemeId))
def test_the_sheet_is_paper_on_the_app_background_with_generous_margins(
    tts: TTSController, qtbot: QtBot, theme_id: ThemeId
) -> None:
    tokens = THEMES[theme_id]
    widget = ReadingView(tts, theme_id)
    widget.setStyleSheet(build_stylesheet(tokens))  # as MainWindow does
    qtbot.addWidget(widget)
    widget.load_document(format_text(theme_id))
    shown(widget, qtbot)
    QApplication.processEvents()
    sheet = widget.page_sheet
    column = sheet.parentWidget()
    assert column is not None
    inside_padding = QPoint(6, sheet.height() // 2)
    above_sheet = QPoint(sheet.width() // 2, 6)
    assert pixel(sheet, inside_padding) == tokens.page_bg.upper()
    assert pixel(column, above_sheet) == tokens.bg.upper()
    text_left = widget.editor.mapTo(sheet, QPoint(0, 0)).x() + READER_MARGIN_X
    assert text_left >= 40


@pytest.mark.parametrize("mode", list(ViewMode))
def test_the_sheet_adds_nothing_to_the_minimum_width_and_no_horizontal_bar(
    tts: TTSController, qtbot: QtBot, mode: ViewMode
) -> None:
    widget = ReadingView(tts, view_mode=mode)
    qtbot.addWidget(widget)
    widget.load_document(format_text(ThemeId.LIGHT))
    widget.resize(1024, 700)
    widget.show()
    qtbot.waitExposed(widget)
    assert widget.minimumSizeHint().width() == widget.play_bar.minimumSizeHint().width()
    assert not widget.editor.horizontalScrollBar().isVisible()
