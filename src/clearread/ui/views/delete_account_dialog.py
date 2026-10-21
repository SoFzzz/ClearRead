"""Confirmation of "Delete my account": asks for the password (A.4.12, AUTH-F06)."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clearread.ui.strings import Language, tr
from clearread.ui.views.login_widgets import (
    password_block as make_password_block,
)
from clearread.ui.views.login_widgets import (
    set_variant,
    text_label,
)

DIALOG_WIDTH = 520


class DeleteAccountDialog(QDialog):
    """Stays open on a wrong password; the password only travels through ``submitted``."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None, language: Language) -> None:
        super().__init__(parent)
        self._language = language
        self._working = False
        self.setObjectName("ErrorDialog")
        self.setWindowTitle(tr("dialog.window_title", language))
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)

        title = QLabel(tr("account.delete_title", language))
        title.setProperty("role", "heading")
        title.setWordWrap(True)
        body = text_label(tr("account.delete_body", language))
        hint = text_label(tr("account.delete_password_hint", language), "note")
        self.password_block, self.password_field = make_password_block(
            tr("account.delete_password_label", language), language
        )
        self.password_edit = self.password_field.edit
        self.password_edit.textChanged.connect(self._update_enabled)
        self.password_edit.returnPressed.connect(self._on_return)
        self.busy_label = text_label(tr("account.deleting", language), "note")
        self.busy_label.hide()

        self.cancel_button = set_variant(
            QPushButton(tr("common.cancel", language)), "primary"
        )
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.delete_button = QPushButton(tr("account.delete_confirm", language))
        self.delete_button.setAutoDefault(False)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._submit)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(hint)
        layout.addWidget(self.password_block)
        layout.addWidget(self.busy_label)
        layout.addLayout(buttons)
        self.password_edit.setFocus()

    @property
    def wrong_password_text(self) -> str:
        return self.password_block.message.text

    def show_wrong_password(self) -> None:
        self._set_working(False)
        self.password_block.message.show_message(
            tr("account.delete_wrong_password", self._language)
        )
        self.password_edit.setFocus()

    def _update_enabled(self) -> None:
        self.delete_button.setEnabled(bool(self.password_edit.text()))

    def _on_return(self) -> None:
        # Enter never deletes by itself: it only moves to the button that does.
        if self.delete_button.isEnabled():
            self.delete_button.setFocus()

    def _submit(self) -> None:
        password = self.password_edit.text()
        if not password:
            return
        self.password_block.message.clear()
        self._set_working(True)
        self.password_edit.clear()
        self.submitted.emit(password)

    def dismiss(self) -> None:
        """Close for good, also while a request is running."""
        self._working = False
        self.reject()

    def reject(self) -> None:
        # Escape must not hide a request that is already deleting.
        if not self._working:
            super().reject()

    def _set_working(self, working: bool) -> None:
        self._working = working
        self.password_block.set_blocked(working)
        self.busy_label.setVisible(working)
        self.cancel_button.setEnabled(not working)
        self.delete_button.setEnabled(not working and bool(self.password_edit.text()))
