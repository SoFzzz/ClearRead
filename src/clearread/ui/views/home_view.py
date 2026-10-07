"""Home and processing views (§4.9, design system 5.1 and 3.4)."""

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from clearread.services.document_library import RecentDocument
from clearread.services.ingestor import DocumentIngestor
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens

CONTENT_WIDTH = 820
RECENT_ITEM_HEIGHT = 72
MAX_VISIBLE_RECENTS = 5
LIST_SPACING = 12
PROCESSING_CARD_WIDTH = 600
ICON_BOX = 40


def local_today() -> date:
    return datetime.now().astimezone().date()


def dialog_filter(language: Language) -> str:
    extensions = (
        DocumentIngestor.SUPPORTED_PDF_EXT | DocumentIngestor.SUPPORTED_IMAGE_EXT
    )
    patterns = " ".join(f"*{ext}" for ext in sorted(extensions))
    return tr("home.file_filter", language, patterns=patterns)


def format_opened(opened_at: str, today: date, language: Language) -> str:
    opened = datetime.fromisoformat(opened_at).date()
    days_ago = (today - opened).days
    if days_ago == 0:
        return tr("home.opened_today", language)
    if days_ago == 1:
        return tr("home.opened_yesterday", language)
    month = tr(f"month.{opened.month}", language)
    return tr("home.opened_on", language, day=opened.day, month=month)


def format_pages(pages: int, language: Language) -> str:
    if pages == 1:
        return tr("home.pages_one", language)
    return tr("home.pages_other", language, count=pages)


class RecentItem(QFrame):
    open_requested = Signal(str)
    remove_requested = Signal(str)

    def __init__(
        self,
        entry: RecentDocument,
        today: date,
        tokens: ThemeTokens,
        language: Language,
    ) -> None:
        super().__init__()
        self.key = entry.key
        self.setObjectName("RecentItem")
        self.setFixedHeight(RECENT_ITEM_HEIGHT)

        icon = QLabel()
        icon.setPixmap(
            load_icon("image" if entry.is_photo else "file", tokens.text).pixmap(20, 20)
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(ICON_BOX, ICON_BOX)
        name = QLabel(entry.name)
        name.setProperty("role", "heading")
        name.setStyleSheet("font-size: 15px;")
        meta_key = "home.recent_photo" if entry.is_photo else "home.recent_pdf"
        meta = QLabel(
            tr(
                meta_key,
                language,
                pages=format_pages(entry.pages, language),
                opened=format_opened(entry.opened_at, today, language),
            )
        )
        meta.setProperty("role", "muted")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addStretch(1)
        texts.addWidget(name)
        texts.addWidget(meta)
        texts.addStretch(1)

        self.open_button = QPushButton(tr("home.recent_open", language))
        self.open_button.setAccessibleName(
            tr("home.recent_open_named", language, name=entry.name)
        )
        self.open_button.clicked.connect(lambda: self.open_requested.emit(self.key))
        self.remove_button = QPushButton()
        self.remove_button.setIcon(load_icon("close", tokens.secondary))
        self.remove_button.setFixedWidth(ICON_BOX)
        remove_text = tr("home.recent_remove", language)
        self.remove_button.setToolTip(remove_text)
        self.remove_button.setAccessibleName(
            tr("home.recent_remove_named", language, name=entry.name)
        )
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.key))

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(12)
        row.addWidget(icon)
        row.addLayout(texts, stretch=1)
        row.addWidget(self.open_button)
        row.addWidget(self.remove_button)


