"""My words: topics, filter plus search, deleting words, default topic from the folder."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtWidgets import QPushButton, QWidget
from pytestqt.qtbot import QtBot

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.glossary import (
    MAX_ENTRIES,
    GlossaryEntry,
    GlossaryStore,
    count_by_topic,
    filter_entries,
)
from clearread.services.groups import GroupStore
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId
from clearread.ui.views.words_view import WordsView


def word(text: str, explanation: str = "Algo.", topic: str = "") -> GlossaryEntry:
    return GlossaryEntry(text, explanation, "Doc", "2026-10-03", topic)


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    tmp_path: Path,
    glossary: GlossaryStore,
    topics: GroupStore,
    folders: GroupStore | None = None,
) -> MainWindow:
    load_reading_font()
    window = MainWindow(
        AppConfig(),
        object(),  # type: ignore[arg-type]
        tts,
        DocumentLibrary(tmp_path / "cache"),
        config_dir=tmp_path / "config",
        glossary=glossary,
        topics=topics,
        folders=folders,
    )
    qtbot.addWidget(window)
    window.resize(1100, 760)
    window.show()
    return window


def press(parent: QWidget, text: str) -> None:
    next(b for b in parent.findChildren(QPushButton) if b.text() == text).click()


# ---- store ---------------------------------------------------------------------------


def test_an_old_glossary_without_topics_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    old = [
        {
            "word": "célula",
            "explanation": "Unidad.",
            "document": "Bio",
            "added_on": "2026-10-03",
        }
    ]
    path.write_text(json.dumps(old), encoding="utf-8")
    [entry] = GlossaryStore(path).entries()
    assert (entry.word, entry.topic) == ("célula", "")


def test_topics_persist_and_a_repeated_word_keeps_its_topic(tmp_path: Path) -> None:
    path = tmp_path / "glossary.json"
    store = GlossaryStore(path)
    store.add(word("célula", "Primera.", topic="t1"))
    store.add(word("CÉLULA", "Segunda."))
    [entry] = GlossaryStore(path).entries()
    assert (entry.explanation, entry.topic) == ("Segunda.", "t1")
    store.set_topic("célula", "t2")
    assert GlossaryStore(path).entries()[0].topic == "t2"
    store.clear_topic("t2")
    assert GlossaryStore(path).entries()[0].topic == ""


def test_a_repeated_word_without_a_topic_takes_the_new_default() -> None:
    store = GlossaryStore()
    store.add(word("raíz"))
    store.add(word("raíz", topic="t9"))
    assert store.entries()[0].topic == "t9"


def test_the_cap_of_entries_is_kept() -> None:
    store = GlossaryStore()
    for number in range(MAX_ENTRIES + 5):
        store.add(word(f"palabra{number}"))
    assert len(store.entries()) == MAX_ENTRIES
    assert store.entries()[0].word == f"palabra{MAX_ENTRIES + 4}"


def test_filter_by_topic_combines_with_the_accent_insensitive_search() -> None:
    entries = [
        word("célula", "Unidad viva.", "t1"),
        word("cuadrado", "Figura.", "t2"),
        word("clorofila", "Pigmento verde.", ""),
    ]
    assert [e.word for e in filter_entries(entries, "*", "")] == [
        "célula",
        "cuadrado",
        "clorofila",
    ]
    assert [e.word for e in filter_entries(entries, "t1", "")] == ["célula"]
    assert [e.word for e in filter_entries(entries, "", "")] == ["clorofila"]
    assert [e.word for e in filter_entries(entries, "*", "CELULA")] == ["célula"]
    assert filter_entries(entries, "t2", "celula") == []
    assert count_by_topic(entries) == {"t1": 1, "t2": 1, "": 1}


# ---- words view ---------------------------------------------------------------------------


def make_view(
    qtbot: QtBot, topics: GroupStore, entries: list[GlossaryEntry]
) -> WordsView:
    load_reading_font()
    view = WordsView(THEMES[ThemeId.LIGHT], Language.ES)
    qtbot.addWidget(view)
    view.resize(1024, 700)
    view.show()
    view.set_entries(entries, topics.groups())
    return view


def test_the_chips_count_words_and_filter_the_cards_with_the_search(
    qtbot: QtBot,
) -> None:
    topics = GroupStore()
    maths = topics.create("Matemáticas")
    science = topics.create("Ciencias")
    entries = [
        word("célula", "Unidad viva.", science.id),
        word("cuadrado", "Figura.", maths.id),
        word("clorofila", "Pigmento.", ""),
    ]
    view = make_view(qtbot, topics, entries)
    chips = view.topic_filter.chips
    assert chips["*"].text() == "Todas (3)"
    assert chips[""].text() == "Sin tema (1)"
    assert chips[science.id].text() == "Ciencias (1)"
    assert len(view.cards) == 3

    chips[science.id].click()
    assert [c.entry.word for c in view.cards] == ["célula"]
    view.search_edit.setText("cuad")
    assert view.cards == []
    assert view.no_results_label.text() == tr("words.no_results", Language.ES)
    view.search_edit.setText("")
    chips[maths.id].click()
    assert [c.entry.word for c in view.cards] == ["cuadrado"]
    view.topic_filter.chips[""].click()
    assert [c.entry.word for c in view.cards] == ["clorofila"]


def test_an_empty_topic_says_so(qtbot: QtBot) -> None:
    topics = GroupStore()
    empty = topics.create("Historia")
    view = make_view(qtbot, topics, [word("célula")])
    view.topic_filter.chips[empty.id].click()
    assert view.cards == []
    assert view.no_results_label.isVisible()
    assert view.no_results_label.text() == tr("words.topic_empty", Language.ES)


def test_the_card_menu_lists_the_topics_and_asks_for_the_change(qtbot: QtBot) -> None:
    topics = GroupStore()
    maths = topics.create("Matemáticas")
    view = make_view(qtbot, topics, [word("cuadrado", topic=maths.id)])
    [card] = view.cards
    assert card.topic_button.text() == "Tema: Matemáticas"
    actions = card.topic_menu.actions()
    assert [a.text() for a in actions] == ["Sin tema", "Matemáticas"]
    assert [a.isChecked() for a in actions] == [False, True]
    with qtbot.waitSignal(view.topic_changed, timeout=2000) as changed:
        actions[0].trigger()
    assert changed.args == ["cuadrado", ""]


def test_a_word_of_a_missing_topic_shows_as_without_topic(qtbot: QtBot) -> None:
    view = make_view(qtbot, GroupStore(), [word("célula", topic="gone")])
    assert view.cards[0].topic_button.text() == "Tema: Sin tema"


# ---- window --------------------------------------------------------------------------------


def test_topics_can_be_created_renamed_and_deleted_without_losing_words(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    glossary = GlossaryStore(tmp_path / "glossary.json")
    topics = GroupStore(tmp_path / "topics.json")
    glossary.add(word("célula"))
    window = make_window(qtbot, tts, tmp_path, glossary, topics)
    window.open_words()
    view = window.words_view

    view.topic_filter.add_button.click()
    assert window.prompt_dialog is not None
    window.prompt_dialog.name_edit.setText("Ciencias")
    window.prompt_dialog.confirm_button.click()
    [topic] = GroupStore(tmp_path / "topics.json").groups()
    assert topic.name == "Ciencias"

    view.cards[0].topic_menu.actions()[1].trigger()
    assert GlossaryStore(tmp_path / "glossary.json").entries()[0].topic == topic.id
    assert view.cards[0].topic_button.text() == "Tema: Ciencias"

    window.rename_topic(topic.id)
    assert window.prompt_dialog is not None
    window.prompt_dialog.name_edit.setText("Biología")
    window.prompt_dialog.confirm_button.click()
    assert view.cards[0].topic_button.text() == "Tema: Biología"

    window.ask_delete_topic(topic.id)
    assert window.confirm_box is not None
    press(window.confirm_box, tr("topic.delete", Language.ES))
    assert topics.groups() == []
    saved = GlossaryStore(tmp_path / "glossary.json").entries()
    assert [(e.word, e.topic) for e in saved] == [("célula", "")]
    assert view.topic_filter.selected == "*" and len(view.cards) == 1


def test_deleting_a_word_asks_first_and_persists(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    glossary = GlossaryStore(tmp_path / "glossary.json")
    glossary.add(word("raíz"))
    glossary.add(word("célula"))
    window = make_window(qtbot, tts, tmp_path, glossary, GroupStore())
    window.open_words()
    window.words_view.cards[0].delete_button.click()
    assert window.confirm_box is not None
    press(window.confirm_box, tr("common.cancel", Language.ES))
    assert len(GlossaryStore(tmp_path / "glossary.json").entries()) == 2

    window.words_view.cards[0].delete_button.click()
    assert window.confirm_box is not None
    press(window.confirm_box, tr("words.delete", Language.ES))
    assert [e.word for e in glossary.entries()] == ["raíz"]
    assert [e.word for e in GlossaryStore(tmp_path / "glossary.json").entries()] == [
        "raíz"
    ]
    assert len(window.words_view.cards) == 1


def test_a_word_explained_in_a_folder_gets_the_topic_with_the_same_name(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    folders = GroupStore()
    topics = GroupStore()
    folder = folders.create("Ciencias")
    topic = topics.create("ciencias")
    window = make_window(qtbot, tts, tmp_path, GlossaryStore(), topics, folders)
    window.open_sample()
    assert window.screen_shown is Screen.READING
    window.move_document(window._reading_key or "", folder.id)

    window._on_word_explained("célula", "Una unidad viva.")
    assert window._glossary.entries()[0].topic == topic.id


def test_without_a_matching_topic_or_folder_the_word_has_no_topic(
    qtbot: QtBot, tts: TTSController, tmp_path: Path
) -> None:
    folders = GroupStore()
    folder = folders.create("Ciencias")
    topics = GroupStore()
    topics.create("Historia")
    window = make_window(qtbot, tts, tmp_path, GlossaryStore(), topics, folders)
    window.open_sample()
    window._on_word_explained("sol", "Una estrella.")
    window.move_document(window._reading_key or "", folder.id)
    window._on_word_explained("luna", "Satélite.")
    assert [e.topic for e in window._glossary.entries()] == ["", ""]
