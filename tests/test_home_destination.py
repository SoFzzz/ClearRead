"""Home: the "Save in" selector of the drop card and where new documents end up."""

import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fakes import EngineSource
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QScrollArea
from pytestqt.qtbot import QtBot
from samples.make_samples import SAMPLES_DIR

from clearread.core.config import AppConfig
from clearread.services.document_library import DocumentLibrary
from clearread.services.groups import GroupStore
from clearread.services.tts_controller import TTSController
from clearread.ui.fonts import load_reading_font
from clearread.ui.main_window import MainWindow, Screen
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId
from clearread.ui.views.home_view import HomeView

DIGITAL = SAMPLES_DIR / "sample_page_digital.pdf"
TIMEOUT_MS = 60000
TODAY = date(2026, 10, 7)
LONG_NAME = "Informe-de-biologia-celular-y-molecular-primer-parcial-2026-final"


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(tmp_path / "cache")


@pytest.fixture
def tts(qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=EngineSource())
    yield controller
    controller.shutdown()


def make_home(qtbot: QtBot, width: int = 1024) -> HomeView:
    load_reading_font()
    home = HomeView(THEMES[ThemeId.LIGHT], Language.ES)
    qtbot.addWidget(home)
    home.resize(width, 700)
    home.show()
    QApplication.processEvents()
    return home


