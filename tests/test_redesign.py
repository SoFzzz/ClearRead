"""Redesign (Day 12): dashboard, sample, reading position, focus mode, My words, fonts."""

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fakes import EngineSource, FakeAIClient
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QFocusEvent,
    QFontMetricsF,
    QKeySequence,
    QShortcut,
    QShortcutEvent,
)
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.document_library import (
    CachedDocument,
    DocumentLibrary,
    RecentDocument,
)
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.services.reading_stats import ReadingStats, StatsStore
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.focus_ring import KeyboardFocusRing
from clearread.ui.fonts import READING_FONT_FILES, load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.ai_panel import PanelState
from clearread.ui.views.home_view import (
    ElidedLabel,
    HomeView,
    format_count,
    format_duration,
    local_today,
)
from clearread.ui.views.reading_view import PlaybackState, ReadingView

TIMEOUT_MS = 5000
LONG_NAME = (
    "Informe-de-biologia-celular-y-molecular-primer-parcial-2026-version-final.pdf"
)


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource(word_delay_s=0.0)


@pytest.fixture
def tts(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=engines)
    yield controller
    controller.shutdown()


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(tmp_path / "cache")


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
    client: FakeAIClient | None = None,
    glossary: GlossaryStore | None = None,
    stats: StatsStore | None = None,
) -> MainWindow:
    load_reading_font()
    window = MainWindow(
        AppConfig(ai_privacy_accepted=True),
        object(),  # type: ignore[arg-type]
        tts,
        library,
        config_dir=tmp_path / "config",
        ai_client=client,
        glossary=glossary,
        stats=stats,
    )
    qtbot.addWidget(window)
    window.resize(1100, 760)
    window.show()
    return window


def recent(name: str = "a.pdf", position: int = 0, total: int = 100) -> RecentDocument:
    return RecentDocument(
        key=name,
        name=name,
        path=name,
        opened_at="2026-10-07T10:00:00",
        pages=3,
        is_photo=False,
        position=position,
        total_words=total,
    )


# ---- library: reading position (READ-F01) --------------------------------------


def stored_library(library: DocumentLibrary, tmp_path: Path) -> str:
    source = tmp_path / "doc.txt"
    source.write_text("Una frase. Otra frase muy corta.", encoding="utf-8")
    formatter = TextFormatter(
        SpanishSyllabifier(), syllable_palette(THEMES[ThemeId.LIGHT])
    )
    formatted = formatter.format_document(source.read_text(encoding="utf-8"))
    cached = CachedDocument(source.read_text(encoding="utf-8"), formatted, "x")
    library.store("k1", source, cached, 1, False)
    return "k1"


