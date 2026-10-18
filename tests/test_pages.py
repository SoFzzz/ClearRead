"""Pages and view modes: page boundaries, navigation, auto page turn, zoom, config."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
    QShortcutEvent,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from test_main_window import (
    FakeOCR,
    multi_page_scan,
    wait_for_idle,
    wait_for_screen,
)

from clearread.core.config import FONT_SIZE_RANGE_PT, AppConfig
from clearread.services.document_library import CachedDocument, DocumentLibrary
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FORMATTER_VERSION,
    PAGE_BREAK,
    FormattedDocument,
    ReadingStyle,
    TextFormatter,
    page_index_at,
)
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.reading_view import (
    ZOOM_IN,
    ZOOM_OUT,
    ZOOM_RESET,
    PlaybackState,
    ReadingView,
    ViewMode,
)

PARAGRAPHS_PER_PAGE = 14
PAGES = 3


def press(view: ReadingView, sequence: str | Qt.Key) -> None:
    """Fire the QShortcut bound to ``sequence`` the way Qt does once the window is active."""
    key = QKeySequence(sequence)
    shortcut = next(s for s in view.findChildren(QShortcut) if s.key() == key)
    assert shortcut.context() is Qt.ShortcutContext.WidgetWithChildrenShortcut
    QApplication.sendEvent(shortcut, QShortcutEvent(key, shortcut.id()))


def page_text(page: int) -> str:
    paragraphs = (
        f"Pagina {page} parrafo {n}. El niño lee una canción con calma "
        "y escribe palabras difíciles en su cuaderno azul."
        for n in range(PARAGRAPHS_PER_PAGE)
    )
    return "\n\n".join(paragraphs)


def multi_page_raw() -> str:
    return PAGE_BREAK.join(page_text(page) for page in range(1, PAGES + 1))


def formatter() -> TextFormatter:
    palette = syllable_palette(THEMES[ThemeId.LIGHT])
    return TextFormatter(SpanishSyllabifier(), palette)


def first_token_of(document: FormattedDocument, page: int) -> int:
    start = document.page_starts[page]
    return next(
        index
        for index, token in enumerate(document.token_map)
        if token.doc_start_pos >= start
    )


# ---- formatter ------------------------------------------------------------------


def test_each_page_start_is_the_first_character_of_its_first_paragraph() -> None:
    document = formatter().format_document("Uno dos.\n\nTres." + PAGE_BREAK + "Cuatro.")
    assert document.page_starts == (0, len("Uno dos.") + 1 + len("Tres.") + 1)
    assert document.tts_script == "Uno dos.\nTres.\nCuatro."


def test_a_text_without_page_breaks_is_one_page() -> None:
    assert formatter().format_document("Uno.\n\nDos.").page_starts == (0,)
    assert formatter().format_document("   ").page_starts == (0,)


def test_empty_pages_are_skipped() -> None:
    raw = PAGE_BREAK.join(["Uno.", "  \n ", "Dos."])
    assert len(formatter().format_document(raw).page_starts) == 2


def test_token_positions_still_match_the_rendered_text_on_every_page() -> None:
    document = formatter().format_document(multi_page_raw())
    rendered = QTextDocument()
    rendered.setHtml(document.html_content)
    plain = rendered.toPlainText()
    assert plain == document.tts_script
    for token in document.token_map:
        assert plain[token.doc_start_pos : token.doc_end_pos] == token.spoken_text


def test_page_index_at_follows_the_page_starts() -> None:
    starts = (0, 10, 25)
    assert [page_index_at(starts, pos) for pos in (0, 9, 10, 24, 25, 99)] == [
        0,
        0,
        1,
        1,
        2,
        2,
    ]


# ---- config and cache ---------------------------------------------------------


def test_view_mode_defaults_to_continuous_and_persists(tmp_path: Path) -> None:
    assert AppConfig().reading_view_mode == "continuous"
    AppConfig(reading_view_mode="paged").save(tmp_path)
    assert AppConfig.load(tmp_path).reading_view_mode == "paged"


def test_an_old_config_without_the_view_mode_loads(tmp_path: Path) -> None:
    old = {"theme": "dark", "font_size_pt": 20}
    (tmp_path / "config.json").write_text(json.dumps(old), encoding="utf-8")
    loaded = AppConfig.load(tmp_path)
    assert loaded.reading_view_mode == "continuous"
    assert loaded.theme == "dark"


@pytest.mark.parametrize("value", ["book", 3, None, ""])
def test_an_unknown_view_mode_falls_back_to_continuous(value: object) -> None:
    assert AppConfig.from_dict({"reading_view_mode": value}).reading_view_mode == (
        "continuous"
    )


def test_the_cache_keeps_page_starts_and_reads_old_files(tmp_path: Path) -> None:
    library = DocumentLibrary(tmp_path)
    raw = multi_page_raw()
    document = formatter().format_document(raw)
    source = tmp_path / "doc.txt"
    source.write_text("x", encoding="utf-8")
    library.store("k", source, CachedDocument(raw, document, "light"), 3, False)
    loaded = library.load("k")
    assert loaded is not None
    assert loaded.formatted.page_starts == document.page_starts
    path = tmp_path / "k.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["page_starts"]
    path.write_text(json.dumps(data), encoding="utf-8")
    old = library.load("k")
    assert old is not None
    assert old.formatted.page_starts == (0,)


def test_the_formatter_version_changed_with_the_cached_shape() -> None:
    assert int(FORMATTER_VERSION) >= 4


# ---- worker through the main window ----------------------------------------------


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    ocr: FakeOCR,
    config_dir: Path | None = None,
    config: AppConfig | None = None,
) -> MainWindow:
    load_reading_font()
    window = MainWindow(
        config or AppConfig(),
        ocr,  # type: ignore[arg-type]
        tts,
        library,
        config_dir=config_dir,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_a_scanned_pdf_keeps_one_page_per_scanned_page(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(multi_page_scan(tmp_path, PAGES)))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    assert window.reading_view.page_count == PAGES
    assert window.reading_view.page_bar.isVisible()


def test_a_text_sample_is_a_single_page_without_the_page_bar(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, DocumentLibrary(tmp_path / "cache"), FakeOCR())
    window.open_sample()
    assert window.reading_view.page_count == 1
    assert not window.reading_view.page_bar.isVisible()


def test_pages_survive_a_reopen_from_the_cache(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    window = make_window(qtbot, tts, library, FakeOCR())
    window.open_document(str(multi_page_scan(tmp_path, PAGES)))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    key = library.recents()[0].key
    window.go_back()
    window.open_recent(key)
    assert window.reading_view.page_count == PAGES


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_zoom_shortcuts_change_the_size_one_step_and_save_it(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    window = make_window(
        qtbot, tts, DocumentLibrary(tmp_path / "cache"), FakeOCR(), tmp_path / "config"
    )
    window.open_sample()
    start = window._config.font_size_pt
    view = window.reading_view
    press(view, "Ctrl++")
    assert window._config.font_size_pt == start + 1
    assert AppConfig.load(tmp_path / "config").font_size_pt == start + 1
    assert window.settings_view.config.font_size_pt == start + 1
    press(view, "Ctrl+-")
    press(view, "Ctrl+-")
    assert window._config.font_size_pt == start - 1
    press(view, "Ctrl+0")
    assert window._config.font_size_pt == AppConfig().font_size_pt
    assert view.editor.reading_font.pointSize() == AppConfig().font_size_pt


def test_zoom_stops_at_the_limits_of_the_settings(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    window = make_window(
        qtbot, tts, DocumentLibrary(tmp_path / "cache"), FakeOCR(), tmp_path / "config"
    )
    window.open_sample()
    for _ in range(FONT_SIZE_RANGE_PT[1]):
        window.reading_view.zoom_requested.emit(ZOOM_IN)
    assert window._config.font_size_pt == FONT_SIZE_RANGE_PT[1]
    for _ in range(FONT_SIZE_RANGE_PT[1] * 2):
        window.reading_view.zoom_requested.emit(ZOOM_OUT)
    assert window._config.font_size_pt == FONT_SIZE_RANGE_PT[0]
    window.reading_view.zoom_requested.emit(ZOOM_RESET)
    assert window._config.font_size_pt == AppConfig().font_size_pt


def test_zoom_keeps_the_pages_of_a_cached_document(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    window = make_window(qtbot, tts, library, FakeOCR(), tmp_path / "config")
    window.open_document(str(multi_page_scan(tmp_path, PAGES)))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    key = library.recents()[0].key
    window.reading_view.zoom_requested.emit(ZOOM_IN)
    window.go_back()
    window.open_recent(key)
    assert window.reading_view.page_count == PAGES


def test_the_view_mode_chosen_in_the_bar_is_saved_and_used_on_start(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    window = make_window(qtbot, tts, library, FakeOCR(), tmp_path / "config")
    window.open_document(str(multi_page_scan(tmp_path, PAGES)))
    wait_for_screen(qtbot, window, Screen.READING)
    wait_for_idle(qtbot, window)
    window.reading_view.paged_button.click()
    assert AppConfig.load(tmp_path / "config").reading_view_mode == "paged"
    window.settings_view.config_changed.emit(window.settings_view.config)
    assert AppConfig.load(tmp_path / "config").reading_view_mode == "paged"
    reopened = make_window(
        qtbot,
        tts,
        library,
        FakeOCR(),
        config=AppConfig.load(tmp_path / "config"),
    )
    assert reopened.reading_view.view_mode is ViewMode.PAGED


# ---- reading view ---------------------------------------------------------------


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource(word_delay_s=0.02)


@pytest.fixture
def speech(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=engines)
    yield controller
    controller.shutdown()


@pytest.fixture
def document() -> FormattedDocument:
    return formatter().format_document(multi_page_raw())


def make_view(
    qtbot: QtBot,
    speech: TTSController,
    document: FormattedDocument,
    mode: ViewMode = ViewMode.CONTINUOUS,
) -> ReadingView:
    view = ReadingView(speech, view_mode=mode)
    qtbot.addWidget(view)
    view.resize(1000, 600)
    view.show()
    qtbot.waitExposed(view)
    view.load_document(document)
    return view


def visible_blocks(view: ReadingView) -> int:
    block = view.editor.document().begin()
    count = 0
    while block.isValid():
        count += block.isVisible()
        block = block.next()
    return count


def click_word(view: ReadingView, qtbot: QtBot, index: int) -> None:
    token = view.token_map[index]
    cursor = QTextCursor(view.editor.document())
    cursor.setPosition(token.doc_start_pos)
    start = view.editor.cursorRect(cursor)
    cursor.setPosition(token.doc_end_pos)
    end = view.editor.cursorRect(cursor)
    assert start.y() == end.y(), "the word must not wrap"
    qtbot.mouseClick(
        view.editor.viewport(),
        Qt.MouseButton.LeftButton,
        pos=QPoint((start.x() + end.x()) // 2, start.center().y()),
    )


def test_the_page_bar_shows_the_page_count(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    assert view.page_bar.isVisible()
    assert view.page_count == PAGES
    assert (view.page_spin.value(), view.page_spin.maximum()) == (1, PAGES)
    assert "3" in view.page_total_label.text()
    assert not view.prev_page_button.isEnabled()
    assert view.next_page_button.isEnabled()
    assert view.state is PlaybackState.IDLE


def test_page_buttons_and_the_number_field_navigate_in_continuous_mode(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    view.next_page_button.click()
    assert view.current_page == 1
    assert view.page_spin.value() == 2
    assert view.editor.verticalScrollBar().value() > 0
    view.page_spin.setValue(3)
    assert view.current_page == 2
    assert not view.next_page_button.isEnabled()
    view.prev_page_button.click()
    assert view.current_page == 1
    top = view.editor.first_visible_position()
    assert page_index_at(view.page_starts, top) == 1


def test_scrolling_updates_the_page_indicator(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    bar = view.editor.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    assert view.current_page == PAGES - 1
    assert view.page_spin.value() == PAGES
    bar.setValue(0)
    assert view.current_page == 0
    view.editor.scroll_to_position(view.page_starts[1])
    bar.setValue(bar.value() + 10)
    assert view.current_page == 1


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_scrolling_by_hand_never_starts_the_voice(
    qtbot: QtBot,
    speech: TTSController,
    engines: EngineSource,
    document: FormattedDocument,
) -> None:
    view = make_view(qtbot, speech, document)
    view._move_start_to(5)
    bar = view.editor.verticalScrollBar()
    for value in (bar.maximum(), 0, bar.maximum() // 2):
        bar.setValue(value)
    press(view, Qt.Key.Key_PageDown)
    qtbot.wait(150)
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == 5
    assert not any(engine.said for engine in engines.created)


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_the_page_keys_and_chords_navigate(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    press(view, "Ctrl+End")
    assert view.current_page == PAGES - 1
    press(view, "Ctrl+Left")
    assert view.current_page == PAGES - 2
    press(view, "Ctrl+Right")
    assert view.current_page == PAGES - 1
    press(view, "Ctrl+Home")
    assert view.current_page == 0
    bar = view.editor.verticalScrollBar()
    press(view, Qt.Key.Key_PageDown)
    assert bar.value() == bar.pageStep()
    press(view, Qt.Key.Key_PageUp)
    assert bar.value() == 0


def test_the_tooltips_name_their_shortcuts(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    assert "Ctrl+Izquierda" in view.prev_page_button.toolTip()
    assert "Ctrl+Derecha" in view.next_page_button.toolTip()


def test_page_mode_shows_only_the_current_page(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    assert visible_blocks(view) == PARAGRAPHS_PER_PAGE
    view.next_page_button.click()
    assert view.current_page == 1
    assert visible_blocks(view) == PARAGRAPHS_PER_PAGE
    assert view.editor.verticalScrollBar().value() == 0
    plain = view.editor.toPlainText()
    assert plain == document.tts_script
    first = first_token_of(document, 1)
    assert (
        view.editor.document()
        .findBlock(view.token_map[first].doc_start_pos)
        .isVisible()
    )
    assert not view.editor.document().findBlock(0).isVisible()


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_page_down_at_the_end_of_a_page_turns_it(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    bar = view.editor.verticalScrollBar()
    while view.current_page == 0:
        press(view, Qt.Key.Key_PageDown)
        assert bar.value() <= bar.maximum()
    assert view.current_page == 1
    press(view, Qt.Key.Key_PageUp)
    assert view.current_page == 0
    assert bar.value() == bar.maximum()


def test_switching_the_mode_keeps_the_current_word(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    word = first_token_of(document, 1) + 7
    view._move_start_to(word)
    token = view.token_map[word]
    view.paged_button.click()
    assert view.view_mode is ViewMode.PAGED
    assert view.current_page == 1
    assert view.editor.highlighted_range() == (token.doc_start_pos, token.doc_end_pos)
    assert view.editor.cursorRect(view.editor.textCursor()).y() >= 0
    view.continuous_button.click()
    assert view.view_mode is ViewMode.CONTINUOUS
    assert view.current_page == 1
    assert visible_blocks(view) == PAGES * PARAGRAPHS_PER_PAGE
    rect = view.editor.cursorRect(view.editor.textCursor())
    assert 0 <= rect.y() <= view.editor.viewport().height()
    assert view.current_word_idx == word


def test_switching_the_mode_without_reading_keeps_the_page_on_screen(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    view.go_to_page(2)
    view.paged_button.click()
    assert view.current_page == 2
    view.continuous_button.click()
    assert view.current_page == 2


def test_the_chosen_mode_is_announced_only_by_the_buttons(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document)
    modes: list[str] = []
    view.view_mode_changed.connect(modes.append)
    view.set_view_mode(ViewMode.PAGED)
    assert modes == []
    assert view.paged_button.isChecked()
    view.continuous_button.click()
    assert modes == ["continuous"]


def test_the_page_turns_by_itself_when_the_voice_reaches_the_next_page(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    first_of_second = first_token_of(document, 1)
    view.toggle_play()
    view._set_state(PlaybackState.PLAYING)
    view._on_word_spoken(first_of_second - 1)
    assert view.current_page == 0
    view._on_word_spoken(first_of_second)
    assert view.current_page == 1
    assert view.page_spin.value() == 2
    assert view.editor.highlighted_range() == (
        view.token_map[first_of_second].doc_start_pos,
        view.token_map[first_of_second].doc_end_pos,
    )
    assert (
        view.editor.document()
        .findBlock(view.token_map[first_of_second].doc_start_pos)
        .isVisible()
    )


def test_the_voice_really_turns_the_page_in_page_mode(
    qtbot: QtBot,
    speech: TTSController,
    document: FormattedDocument,
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    view._move_start_to(first_token_of(document, 1) - 3)
    assert view.current_page == 0
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_page == 1, timeout=10000)
    view.toggle_play()


def test_a_click_in_page_mode_moves_the_start_point_to_that_word(
    qtbot: QtBot,
    speech: TTSController,
    engines: EngineSource,
    document: FormattedDocument,
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    view.go_to_page(2)
    target = first_token_of(document, 2) + 4
    click_word(view, qtbot, target)
    assert view.state is PlaybackState.PAUSED
    assert view.current_word_idx == target
    assert view.resume_index == target
    assert view.current_page == 2
    assert not any(engine.said for engine in engines.created)


def test_resume_position_on_a_later_page_works_in_both_modes(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    for mode in ViewMode:
        view = make_view(qtbot, speech, document, mode)
        target = first_token_of(document, 2) + 2
        view.load_document(document, resume_at=target)
        view.resume_continue_button.click()
        assert view.current_word_idx == target
        assert view.current_page == 2
        token = view.token_map[target]
        assert view.editor.highlighted_range() == (
            token.doc_start_pos,
            token.doc_end_pos,
        )


def test_a_single_page_document_keeps_the_view_as_before(
    qtbot: QtBot, speech: TTSController
) -> None:
    document = formatter().format_document("Una sola pagina con pocas palabras.")
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    assert not view.page_bar.isVisible()
    assert view.page_count == 1
    assert visible_blocks(view) == 1


def test_appearance_change_keeps_the_page_and_the_mode(
    qtbot: QtBot, speech: TTSController, document: FormattedDocument
) -> None:
    view = make_view(qtbot, speech, document, ViewMode.PAGED)
    view.go_to_page(1)
    view.apply_appearance(
        ThemeId.DARK, ReadingStyle(font_size_pt=20), 1.5, document.html_content
    )
    assert view.current_page == 1
    assert visible_blocks(view) == PARAGRAPHS_PER_PAGE
