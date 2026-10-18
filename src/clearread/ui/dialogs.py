"""Accessible, low-cognitive-load error dialog (§4.9, design system 7)."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clearread.services.groups import MAX_NAME_CHARS, GroupNameProblem
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens
from clearread.workers.ocr_worker import ProcessingErrorKind

DIALOG_WIDTH = 540
MARK_SIZE = 44


class AccessibleErrorDialog(QDialog):
    """Title, one plain sentence and what the person can do; no technical text."""

    def __init__(
        self,
        parent: QWidget | None,
        kind: ProcessingErrorKind,
        tokens: ThemeTokens,
        language: Language,
        offer_choose_other: bool = True,
        offer_remove: bool = False,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.choose_other_requested = False
        self.remove_requested = False
        self.setObjectName("ErrorDialog")
        self.setWindowTitle(tr("dialog.window_title", language))
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)

        slug = kind.value
        title = QLabel(tr(f"error.{slug}.title", language))
        title.setProperty("role", "heading")
        title.setWordWrap(True)
        message = QLabel(tr(f"error.{slug}.message", language))
        message.setWordWrap(True)
        mark = QLabel("!")
        mark.setObjectName("ErrorMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(MARK_SIZE, MARK_SIZE)
        mark.setAccessibleName(tr("dialog.window_title", language))

        texts = QVBoxLayout()
        texts.addWidget(title)
        texts.addWidget(message)
        header = QHBoxLayout()
        header.setSpacing(16)
        header.addWidget(mark, alignment=Qt.AlignmentFlag.AlignTop)
        header.addLayout(texts, stretch=1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        if offer_choose_other:
            other = QPushButton(tr("dialog.choose_other", language))
            other.clicked.connect(self._choose_other)
            buttons.addWidget(other)
        if offer_remove:
            remove = QPushButton(tr("dialog.remove_from_library", language))
            remove.clicked.connect(self._remove)
            buttons.addWidget(remove)
        self.understood_button = QPushButton(tr("common.understood", language))
        self.understood_button.setProperty("variant", "primary")
        self.understood_button.setDefault(True)
        self.understood_button.clicked.connect(self.accept)
        buttons.addWidget(self.understood_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(self._action_box(slug, tokens, language))
        layout.addLayout(buttons)
        self.understood_button.setFocus()

    @staticmethod
    def _action_box(slug: str, tokens: ThemeTokens, language: Language) -> QFrame:
        box = QFrame()
        box.setObjectName("ActionBox")
        icon = QLabel()
        icon.setPixmap(load_icon("lightbulb", tokens.text).pixmap(20, 20))
        heading = QLabel(tr("dialog.what_you_can_do", language))
        heading.setProperty("role", "heading")
        heading.setStyleSheet("font-size: 15px;")
        action = QLabel(tr(f"error.{slug}.action", language))
        action.setWordWrap(True)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(heading)
        texts.addWidget(action)
        row = QHBoxLayout(box)
        row.setContentsMargins(16, 12, 16, 12)
        row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, stretch=1)
        return box

    def _choose_other(self) -> None:
        self.choose_other_requested = True
        self.accept()

    def _remove(self) -> None:
        self.remove_requested = True
        self.accept()


def make_confirm_box(
    parent: QWidget, question: str, detail: str, confirm_label: str, language: Language
) -> tuple[QMessageBox, QPushButton]:
    """A question with a destructive answer; Cancel is the default, like the settings one."""
    box = QMessageBox(
        QMessageBox.Icon.Question,
        tr("dialog.window_title", language),
        question,
        parent=parent,
    )
    box.setInformativeText(detail)
    confirm = box.addButton(confirm_label, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton(
        tr("common.cancel", language), QMessageBox.ButtonRole.RejectRole
    )
    box.setDefaultButton(cancel)
    return box, confirm


def make_restart_box(
    parent: QWidget, language: Language
) -> tuple[QMessageBox, QPushButton]:
    """Worded in the language being chosen, so the user reads what they will get."""
    box = QMessageBox(
        QMessageBox.Icon.Question,
        tr("settings.language.confirm_title", language),
        tr("settings.language.confirm_message", language),
        parent=parent,
    )
    restart = box.addButton(
        tr("settings.language.confirm_restart", language),
        QMessageBox.ButtonRole.AcceptRole,
    )
    cancel = box.addButton(
        tr("common.cancel", language), QMessageBox.ButtonRole.RejectRole
    )
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box, restart


def make_clear_recents_box(
    parent: QWidget, language: Language
) -> tuple[QMessageBox, QPushButton]:
    box = QMessageBox(
        QMessageBox.Icon.Question,
        tr("settings.clear_confirm.title", language),
        tr("settings.clear_confirm.message", language),
        parent=parent,
    )
    yes = box.addButton(
        tr("settings.clear_confirm.yes", language), QMessageBox.ButtonRole.AcceptRole
    )
    cancel = box.addButton(
        tr("common.cancel", language), QMessageBox.ButtonRole.RejectRole
    )
    box.setDefaultButton(cancel)
    return box, yes


class NamePromptDialog(QDialog):
    """Asks for a short name; ``apply`` returns why the name was refused, or None if saved."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        field_label: str,
        initial: str,
        confirm_label: str,
        apply: Callable[[str], GroupNameProblem | None],
        language: Language,
    ) -> None:
        super().__init__(parent)
        self._apply = apply
        self._language = language
        self.setObjectName("ErrorDialog")
        self.setWindowTitle(tr("dialog.window_title", language))
        self.setModal(True)
        self.setFixedWidth(DIALOG_WIDTH)

        heading = QLabel(title)
        heading.setProperty("role", "heading")
        label = QLabel(field_label)
        self.name_edit = QLineEdit(initial)
        self.name_edit.setMaxLength(MAX_NAME_CHARS)
        self.name_edit.setAccessibleName(field_label)
        self.name_edit.setPlaceholderText(tr("group.name_hint", language))
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self._submit)
        self.problem_label = QLabel()
        self.problem_label.setWordWrap(True)
        self.problem_label.hide()

        cancel = QPushButton(tr("common.cancel", language))
        cancel.clicked.connect(self.reject)
        self.confirm_button = QPushButton(confirm_label)
        self.confirm_button.setProperty("variant", "primary")
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self._submit)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(label)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.problem_label)
        layout.addLayout(buttons)
        self.name_edit.setFocus()

    def _submit(self) -> None:
        problem = self._apply(self.name_edit.text())
        if problem is None:
            self.accept()
            return
        self.problem_label.setText(tr(f"group.error.{problem.value}", self._language))
        self.problem_label.show()
        self.name_edit.setFocus()
