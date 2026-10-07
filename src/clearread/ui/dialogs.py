"""Accessible, low-cognitive-load error dialog (§4.9, design system 7)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.choose_other_requested = False
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