def make_window(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
    folders: GroupStore,
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


def pdf_copy(tmp_path: Path, name: str = "mates.pdf") -> Path:
    target = tmp_path / name
    shutil.copyfile(DIGITAL, target)
    return target


def wait_for_reading(qtbot: QtBot, window: MainWindow) -> None:
    qtbot.waitUntil(lambda: window.screen_shown is Screen.READING, timeout=TIMEOUT_MS)
    qtbot.waitUntil(lambda: not window._retired_workers, timeout=TIMEOUT_MS)


def pick(home: HomeView, folder_id: str) -> None:
    home.destination_combo.setCurrentIndex(home.destination_combo.findData(folder_id))


def combo_texts(home: HomeView) -> list[str]:
    combo = home.destination_combo
    return [combo.itemText(i) for i in range(combo.count())]


def url_mime(path: Path) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    return mime


def drag_enter(home: HomeView, mime: QMimeData) -> None:
    event = QDragEnterEvent(
        QPoint(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    home.dragEnterEvent(event)


def drop(home: HomeView, mime: QMimeData) -> None:
    event = QDropEvent(
        QPointF(5, 5),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    home.dropEvent(event)


def test_the_selector_lists_no_folder_each_folder_and_the_new_folder_entry(
    qtbot: QtBot,
) -> None:
    store = GroupStore()
    store.create("Matemáticas")
    store.create("Ciencias")
    home = make_home(qtbot)
    home.set_recents([], TODAY, store.groups())
    assert combo_texts(home) == [
        "Sin carpeta",
        "Matemáticas",
        "Ciencias",
        "+ Nueva carpeta",
    ]
    assert home.destination_combo.currentData() == ""
    assert home.destination_combo.accessibleName()
    assert home.destination_combo.toolTip()
    assert home.destination_combo.focusPolicy() != Qt.FocusPolicy.NoFocus


def test_the_selector_shows_in_the_first_run_state_without_folders(
    qtbot: QtBot,
) -> None:
    home = make_home(qtbot)
    home.set_recents([], TODAY, [])
    assert home.destination_combo.isVisible()
    assert combo_texts(home) == ["Sin carpeta", "+ Nueva carpeta"]
    assert home.folder_filter.isHidden()


def test_the_selector_follows_the_chips_and_all_means_no_folder(qtbot: QtBot) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    home = make_home(qtbot)
    home.set_recents([], TODAY, store.groups())
    home.folder_filter.chips[maths.id].click()
    assert home.destination_combo.currentData() == maths.id
    assert home.current_folder_id == maths.id
    home.folder_filter.chips["*"].click()
    assert home.destination_combo.currentData() == ""
    assert home.current_folder_id == ""


def test_changing_the_selector_changes_the_destination_but_not_the_filter(
    qtbot: QtBot,
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    home = make_home(qtbot)
    home.set_recents([], TODAY, store.groups())
    pick(home, maths.id)
    assert home.current_folder_id == maths.id
    assert home.folder_filter.selected == "*"
    home.set_recents([], TODAY, store.groups())
    assert home.destination_combo.currentData() == maths.id


def test_a_deleted_destination_falls_back_to_no_folder(qtbot: QtBot) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    home = make_home(qtbot)
    home.set_recents([], TODAY, store.groups())
    pick(home, maths.id)
    store.delete(maths.id)
    home.set_recents([], TODAY, store.groups())
    assert home.current_folder_id == ""
    assert home.destination_combo.currentData() == ""


def test_dragging_a_file_over_the_zone_names_the_destination_folder(
    qtbot: QtBot, tmp_path: Path
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    home = make_home(qtbot)
    home.set_recents([], TODAY, store.groups())
    calm = home.drop_title.text()
    mime = url_mime(pdf_copy(tmp_path))

    drag_enter(home, mime)
    assert home.drop_title.text() == tr(
        "home.drop_release_none", Language.ES, folder="Sin carpeta"
    )
    home.dragLeaveEvent(None)
    assert home.drop_title.text() == calm

    pick(home, maths.id)
    drag_enter(home, mime)
    assert "«Matemáticas»" in home.drop_title.text()
    assert home.drop_zone.property("dragging") is True
    with qtbot.waitSignal(home.file_chosen, timeout=2000) as chosen:
        drop(home, mime)
    assert [Path(a) for a in chosen.args] == [tmp_path / "mates.pdf"]
    assert home.drop_title.text() == calm
    assert home.drop_zone.property("dragging") is False


def test_a_dropped_file_is_stored_in_the_chosen_folder_and_confirmed(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view
    pick(home, maths.id)

    drop(home, url_mime(pdf_copy(tmp_path)))
    wait_for_reading(qtbot, window)
    assert library.recents()[0].folder_id == maths.id
    window.go_back()
    assert [i.name_label.full_text for i in home.recent_item_widgets()] == ["mates.pdf"]
    assert home.folder_filter.chips[maths.id].text() == "Matemáticas (1)"
    assert home.saved_label.isVisible()
    assert home.saved_label.text() == tr(
        "home.saved_in", Language.ES, folder="Matemáticas"
    )


def test_choose_file_and_the_sample_use_the_destination_too(
    qtbot: QtBot,
    tts: TTSController,
    library: DocumentLibrary,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view
    pick(home, maths.id)
    chosen = pdf_copy(tmp_path)
    monkeypatch.setattr(
        "clearread.ui.views.home_view.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(chosen), ""),
    )
    home.choose_button.click()
    wait_for_reading(qtbot, window)
    assert library.recents()[0].folder_id == maths.id

    window.go_back()
    home.sample_button.click()
    assert library.recents()[0].folder_id == maths.id


def test_a_file_dropped_with_no_folder_selected_goes_loose(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    drop(window.home_view, url_mime(pdf_copy(tmp_path)))
    wait_for_reading(qtbot, window)
    assert library.recents()[0].folder_id == ""
    window.go_back()
    assert window.home_view.saved_label.text() == tr(
        "home.saved_in", Language.ES, folder="Sin carpeta"
    )


def test_a_document_already_in_the_library_keeps_its_folder(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    science = store.create("Ciencias")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view
    source = pdf_copy(tmp_path)
    pick(home, maths.id)
    window.open_document(str(source))
    wait_for_reading(qtbot, window)
    window.go_back()

    pick(home, science.id)
    window.open_document(str(source))
    assert library.recents()[0].folder_id == maths.id
    window.go_back()
    assert home.saved_label.text() == tr(
        "home.already_in", Language.ES, folder="Matemáticas"
    )


def test_a_folder_can_be_created_from_the_selector_even_with_an_empty_library(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore(tmp_path / "folders.json")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view
    assert home.folder_filter.isHidden()
    combo = home.destination_combo
    combo.setCurrentIndex(combo.findData("+new"))
    dialog = window.prompt_dialog
    assert dialog is not None
    dialog.name_edit.setText("Historia")
    dialog.confirm_button.click()
    [folder] = store.groups()
    assert combo.currentData() == folder.id
    assert home.current_folder_id == folder.id
    assert home.folder_filter.isVisible()

    drop(home, url_mime(pdf_copy(tmp_path)))
    wait_for_reading(qtbot, window)
    assert library.recents()[0].folder_id == folder.id


def test_cancelling_the_new_folder_dialog_keeps_the_previous_destination(
    qtbot: QtBot, tts: TTSController, library: DocumentLibrary, tmp_path: Path
) -> None:
    store = GroupStore()
    maths = store.create("Matemáticas")
    window = make_window(qtbot, tts, library, tmp_path, store)
    home = window.home_view
    pick(home, maths.id)
    home.destination_combo.setCurrentIndex(home.destination_combo.findData("+new"))
    assert home.destination_combo.currentData() == maths.id
    assert window.prompt_dialog is not None
    window.prompt_dialog.reject()
    assert home.current_folder_id == maths.id


@pytest.mark.parametrize("width", [1024, 1100, 1400])
def test_long_folder_names_do_not_make_the_selector_overflow(
    qtbot: QtBot, width: int
) -> None:
    store = GroupStore()
    folders = [store.create(f"{n} {LONG_NAME}") for n in range(6)]
    home = make_home(qtbot, width)
    home.set_recents([], TODAY, store.groups())
    pick(home, folders[0].id)
    QApplication.processEvents()
    scroll = home.scroll
    assert isinstance(scroll, QScrollArea)
    assert scroll.widget().width() <= scroll.viewport().width()
    combo = home.destination_combo
    right = combo.mapTo(scroll.widget(), combo.rect().bottomRight()).x()
    assert right <= scroll.widget().width()
    assert home.drop_zone.width() <= scroll.viewport().width()
