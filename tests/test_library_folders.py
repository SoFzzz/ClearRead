"""Library: folders, moving and removing documents, entries that survive a version change."""

import json
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea, QWidget
from pytestqt.qtbot import QtBot
from samples.make_samples import SAMPLES_DIR

from clearread.core.config import AppConfig
from clearread.services.document_library import (
    CachedDocument,
    DocumentLibrary,
    RecentDocument,
    doc_id_of,
)
from clearread.services.groups import GroupStore
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FORMATTER_VERSION,
    SyllablePalette,
    TextFormatter,
)
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId
from clearread.ui.views.home_view import HomeView
from clearread.workers.ocr_worker import ProcessingErrorKind

DIGITAL = SAMPLES_DIR / "sample_page_digital.pdf"
TIMEOUT_MS = 60000
TEXT = "El niño leyó una canción.\n\nSegundo párrafo."
LONG_NAME = "Informe-de-biologia-celular-y-molecular-primer-parcial-2026-final.pdf"


def cached() -> CachedDocument:
    formatter = TextFormatter(SpanishSyllabifier(), SyllablePalette("#111", "#222"))
    return CachedDocument(TEXT, formatter.format_document(TEXT), "light")


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(tmp_path / "cache")


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
    folders: GroupStore | None = None,
) -> MainWindow:
    load_reading_font()
    window = MainWindow(
        AppConfig(),
        object(),  # type: ignore[arg-type]  # a digital PDF needs no OCR
        tts,
        library,
        config_dir=tmp_path / "config",
        folders=folders,
    )
    qtbot.addWidget(window)
    window.resize(1100, 760)
    window.show()
    return window


def press(parent: QWidget, text: str) -> None:
    button = next(b for b in parent.findChildren(QPushButton) if b.text() == text)
    button.click()


def wait_for_reading(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: window.screen_shown is Screen.READING, timeout=TIMEOUT_MS)
    qtbot.waitUntil(lambda: not window._retired_workers, timeout=TIMEOUT_MS)


def copy_of_digital(tmp_path: Path, name: str = "mates.pdf") -> Path:
    target = tmp_path / name
    shutil.copyfile(DIGITAL, target)
    return target


def entry(name: str, folder_id: str = "", key: str | None = None) -> RecentDocument:
    return RecentDocument(
        key=key or name,
        name=name,
        path=name,
        opened_at="2026-10-07T10:00:00",
        pages=2,
        is_photo=False,
        position=0,
        total_words=100,
        folder_id=folder_id,
    )


# ---- service: folders inside the index ---------------------------------------------