def test_the_library_remembers_the_position_and_computes_progress(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    key = stored_library(library, tmp_path)
    entry = library.recent(key)
    assert entry is not None
    assert (entry.position, entry.total_words, entry.progress_percent) == (0, 6, 17)
    library.set_position(key, 3)
    entry = library.recent(key)
    assert entry is not None
    assert (entry.position, entry.progress_percent, entry.can_resume) == (3, 67, True)
    library.set_position(key, 5)
    entry = library.recent(key)
    assert entry is not None
    assert (entry.progress_percent, entry.can_resume) == (100, False)


def test_a_stored_document_keeps_its_position_when_it_is_stored_again(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    key = stored_library(library, tmp_path)
    library.set_position(key, 2)
    stored_library(library, tmp_path)
    entry = library.recent(key)
    assert entry is not None and entry.position == 2


def test_an_index_written_before_positions_existed_still_loads(tmp_path: Path) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    old = {
        "key": "k",
        "name": "old.pdf",
        "path": "old.pdf",
        "opened_at": "2026-10-01T09:00:00",
        "pages": 1,
        "is_photo": False,
    }
    (tmp_path / "cache" / "k.json").write_text("{}", encoding="utf-8")
    (tmp_path / "cache" / "recents.json").write_text(
        json.dumps([old]), encoding="utf-8"
    )
    [entry] = library.recents()
    assert (entry.position, entry.total_words, entry.progress_percent) == (0, 0, 0)


# ---- stores ---------------------------------------------------------------------


def test_the_glossary_adds_replaces_searches_and_deletes(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    store = GlossaryStore(path)
    store.add(
        GlossaryEntry(
            "Célula", "La parte más pequeña de un ser vivo.", "Bio", "2026-10-01"
        )
    )
    store.add(
        GlossaryEntry(
            "clorofila", "El pigmento verde de las hojas.", "Bio", "2026-10-02"
        )
    )
    store.add(GlossaryEntry("célula", "Una unidad muy pequeña.", "Bio 2", "2026-10-03"))
    assert [e.word for e in store.entries()] == ["célula", "clorofila"]
    assert store.entries()[0].document == "Bio 2"
    assert [e.word for e in store.search("verde")] == ["clorofila"]
    assert [e.word for e in store.search("CELULA")] == ["célula"]
    assert [e.word for e in store.search("  CLORO ")] == ["clorofila"]
    assert len(store.search("")) == 2
    assert GlossaryStore(path).entries() == store.entries()
    store.remove("CÉLULA")
    assert [e.word for e in GlossaryStore(path).entries()] == ["clorofila"]


@pytest.mark.parametrize("content", ["", "{not json", '{"a": 1}', "[1, 2]"])
def test_a_damaged_glossary_file_means_an_empty_glossary(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "glossary.json"
    path.write_text(content, encoding="utf-8")
    assert GlossaryStore(path).entries() == []


def test_the_stats_add_up_persist_and_ignore_nothing_readings(tmp_path: Path) -> None:
    path = tmp_path / "stats.json"
    store = StatsStore(path)
    store.add(120, 95.4)
    store.add(0, 0.2)
    store.add(30, 65)
    assert store.stats == ReadingStats(words_read=150, seconds_read=160)
    assert StatsStore(path).stats == store.stats
    path.write_text("not json", encoding="utf-8")
    assert StatsStore(path).stats == ReadingStats()


# ---- dashboard (HOME-F02) ---------------------------------------------------------


def make_home(qtbot: QtBot, width: int = 1024) -> HomeView:
    load_reading_font()
    home = HomeView(THEMES[ThemeId.LIGHT], Language.ES)
    qtbot.addWidget(home)
    home.resize(width, 700)
    home.show()
    QApplication.processEvents()
    return home


def test_first_time_the_home_is_a_friendly_empty_state(qtbot: QtBot) -> None:
    home = make_home(qtbot)
    assert home.drop_title.text() == tr("home.empty.title", Language.ES)
    assert home.drop_hint.text() == tr("home.empty.body", Language.ES)
    assert home.continue_card.isHidden()
    assert home.stats_box.isHidden()
    assert home.recent_heading.isHidden()
    assert home.sample_button.isVisible() and home.choose_button.isVisible()


def test_with_documents_the_home_shows_continue_stats_and_cards(qtbot: QtBot) -> None:
    home = make_home(qtbot)
    home.set_stats(ReadingStats(words_read=12345, seconds_read=3 * 3600 + 25 * 60))
    home.set_recents(
        [recent("ultimo.pdf", position=49, total=100), recent("otro.pdf")],
        date(2026, 10, 7),
    )
    assert home.continue_card.isVisible()
    assert home.continue_name.full_text == "ultimo.pdf"
    assert home.continue_bar.value() == 50
    assert home.continue_progress.text() == tr("home.progress", Language.ES, percent=50)
    assert home.stat_words.value_label.text() == "12.345"
    assert home.stat_time.value_label.text() == "3 h 25 min"
    assert home.stat_documents.value_label.text() == "2"
    assert home.drop_title.text() == tr("home.drop_title", Language.ES)
    assert len(home.recent_item_widgets()) == 2


def test_continue_and_sample_buttons_emit_their_requests(qtbot: QtBot) -> None:
    home = make_home(qtbot)
    home.set_recents([recent("ultimo.pdf")], date(2026, 10, 7))
    with qtbot.waitSignal(home.recent_open_requested, timeout=TIMEOUT_MS) as opened:
        home.continue_button.click()
    assert opened.args == ["ultimo.pdf"]
    with qtbot.waitSignal(home.sample_requested, timeout=TIMEOUT_MS):
        home.sample_button.click()


def test_number_and_time_formats_in_both_languages() -> None:
    assert format_count(1234567, Language.ES) == "1.234.567"
    assert format_count(1234567, Language.EN) == "1,234,567"
    assert format_duration(0, Language.ES) == "0 min"
    assert format_duration(59 * 60 + 59, Language.EN) == "59 min"
    assert format_duration(3600, Language.EN) == "1 h 0 min"


@pytest.mark.parametrize("width", [1024, 1100, 1400])
def test_home_has_no_horizontal_scroll_and_nothing_is_cut(
    qtbot: QtBot, width: int
) -> None:
    home = make_home(qtbot, width)
    home.set_recents(
        [recent(LONG_NAME, 10), recent("b.pdf"), recent(LONG_NAME + "x", 40)],
        date(2026, 10, 7),
    )
    QApplication.processEvents()
    scroll = home.scroll
    assert isinstance(scroll, QScrollArea)
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.widget().width() <= scroll.viewport().width()
    for item in home.recent_item_widgets():
        right = item.mapTo(scroll.widget(), item.rect().bottomRight()).x()
        assert right <= scroll.widget().width()
        button = item.open_button
        assert button.width() >= button.sizeHint().width()
        assert button.isVisible()


def test_long_names_end_in_an_ellipsis_and_keep_the_full_name_in_the_tooltip(
    qtbot: QtBot,
) -> None:
    home = make_home(qtbot)
    home.set_recents([recent(LONG_NAME)], date(2026, 10, 7))
    QApplication.processEvents()
    label = home.recent_item_widgets()[0].name_label
    assert isinstance(label, ElidedLabel)
    assert label.text().endswith("…") and label.text() != LONG_NAME
    assert label.toolTip() == LONG_NAME
    assert label.accessibleName() == LONG_NAME
    assert LONG_NAME.startswith(label.text()[:-1])
    assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width()


def test_short_names_are_not_elided(qtbot: QtBot) -> None:
    home = make_home(qtbot)
    home.set_recents([recent("corto.pdf")], date(2026, 10, 7))
    QApplication.processEvents()
    assert home.recent_item_widgets()[0].name_label.text() == "corto.pdf"


# ---- the bundled example (HOME-F03) --------------------------------------------------


def test_the_sample_opens_without_ocr_and_goes_to_the_recents(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.home_view.sample_button.click()
    assert window.screen_shown is Screen.READING
    assert window.title_label.text() == tr("home.sample_title", Language.ES)
    assert len(window.reading_view.token_map) > 100
    assert "fotosíntesis" in window.reading_view.editor.toPlainText()
    [entry] = library.recents()
    assert entry.name == tr("home.sample_title", Language.ES)
    window.go_back()
    assert window.home_view.continue_name.full_text == entry.name


def test_the_sample_text_is_spanish_and_free_of_personal_data() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "resources" / "samples" / "ejemplo_es.txt"
    ).read_text(encoding="utf-8")
    assert 100 < len(text.split()) < 400
    assert "@" not in text and "http" not in text


# ---- remembering the position (READ-F01) -----------------------------------------------


def test_reopening_offers_to_continue_from_where_it_was_left(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    reading = window.reading_view
    assert reading.resume_banner.isHidden()
    reading._set_state(PlaybackState.PLAYING)
    reading._on_word_spoken(42)
    window.go_back()
    key = library.recents()[0].key
    assert library.recents()[0].position == 42

    window.open_recent(key)
    assert reading.resume_banner.isVisible()
    assert tr("reading.resume_title", Language.ES) == reading.resume_title.text()
    assert "43" in reading.resume_detail.text()
    reading.resume_continue_button.click()
    assert reading.resume_banner.isHidden()
    assert reading.state is PlaybackState.PAUSED
    assert reading.current_word_idx == 42
    assert reading.editor.highlighted_range() is not None


def test_start_over_dismisses_the_offer_and_forgets_the_place(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    window.reading_view._set_state(PlaybackState.PLAYING)
    window.reading_view._on_word_spoken(30)
    window.go_back()
    assert library.recents()[0].position == 30
    window.open_recent(library.recents()[0].key)
    reading = window.reading_view
    reading.resume_restart_button.click()
    assert reading.resume_banner.isHidden()
    assert reading.state is PlaybackState.IDLE
    window.go_back()
    assert library.recents()[0].position == 0


def test_a_finished_document_is_not_offered_again(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    reading = window.reading_view
    reading._set_state(PlaybackState.PLAYING)
    reading._on_playback_ended()
    window.go_back()
    assert library.recents()[0].progress_percent == 100
    window.open_recent(library.recents()[0].key)
    assert window.reading_view.resume_banner.isHidden()


def test_the_position_is_saved_when_the_window_closes(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    window.reading_view._set_state(PlaybackState.PLAYING)
    window.reading_view._on_word_spoken(25)
    window.close()
    assert library.recents()[0].position == 25


# ---- statistics shown on the home -------------------------------------------------------


def test_reading_aloud_feeds_the_statistics_on_the_home(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    stats = StatsStore(tmp_path / "stats.json")
    window = make_window(qtbot, tts, library, tmp_path, stats=stats)
    window.open_sample()
    reading = window.reading_view
    now = [100.0]
    reading._clock = lambda: now[0]
    reading._set_state(PlaybackState.PLAYING)
    for index in range(5):
        reading._on_word_spoken(index)
    now[0] = 190.0
    reading.pause_reading()
    assert stats.stats == ReadingStats(words_read=5, seconds_read=90)
    window.go_back()
    assert window.home_view.stat_words.value_label.text() == "5"
    assert window.home_view.stat_time.value_label.text() == "1 min"
    assert window.home_view.stat_documents.value_label.text() == "1"
    assert StatsStore(tmp_path / "stats.json").stats == stats.stats


def test_the_answer_of_the_assistant_is_not_counted_as_reading(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    stats = StatsStore()
    window = make_window(qtbot, tts, library, tmp_path, stats=stats)
    window.open_sample()
    window.reading_view.speak_aside("Una respuesta del asistente.")
    window.reading_view._on_word_spoken(3)
    window.reading_view.stop_aside()
    assert stats.stats == ReadingStats()


# ---- focus mode (READ-F02) ---------------------------------------------------------------


def make_reader(
    qtbot: QtBot, tts: TTSController, theme: ThemeId = ThemeId.LIGHT
) -> ReadingView:
    load_reading_font()
    view = ReadingView(tts, theme)
    qtbot.addWidget(view)
    text = "\n\n".join("palabra " * 60 for _ in range(4))
    formatter = TextFormatter(SpanishSyllabifier(), syllable_palette(THEMES[theme]))
    view.load_document(formatter.format_document(text))
    view.resize(900, 700)
    view.show()
    QApplication.processEvents()
    return view


def selection_ranges(view: ReadingView) -> list[tuple[int, int, str]]:
    return [
        (
            s.cursor.selectionStart(),
            s.cursor.selectionEnd(),
            s.format.foreground().color().name().upper(),
        )
        for s in view.editor.extraSelections()
    ]


def test_focus_mode_dims_everything_but_the_active_line(
    qtbot: QtBot, tts: TTSController
) -> None:
    view = make_reader(qtbot, tts)
    view._on_word_spoken(100)
    token = view.token_map[100]
    plain_length = len(view.editor.toPlainText())
    before = view.editor.extraSelections()
    assert len(before) == 2  # ruler and word only

    view.set_focus_mode(True)
    ranges = selection_ranges(view)
    dim = THEMES[ThemeId.LIGHT].dim_text.upper()
    dimmed = [(a, b) for a, b, colour in ranges if colour == dim]
    assert len(dimmed) == 2
    (first_start, line_start), (line_end, last_end) = dimmed
    assert first_start == 0 and last_end == plain_length
    assert line_start <= token.doc_start_pos and token.doc_end_pos <= line_end
    assert 0 < line_end - line_start < 80  # a visual line, not the whole paragraph
    assert ranges[-1][:2] == (token.doc_start_pos, token.doc_end_pos)  # word stays last
    assert view.editor.highlighted_range() == (token.doc_start_pos, token.doc_end_pos)

    view.set_focus_mode(False)
    assert len(view.editor.extraSelections()) == 2


def test_focus_mode_follows_the_voice_from_line_to_line(
    qtbot: QtBot, tts: TTSController
) -> None:
    view = make_reader(qtbot, tts)
    view.set_focus_mode(True)
    view._on_word_spoken(3)
    dim = THEMES[ThemeId.LIGHT].dim_text.upper()

    def dimmed() -> list[tuple[int, int]]:
        return [(a, b) for a, b, colour in selection_ranges(view) if colour == dim]

    view._on_word_spoken(3)
    first = dimmed()
    view._on_word_spoken(200)
    second = dimmed()
    assert first != second
    assert second[0][1] <= view.token_map[200].doc_start_pos


def press_shortcut(view: ReadingView, key: Qt.Key) -> None:
    """Send the event the shortcut map sends once the window is active (test_reading_view)."""
    sequence = QKeySequence(key)
    shortcut = next(s for s in view.findChildren(QShortcut) if s.key() == sequence)
    assert shortcut.context() is Qt.ShortcutContext.WidgetWithChildrenShortcut
    QApplication.sendEvent(shortcut, QShortcutEvent(sequence, shortcut.id()))


@pytest.mark.filterwarnings("ignore:Function.*QShortcut.id:DeprecationWarning")
def test_focus_mode_has_its_toggle_button_and_the_f_shortcut(
    qtbot: QtBot, tts: TTSController
) -> None:
    view = make_reader(qtbot, tts)
    assert view.focus_button.isCheckable() and not view.focus_button.isChecked()
    assert view.focus_button.text() == tr("reading.focus", Language.ES)
    assert "(F)" in view.focus_button.toolTip()
    view.focus_button.click()
    assert view.editor.focus_mode
    press_shortcut(view, Qt.Key.Key_F)
    assert not view.editor.focus_mode and not view.focus_button.isChecked()
    press_shortcut(view, Qt.Key.Key_F)
    assert view.editor.focus_mode


def test_focus_mode_survives_a_theme_change_and_dims_with_the_new_colour(
    qtbot: QtBot, tts: TTSController
) -> None:
    view = make_reader(qtbot, tts)
    view.set_focus_mode(True)
    view._on_word_spoken(80)
    dark = THEMES[ThemeId.DARK]
    view.editor.apply_theme(dark)
    colours = {colour for _, _, colour in selection_ranges(view)}
    assert dark.dim_text.upper() in colours


def test_without_a_word_being_read_nothing_is_dimmed(
    qtbot: QtBot, tts: TTSController
) -> None:
    view = make_reader(qtbot, tts)
    view.set_focus_mode(True)
    assert view.editor.extraSelections() == []


# ---- keyboard-only focus ring ---------------------------------------------------------------


def focus_in(widget: QPushButton, reason: Qt.FocusReason) -> None:
    QApplication.sendEvent(widget, QFocusEvent(QEvent.Type.FocusIn, reason))


def test_the_focus_ring_shows_for_tab_and_never_for_a_mouse_click(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    button = window.home_view.sample_button
    focus_in(button, Qt.FocusReason.TabFocusReason)
    assert button.property("keyFocus") is True
    focus_in(button, Qt.FocusReason.MouseFocusReason)
    assert button.property("keyFocus") is False
    focus_in(button, Qt.FocusReason.BacktabFocusReason)
    assert button.property("keyFocus") is True
    leave = QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.TabFocusReason)
    QApplication.sendEvent(button, leave)
    assert button.property("keyFocus") is False


def test_shortcut_and_other_reasons_do_not_show_the_ring(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    button = window.home_view.choose_button
    for reason in (Qt.FocusReason.ShortcutFocusReason, Qt.FocusReason.OtherFocusReason):
        focus_in(button, reason)
        assert not button.property("keyFocus")


def test_the_filter_is_removed_when_the_window_closes(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    assert isinstance(window._focus_ring, KeyboardFocusRing)
    window.close()
    probe = QPushButton()
    qtbot.addWidget(probe)
    focus_in(probe, Qt.FocusReason.TabFocusReason)
    assert not probe.property("keyFocus")


# ---- My words (AI-F05) ------------------------------------------------------------------------


def test_an_explained_word_is_saved_and_listed_in_my_words(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    client = FakeAIClient(text="Es una parte muy pequeña de la planta.")
    store = GlossaryStore(tmp_path / "glossary.json")
    window = make_window(qtbot, tts, library, tmp_path, client, store)
    window.open_sample()
    window.reading_view.explain_at(
        window.reading_view.editor.toPlainText().index("cloroplastos")
    )
    qtbot.waitUntil(
        lambda: window.reading_view.ai_panel.state is PanelState.ANSWER,
        timeout=TIMEOUT_MS,
    )
    assert window.reading_view.ai_panel.saved_label.isVisible()
    [entry] = store.entries()
    assert entry.word == "cloroplastos"
    assert entry.explanation == "Es una parte muy pequeña de la planta."
    assert entry.document == tr("home.sample_title", Language.ES)
    assert entry.added_on == local_today().isoformat()

    window.open_words()
    assert window.screen_shown is Screen.WORDS
    [card] = window.words_view.cards
    assert card.entry.word == "cloroplastos"
    assert window.title_label.text() == tr("words.title", Language.ES)


def test_simplified_paragraphs_are_not_saved_and_nothing_calls_the_assistant_again(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    client = FakeAIClient()
    store = GlossaryStore()
    window = make_window(qtbot, tts, library, tmp_path, client, store)
    window.open_sample()
    window.reading_view.simplify_at(5)
    qtbot.waitUntil(
        lambda: window.reading_view.ai_panel.state is PanelState.ANSWER,
        timeout=TIMEOUT_MS,
    )
    assert store.entries() == []
    assert window.reading_view.ai_panel.saved_label.isHidden()
    window.open_words()
    window.words_view.listen_requested.emit("x")
    window.go_back()
    assert len(client.calls) == 1


def entries() -> list[GlossaryEntry]:
    return [
        GlossaryEntry(
            "célula", "La parte más pequeña de un ser vivo.", "Biología", "2026-10-01"
        ),
        GlossaryEntry(
            "clorofila", "El pigmento verde de las hojas.", "Biología", "2026-10-02"
        ),
        GlossaryEntry(
            "raíz", "La parte de la planta que toma el agua.", "Plantas", "2026-10-03"
        ),
    ]


def test_my_words_is_reachable_from_home_and_reading_and_goes_back_to_where_it_came_from(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    assert window.words_button.isVisible()
    window.words_button.click()
    assert window.screen_shown is Screen.WORDS
    window.go_back()
    assert window.screen_shown is Screen.HOME
    window.open_sample()
    assert window.words_button.isVisible()
    window.words_button.click()
    window.go_back()
    assert window.screen_shown is Screen.READING


def test_my_words_empty_state_search_listen_and_delete(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
    engines: EngineSource,
) -> None:
    store = GlossaryStore(tmp_path / "glossary.json")
    window = make_window(qtbot, tts, library, tmp_path, glossary=store)
    window.open_words()
    view = window.words_view
    assert view.empty_box.isVisible() and view.cards == []
    assert view.empty_title.text() == tr("words.empty_title", Language.ES)
    for entry in reversed(entries()):
        store.add(entry)
    window.go_back()
    window.open_words()
    assert view.empty_box.isHidden() and len(view.cards) == 3
    assert view.count_label.text() == tr("words.count_other", Language.ES, count=3)

    view.search_edit.setText("verde")
    assert [c.entry.word for c in view.cards] == ["clorofila"]
    view.search_edit.setText("CELU")
    assert [c.entry.word for c in view.cards] == ["célula"]
    view.search_edit.setText("zzz")
    assert view.cards == [] and view.no_results_label.isVisible()
    view.search_edit.setText("")

    assert [c.entry.word for c in view.cards] == ["célula", "clorofila", "raíz"]
    first = view.cards[0]
    assert first.listen_button.accessibleName() == tr(
        "words.listen_named", Language.ES, word="célula"
    )
    first.listen_button.click()
    qtbot.waitUntil(
        lambda: any(
            "célula. La parte más pequeña" in said
            for engine in engines.created
            for said in engine.said
        ),
        timeout=TIMEOUT_MS,
    )
    first.delete_button.click()
    assert [c.entry.word for c in view.cards] == ["clorofila", "raíz"]
    saved = GlossaryStore(tmp_path / "glossary.json").entries()
    assert [e.word for e in saved] == ["clorofila", "raíz"]


def test_listening_to_a_saved_word_does_not_move_the_document(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GlossaryStore()
    for entry in entries():
        store.add(entry)
    window = make_window(qtbot, tts, library, tmp_path, glossary=store)
    window.open_sample()
    reading = window.reading_view
    reading._on_word_spoken(7)
    window.open_words()
    window.words_view.cards[0].listen_button.click()
    qtbot.wait(150)
    assert reading.current_word_idx == 7
    assert reading.resume_index == 7


# ---- fonts and settings -------------------------------------------------------------------------


@pytest.mark.parametrize("family", list(READING_FONT_FILES))
def test_each_reading_font_loads_and_covers_spanish(qtbot: QtBot, family: str) -> None:
    from PySide6.QtGui import QFont, QFontDatabase

    load_reading_font()
    assert family in QFontDatabase.families()
    metrics = QFontMetricsF(QFont(family, 18))
    assert all(metrics.inFontUcs4(ord(c)) for c in "ñÑáéíóúü¿¡«»—“”")


def test_settings_offers_the_three_fonts_and_two_themes_and_no_advanced_section(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    view = window.settings_view
    assert [view.font_combo.itemData(i) for i in range(view.font_combo.count())] == [
        "Lexend",
        "Atkinson Hyperlegible",
        "OpenDyslexic",
    ]
    assert view.font_combo.currentData() == "Lexend"
    assert set(view.theme_buttons) == {"light", "dark"}
    assert not hasattr(view, "url_edit") and not hasattr(view, "advanced_toggle")
    defaults = (
        view.sliders["font_size_pt"].value(),
        view.sliders["line_spacing"].value(),
        view.sliders["letter_spacing_em"].value(),
        view.sliders["word_spacing_em"].value(),
    )
    assert defaults == (18, 15, 12, 16)


def test_choosing_a_font_changes_the_open_document_and_keeps_the_word(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    reading = window.reading_view
    reading._set_state(PlaybackState.PLAYING)
    reading._on_word_spoken(4)
    window.open_settings()
    view = window.settings_view
    view.font_combo.setCurrentIndex(view.font_combo.findData("Atkinson Hyperlegible"))
    assert reading.editor.reading_font.family() == "Atkinson Hyperlegible"
    assert "Atkinson Hyperlegible" in reading.editor.toHtml()
    assert reading.editor.highlighted_range() is not None


def test_the_backend_address_still_lives_in_the_config_but_not_in_the_interface(
    tmp_path: Path,
) -> None:
    config = AppConfig(backend_url="https://example.test/api")
    config.save(tmp_path)
    assert AppConfig.load(tmp_path).backend_url == "https://example.test/api"