class HomeView(QWidget):
    """Drop zone, file picker and the list of recent documents."""

    file_chosen = Signal(str)
    recent_open_requested = Signal(str)
    recent_remove_requested = Signal(str)

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__()
        self._tokens = tokens
        self._language = language
        self.recent_items: list[RecentDocument] = []
        self.setAcceptDrops(True)
        self._build_ui()
        shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.choose_file)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _build_ui(self) -> None:
        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("DropZone")
        self.drop_zone.setFixedSize(CONTENT_WIDTH, 168)
        upload = QLabel()
        upload.setPixmap(load_icon("upload", self._tokens.text).pixmap(20, 20))
        title = QLabel(self._t("home.drop_title"))
        title.setProperty("role", "heading")
        hint = QLabel(self._t("home.formats_hint"))
        hint.setProperty("role", "muted")
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addStretch(1)
        texts.addWidget(title)
        texts.addWidget(hint)
        texts.addStretch(1)
        self.choose_button = QPushButton(self._t("home.choose_file"))
        self.choose_button.setIcon(load_icon("folder", self._tokens.primary_fg))
        self.choose_button.setProperty("variant", "primary")
        self.choose_button.setToolTip(f"{self._t('home.choose_file')} (Ctrl+O)")
        self.choose_button.clicked.connect(self.choose_file)
        zone_row = QHBoxLayout(self.drop_zone)
        zone_row.setSpacing(20)
        zone_row.addStretch(1)
        zone_row.addWidget(upload)
        zone_row.addLayout(texts)
        zone_row.addWidget(self.choose_button)
        zone_row.addStretch(1)

        self.recent_heading = QLabel(self._t("home.recent_title"))
        self.recent_heading.setProperty("role", "heading")
        self._recent_layout = QVBoxLayout()
        self._recent_layout.setSpacing(LIST_SPACING)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_body = QWidget()
        recent_body.setLayout(self._recent_layout)
        self.recent_scroll = QScrollArea()
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recent_scroll.setWidget(recent_body)
        self.recent_scroll.setFixedWidth(CONTENT_WIDTH)
        max_list = MAX_VISIBLE_RECENTS * (RECENT_ITEM_HEIGHT + LIST_SPACING)
        self.recent_scroll.setMaximumHeight(max_list)

        column = QVBoxLayout()
        column.setSpacing(24)
        column.addWidget(self.drop_zone)
        column.addWidget(self.recent_heading)
        column.addWidget(self.recent_scroll, stretch=1)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 40, 0, 32)
        outer.addStretch(1)
        outer.addLayout(column)
        outer.addStretch(1)
        self.set_recents([], local_today())

    def set_recents(self, entries: list[RecentDocument], today: date) -> None:
        while self._recent_layout.count():
            item = self._recent_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for entry in entries:
            row = RecentItem(entry, today, self._tokens, self._language)
            row.open_requested.connect(self.recent_open_requested)
            row.remove_requested.connect(self.recent_remove_requested)
            self._recent_layout.addWidget(row)
        self._recent_layout.addStretch(1)
        self.recent_heading.setVisible(bool(entries))
        self.recent_scroll.setVisible(bool(entries))
        self.recent_items = entries

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("home.file_dialog_title"),
            "",
            dialog_filter(self._language),
        )
        if path:
            self.file_chosen.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_dragging(True)

    def dragLeaveEvent(self, event: object) -> None:
        self._set_dragging(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_dragging(False)
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            event.acceptProposedAction()
            self.file_chosen.emit(urls[0].toLocalFile())

    def _set_dragging(self, dragging: bool) -> None:
        self.drop_zone.setProperty("dragging", dragging)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)


class ProcessingView(QWidget):
    """Page-by-page progress with a Cancel button."""

    cancel_requested = Signal()

    def __init__(self, language: Language) -> None:
        super().__init__()
        self._language = language
        title = QLabel(tr("processing.title", language))
        title.setProperty("role", "title")
        self.file_label = QLabel()
        self.file_label.setProperty("role", "muted")
        self.status_label = QLabel()
        self.status_label.setProperty("role", "heading")
        self.status_label.setStyleSheet("font-size: 15px;")
        self.percent_label = QLabel()
        self.percent_label.setProperty("role", "muted")
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label, stretch=1)
        status_row.addWidget(self.percent_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        note = QLabel(tr("processing.note", language))
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        self.cancel_button = QPushButton(tr("common.cancel", language))
        self.cancel_button.clicked.connect(self.cancel_requested)

        card = QFrame()
        card.setObjectName("ProcessingCard")
        card.setFixedWidth(PROCESSING_CARD_WIDTH)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.file_label)
        layout.addSpacing(8)
        layout.addLayout(status_row)
        layout.addWidget(self.progress_bar)
        layout.addSpacing(8)
        layout.addWidget(note)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)

        outer = QHBoxLayout(self)
        outer.addStretch(1)
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addStretch(1)
        escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        escape.activated.connect(self.cancel_requested)

    def start(self, file_name: str) -> None:
        self.file_label.setText(file_name)
        self.set_progress(0, 1)
        self.status_label.setText("")
        self.percent_label.setText("")
        self.cancel_button.setFocus()

    def set_progress(self, page: int, total: int) -> None:
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(max(page - 1, 0))
        self.status_label.setText(
            tr("processing.reading_page", self._language, current=page, total=total)
        )
        percent = round(100 * max(page - 1, 0) / total)
        self.percent_label.setText(
            tr("processing.percent", self._language, percent=percent)
        )

    def set_preparing(self) -> None:
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.status_label.setText(tr("processing.preparing", self._language))
        self.percent_label.setText(
            tr("processing.percent", self._language, percent=100)
        )