def test_a_document_keeps_its_folder_and_it_persists(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    library.store("a", tmp_path / "a.pdf", cached(), 1, False)
    assert library.recent("a").folder_id == ""  # type: ignore[union-attr]
    library.set_folder("a", "f1")
    assert DocumentLibrary(tmp_path / "cache").recent("a").folder_id == "f1"  # type: ignore[union-attr]


def test_a_new_document_goes_to_the_given_folder_but_an_old_one_keeps_its_own(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    library.store("a", tmp_path / "a.pdf", cached(), 1, False, folder_id="f1")
    library.store("a", tmp_path / "a.pdf", cached(), 1, False, folder_id="f2")
    assert library.recent("a").folder_id == "f1"  # type: ignore[union-attr]


def test_clearing_a_folder_keeps_every_document(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    for key, folder in (("a", "f1"), ("b", "f1"), ("c", "f2")):
        library.store(
            key, tmp_path / f"{key}.pdf", cached(), 1, False, folder_id=folder
        )
    library.clear_folder("f1")
    folders = {r.key: r.folder_id for r in library.recents()}
    assert folders == {"a": "", "b": "", "c": "f2"}
    assert library.has("a") and library.has("b")


def test_an_index_without_folder_fields_still_loads(tmp_path: Path) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    old = {
        "key": "k",
        "name": "old.pdf",
        "path": "old.pdf",
        "opened_at": "2026-10-01T09:00:00",
        "pages": 1,
        "is_photo": False,
        "position": 4,
        "total_words": 10,
        "field_from_the_future": True,
    }
    (library._root / "recents.json").write_text(json.dumps([old]), encoding="utf-8")
    [loaded] = library.recents()
    assert (loaded.name, loaded.position, loaded.folder_id) == ("old.pdf", 4, "")


def test_an_entry_without_cache_stays_in_the_library_and_asks_for_processing(
    tmp_path: Path,
) -> None:
    library = DocumentLibrary(tmp_path / "cache")
    library.store("a", tmp_path / "a.pdf", cached(), 1, False)
    library._cache_path("a").unlink()
    assert [r.key for r in library.recents()] == ["a"]
    assert library.needs_processing("a")


def test_a_cache_from_an_older_formatter_is_listed_but_needs_processing(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    old_key = "abc-f1"
    library.store(old_key, tmp_path / "a.pdf", cached(), 1, False)
    assert library.has(old_key) and library.needs_processing(old_key)
    current = f"abc-f{FORMATTER_VERSION}"
    assert library.needs_processing(current)  # the same document, found by its id
    library.store(current, tmp_path / "a.pdf", cached(), 1, False)
    assert not library.needs_processing(current)


def test_processing_again_under_a_new_version_keeps_folder_and_replaces_the_old_cache(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    library.store("abc-f1", tmp_path / "a.pdf", cached(), 1, False, folder_id="f1")
    library.set_position("abc-f1", 3)
    current = f"abc-f{FORMATTER_VERSION}"
    library.store(current, tmp_path / "moved" / "a.pdf", cached(), 1, False)
    [only] = library.recents()
    assert (only.key, only.folder_id, only.position) == (current, "f1", 3)
    assert only.path.endswith("a.pdf") and "moved" in only.path
    assert not library.has("abc-f1")
    assert doc_id_of(current) == "abc" == only.doc_id


def test_removing_deletes_the_cache_but_never_the_original(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    original = tmp_path / "original.pdf"
    original.write_bytes(b"data")
    library.store("a", original, cached(), 1, False)
    library.remove("a")
    assert library.recents() == [] and not library.has("a")
    assert original.read_bytes() == b"data"


# ---- window: folder management -------------------------------------------------------


def add_documents(library: DocumentLibrary, tmp_path: Path, *names: str) -> None:
    for name in names:
        library.store(name, tmp_path / name, cached(), 1, False)


def test_create_rename_and_delete_a_folder_keeping_its_documents(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    add_documents(library, tmp_path, "a.pdf", "b.pdf")
    store = GroupStore(tmp_path / "folders.json")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view

    home.folder_filter.add_button.click()
    dialog = window.prompt_dialog
    assert dialog is not None
    dialog.name_edit.setText("Matemáticas")
    dialog.confirm_button.click()
    [folder] = store.groups()
    assert folder.name == "Matemáticas"
    assert GroupStore(tmp_path / "folders.json").groups() == [folder]
    assert folder.id in home.folder_filter.chips

    window.move_document("a.pdf", folder.id)
    assert library.recent("a.pdf").folder_id == folder.id  # type: ignore[union-attr]

    window.rename_folder(folder.id)
    assert window.prompt_dialog is not None
    window.prompt_dialog.name_edit.setText("Mates")
    window.prompt_dialog.confirm_button.click()
    assert store.get(folder.id).name == "Mates"  # type: ignore[union-attr]

    window.ask_delete_folder(folder.id)
    assert window.confirm_box is not None
    press(window.confirm_box, tr("folder.delete", Language.ES))
    assert store.groups() == []
    assert {r.name: r.folder_id for r in library.recents()} == {
        "a.pdf": "",
        "b.pdf": "",
    }
    assert window.home_view.folder_filter.selected == "*"
    assert len(home.visible_items) == 2


def test_a_folder_name_that_is_empty_or_repeated_keeps_the_dialog_open_with_a_message(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    add_documents(library, tmp_path, "a.pdf")
    store = GroupStore()
    store.create("Ciencias")
    window = make_window(qtbot, tts, library, tmp_path, store)
    window.create_folder()
    dialog = window.prompt_dialog
    assert dialog is not None
    dialog.name_edit.setText("   ")
    dialog.confirm_button.click()
    assert dialog.problem_label.text() == tr("group.error.empty", Language.ES)
    dialog.name_edit.setText("ciencias")
    dialog.confirm_button.click()
    assert dialog.problem_label.text() == tr("group.error.duplicate", Language.ES)
    assert dialog.isVisible() and len(store.groups()) == 1
    dialog.reject()
    assert window.prompt_dialog is None


def test_cancelling_the_delete_questions_keeps_everything(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    add_documents(library, tmp_path, "a.pdf")
    store = GroupStore()
    folder = store.create("Ciencias")
    window = make_window(qtbot, tts, library, tmp_path, store)
    window.ask_delete_folder(folder.id)
    assert window.confirm_box is not None
    press(window.confirm_box, tr("common.cancel", Language.ES))
    window.ask_remove_document("a.pdf")
    assert window.confirm_box is not None
    press(window.confirm_box, tr("common.cancel", Language.ES))
    assert store.get(folder.id) is not None
    assert library.has("a.pdf")


def test_removing_a_document_asks_first_and_leaves_the_original_file(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    original = copy_of_digital(tmp_path)
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_document(str(original))
    wait_for_reading(qtbot, window)
    window.go_back()
    key = library.recents()[0].key
    window.home_view.recent_item_widgets()[0].remove_button.click()
    assert window.confirm_box is not None and library.has(key)
    press(window.confirm_box, tr("home.remove_confirm", Language.ES))
    assert library.recents() == [] and not library.has(key)
    assert window.home_view.recent_items == []
    assert original.is_file()


def test_a_document_opened_while_a_folder_is_selected_goes_into_it(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    folder = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    window.home_view.set_recents([], date(2026, 10, 7), store.groups())
    window.home_view.folder_filter.chips[folder.id].click()
    assert window.home_view.current_folder_id == folder.id

    window.open_document(str(copy_of_digital(tmp_path)))
    wait_for_reading(qtbot, window)
    assert library.recents()[0].folder_id == folder.id
    window.go_back()
    window.open_sample()
    assert [r.folder_id for r in library.recents()] == [folder.id, folder.id]


def test_reopening_a_document_does_not_move_it_to_the_selected_folder(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    folder = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    window.open_sample()
    window.go_back()
    window.home_view.folder_filter.chips[folder.id].click()
    window.open_sample()
    assert library.recents()[0].folder_id == ""


# ---- window: entries that survive a formatter version change ---------------------------


def age_the_cache(library: DocumentLibrary) -> str:
    """Rewrite the only entry the way an older release left it (key ending in -f1)."""
    [entry_now] = library.recents()
    old_key = f"{entry_now.doc_id}-f1"
    library._cache_path(entry_now.key).rename(library._cache_path(old_key))
    index = json.loads((library._root / "recents.json").read_text(encoding="utf-8"))
    index[0]["key"] = old_key
    (library._root / "recents.json").write_text(json.dumps(index), encoding="utf-8")
    return old_key


def test_after_a_formatter_update_the_document_stays_and_is_processed_again(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    folder = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    original = copy_of_digital(tmp_path)
    window.open_document(str(original))
    wait_for_reading(qtbot, window)
    window.go_back()
    window.move_document(library.recents()[0].key, folder.id)
    old_key = age_the_cache(library)

    window._refresh_home()
    assert [i.name for i in window.home_view.recent_items] == [original.name]

    window.open_recent(old_key)
    assert window.screen_shown is Screen.PROCESSING
    wait_for_reading(qtbot, window)
    [migrated] = library.recents()
    assert migrated.key.endswith(f"-f{FORMATTER_VERSION}")
    assert migrated.folder_id == folder.id
    assert not library.has(old_key) and library.has(migrated.key)
    assert not library.needs_processing(migrated.key)


def test_a_missing_original_offers_to_remove_the_entry(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    original = copy_of_digital(tmp_path)
    window.open_document(str(original))
    wait_for_reading(qtbot, window)
    window.go_back()
    old_key = age_the_cache(library)
    original.unlink()

    window.open_recent(old_key)
    dialog = window.error_dialog
    assert dialog is not None
    assert dialog.kind is ProcessingErrorKind.LIBRARY_FILE_MISSING
    assert window.screen_shown is Screen.HOME
    assert [r.key for r in library.recents()] == [old_key]  # nothing is lost yet
    press(dialog, tr("dialog.remove_from_library", Language.ES))
    assert library.recents() == []
    assert window.home_view.recent_items == []


def test_dismissing_the_missing_file_message_keeps_the_entry(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    library.store("gone-f1", tmp_path / "gone.pdf", cached(), 1, False)
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_recent("gone-f1")
    assert window.error_dialog is not None
    press(window.error_dialog, tr("common.understood", Language.ES))
    assert [r.key for r in library.recents()] == ["gone-f1"]


def test_an_outdated_sample_is_rebuilt_from_the_bundled_text(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    window = make_window(qtbot, tts, library, tmp_path)
    window.open_sample()
    window.go_back()
    old_key = age_the_cache(library)
    window.open_recent(old_key)
    assert window.screen_shown is Screen.READING
    [rebuilt] = library.recents()
    assert rebuilt.key.endswith(f"-f{FORMATTER_VERSION}")
    assert rebuilt.name == tr("home.sample_title", Language.ES)


# ---- home view: library filters ---------------------------------------------------------


def make_home(qtbot: QtBot, width: int = 1024) -> HomeView:
    load_reading_font()
    home = HomeView(THEMES[ThemeId.LIGHT], Language.ES)
    qtbot.addWidget(home)
    home.resize(width, 700)
    home.show()
    QApplication.processEvents()
    return home


def folders_and_entries() -> tuple[GroupStore, list[RecentDocument]]:
    store = GroupStore()
    maths = store.create("Matemáticas")
    science = store.create("Ciencias")
    entries = [
        entry("algebra.pdf", maths.id),
        entry("geometria.pdf", maths.id),
        entry("celulas.pdf", science.id),
        entry("suelto.pdf"),
    ]
    return store, entries


def test_the_chips_count_documents_and_filter_the_cards(qtbot: QtBot) -> None:
    store, entries = folders_and_entries()
    maths, science = store.groups()
    home = make_home(qtbot)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    chips = home.folder_filter.chips
    assert chips["*"].text() == "Todos (4)"
    assert chips[""].text() == "Sin carpeta (1)"
    assert chips[maths.id].text() == "Matemáticas (2)"
    assert len(home.recent_item_widgets()) == 4

    chips[maths.id].click()
    assert [i.name_label.full_text for i in home.recent_item_widgets()] == [
        "algebra.pdf",
        "geometria.pdf",
    ]
    assert home.current_folder_id == maths.id
    assert home.destination_combo.currentData() == maths.id
    home.folder_filter.chips[""].click()
    assert [i.name_label.full_text for i in home.recent_item_widgets()] == [
        "suelto.pdf"
    ]
    assert home.current_folder_id == "" and home.destination_combo.currentData() == ""
    assert science.id in home.folder_filter.chips


def test_search_by_name_ignores_accents_and_combines_with_the_folder(
    qtbot: QtBot,
) -> None:
    store, entries = folders_and_entries()
    home = make_home(qtbot)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    home.search_edit.setText("CELULAS")
    assert [e.name for e in home.visible_items] == ["celulas.pdf"]
    home.search_edit.setText("zzz")
    assert home.visible_items == []
    assert home.library_message.text() == tr("home.search_no_results", Language.ES)
    home.search_edit.setText("")
    home.folder_filter.chips[store.groups()[0].id].click()
    home.search_edit.setText("geo")
    assert [e.name for e in home.visible_items] == ["geometria.pdf"]


def test_an_empty_folder_says_so_and_a_deleted_folder_falls_back_to_all(
    qtbot: QtBot,
) -> None:
    store, entries = folders_and_entries()
    empty = store.create("Historia")
    home = make_home(qtbot)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    home.folder_filter.chips[empty.id].click()
    assert home.library_message.text() == tr("home.folder_empty", Language.ES)
    store.delete(empty.id)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    assert home.folder_filter.selected == "*" and len(home.visible_items) == 4


def test_a_card_names_its_folder_and_its_menu_moves_the_document(qtbot: QtBot) -> None:
    store, entries = folders_and_entries()
    _maths, science = store.groups()
    home = make_home(qtbot)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    card = home.recent_item_widgets()[0]
    assert card.meta_label.full_text.endswith("Matemáticas")
    texts = [a.text() for a in card.move_menu.actions()]
    assert texts == ["Sin carpeta", "Matemáticas", "Ciencias"]
    assert [a.isChecked() for a in card.move_menu.actions()] == [False, True, False]
    with qtbot.waitSignal(home.recent_move_requested, timeout=2000) as moved:
        card.move_menu.actions()[2].trigger()
    assert moved.args == ["algebra.pdf", science.id]


def test_only_folders_and_no_documents_still_shows_the_library_controls(
    qtbot: QtBot,
) -> None:
    store = GroupStore()
    store.create("Matemáticas")
    home = make_home(qtbot)
    home.set_recents([], date(2026, 10, 7), store.groups())
    assert home.folder_filter.isVisible() and home.continue_card.isHidden()
    assert home.library_message.isVisible()


@pytest.mark.parametrize("width", [1024, 1100, 1400])
def test_the_library_has_no_horizontal_scroll_with_many_long_folders(
    qtbot: QtBot, width: int
) -> None:
    store = GroupStore()
    folders = [store.create(f"{LONG_NAME[:30]} {n}") for n in range(12)]
    entries = [entry(LONG_NAME, folders[0].id), entry("b.pdf"), entry(LONG_NAME + "x")]
    home = make_home(qtbot, width)
    home.set_recents(entries, date(2026, 10, 7), store.groups())
    QApplication.processEvents()
    scroll = home.scroll
    assert isinstance(scroll, QScrollArea)
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.widget().width() <= scroll.viewport().width()
    content_right = scroll.widget().width()
    for chip in [*home.folder_filter.chips.values(), home.folder_filter.add_button]:
        right = chip.mapTo(scroll.widget(), chip.rect().bottomRight()).x()
        assert right <= content_right
    for item in home.recent_item_widgets():
        right = item.mapTo(scroll.widget(), item.rect().bottomRight()).x()
        assert right <= content_right
        assert item.open_button.width() >= item.open_button.sizeHint().width()
    long_chip = home.folder_filter.chips[folders[0].id]
    assert long_chip.toolTip() == folders[0].name
