"""My words: the words the assistant explained, kept on this computer (AI-F05)."""

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from clearread.services.glossary import GlossaryEntry, search_entries
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens
from clearread.ui.views.home_view import ElidedLabel, fit_button

CONTENT_MAX_WIDTH = 860
PAGE_MARGIN = 32


def format_added(added_on: str, language: Language) -> str:
    added = date.fromisoformat(added_on)
    month = tr(f"month.{added.month}", language)
    return tr("words.date", language, day=added.day, month=month)


class WordCard(QFrame):
    listen_requested = Signal(str)  # text to read aloud
    delete_requested = Signal(str)  # word

    def __init__(
        self, entry: GlossaryEntry, tokens: ThemeTokens, language: Language
    ) -> None:
        super().__init__()
        self.entry = entry
        self.setObjectName("Card")
        word = QLabel(entry.word)
        word.setProperty("role", "heading")
        explanation = QLabel(entry.explanation)
        explanation.setWordWrap(True)
        meta = ElidedLabel(
            tr(
                "words.meta",
                language,
                document=entry.document,
                date=format_added(entry.added_on, language),
            ),
            role="muted",
        )
        self.listen_button = QPushButton(tr("words.listen", language))
        self.listen_button.setIcon(load_icon("speaker", tokens.secondary))
        self.listen_button.setAccessibleName(
            tr("words.listen_named", language, word=entry.word)
        )
        self.listen_button.clicked.connect(
            lambda: self.listen_requested.emit(f"{entry.word}. {entry.explanation}")
        )
        self.delete_button = QPushButton(tr("words.delete", language))
        self.delete_button.setIcon(load_icon("close", tokens.secondary))
        self.delete_button.setAccessibleName(
            tr("words.delete_named", language, word=entry.word)
        )
        self.delete_button.clicked.connect(
            lambda: self.delete_requested.emit(entry.word)
        )
        for button in (self.listen_button, self.delete_button):
            fit_button(button)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.listen_button)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(word)
        layout.addWidget(explanation)
        layout.addWidget(meta)
        layout.addLayout(buttons)


class WordsView(QWidget):
    listen_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__()
        self._tokens = tokens
        self._language = language
        self._entries: list[GlossaryEntry] = []
        self.cards: list[WordCard] = []
        self._build_ui()

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _build_ui(self) -> None:
        self.title_label = QLabel(self._t("words.title"))
        self.title_label.setProperty("role", "title")
        self.count_label = QLabel()
        self.count_label.setProperty("role", "muted")
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addWidget(self.count_label, alignment=Qt.AlignmentFlag.AlignBottom)
        header.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self._t("words.search_placeholder"))
        self.search_edit.setAccessibleName(self._t("words.search_placeholder"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._render)

        self.empty_title = QLabel(self._t("words.empty_title"))
        self.empty_title.setProperty("role", "heading")
        self.empty_body = QLabel(self._t("words.empty_body"))
        self.empty_body.setWordWrap(True)
        self.empty_box = QFrame()
        self.empty_box.setObjectName("Card")
        empty_layout = QVBoxLayout(self.empty_box)
        empty_layout.setContentsMargins(24, 20, 24, 20)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_body)
        self.no_results_label = QLabel(self._t("words.no_results"))
        self.no_results_label.setProperty("role", "muted")

        self._list = QVBoxLayout()
        self._list.setSpacing(12)
        content = QWidget()
        content.setMaximumWidth(CONTENT_MAX_WIDTH)
        column = QVBoxLayout(content)
        column.setContentsMargins(PAGE_MARGIN, 28, PAGE_MARGIN, PAGE_MARGIN)
        column.setSpacing(16)
        column.addLayout(header)
        column.addWidget(self.search_edit)
        column.addWidget(self.empty_box)
        column.addWidget(self.no_results_label)
        column.addLayout(self._list)
        column.addStretch(1)

        page = QWidget()
        centered = QHBoxLayout(page)
        centered.setContentsMargins(0, 0, 0, 0)
        # Spacers on both sides keep the content centred while it fills the width up to
        # its maximum (an alignment would shrink it to its size hint).
        centered.addStretch(1)
        centered.addWidget(content, stretch=100)
        centered.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._render()

    def set_entries(self, entries: list[GlossaryEntry]) -> None:
        self._entries = entries
        self._render()

    def _render(self) -> None:
        while self._list.count():
            widget = self._list.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        shown = search_entries(self._entries, self.search_edit.text())
        self.cards = []
        for entry in shown:
            card = WordCard(entry, self._tokens, self._language)
            card.listen_requested.connect(self.listen_requested)
            card.delete_requested.connect(self.delete_requested)
            self._list.addWidget(card)
            self.cards.append(card)
        total = len(self._entries)
        self.empty_box.setVisible(total == 0)
        self.search_edit.setVisible(total > 0)
        self.no_results_label.setVisible(total > 0 and not shown)
        self.count_label.setText(
            self._t("words.count_one")
            if total == 1
            else self._t("words.count_other", count=total)
        )
        self.count_label.setVisible(total > 0)
