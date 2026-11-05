"""AccessibleErrorDialog: buttons keep their text when the labels need more room."""

from PySide6.QtWidgets import QApplication, QPushButton
from pytestqt.qtbot import QtBot

from clearread.ui.dialogs import AccessibleErrorDialog
from clearread.ui.strings import Language
from clearread.ui.theme import THEMES, ThemeId
from clearread.workers.ocr_worker import ProcessingErrorKind

LARGE_FONT_POINTS = 24


def make_missing_file_dialog(qtbot: QtBot) -> AccessibleErrorDialog:
    dialog = AccessibleErrorDialog(
        None,
        ProcessingErrorKind.LIBRARY_FILE_MISSING,
        THEMES[ThemeId.LIGHT],
        Language.ES,
        offer_remove=True,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_every_button_is_at_least_as_wide_as_its_text_needs(qtbot: QtBot) -> None:
    dialog = make_missing_file_dialog(qtbot)
    font = dialog.font()
    font.setPointSize(LARGE_FONT_POINTS)
    dialog.setFont(font)
    dialog.show()
    QApplication.processEvents()
    buttons = dialog.findChildren(QPushButton)
    assert buttons
    for button in buttons:
        assert button.width() >= button.sizeHint().width(), button.text()


def test_the_dialog_grows_instead_of_squeezing_the_buttons(qtbot: QtBot) -> None:
    dialog = make_missing_file_dialog(qtbot)
    font = dialog.font()
    font.setPointSize(LARGE_FONT_POINTS)
    dialog.setFont(font)
    dialog.show()
    QApplication.processEvents()
    buttons_width = sum(b.sizeHint().width() for b in dialog.findChildren(QPushButton))
    assert dialog.width() >= buttons_width
