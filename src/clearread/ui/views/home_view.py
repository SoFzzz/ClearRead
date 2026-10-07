"""Home and processing views (§4.9, design system 5.1 and 3.4)."""

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clearread.services.document_library import RecentDocument
from clearread.services.ingestor import DocumentIngestor
from clearread.services.reading_stats import ReadingStats
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens

CONTENT_MAX_WIDTH = 1100
PAGE_MARGIN = 32
GRID_SPACING = 16
RECENT_COLUMNS = 2
DROP_ZONE_MIN_WIDTH = 320
DROP_ZONE_MIN_HEIGHT = 230
PROCESSING_CARD_WIDTH = 600
ICON_BOX = 40
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60


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


def format_count(value: int, language: Language) -> str:
    grouped = f"{value:,}"
    return grouped.replace(",", ".") if language is Language.ES else grouped


def format_duration(seconds: int, language: Language) -> str:
    minutes_total = seconds // SECONDS_PER_MINUTE
    hours, minutes = divmod(minutes_total, MINUTES_PER_HOUR)
    if hours:
        return tr("home.stats.hours", language, hours=hours, minutes=minutes)
    return tr("home.stats.minutes", language, minutes=minutes)


def recent_meta_key(entry: RecentDocument) -> str:
    if entry.is_photo:
        return "home.recent_photo"
    if Path(entry.path).suffix.lower() == ".txt":
        return "home.recent_text"
    return "home.recent_pdf"


class ElidedLabel(QLabel):
    """One line that ends in an ellipsis instead of widening its layout (tooltip: full text)."""

    def __init__(self, text: str = "", role: str | None = None) -> None:
        super().__init__()
        if role:
            self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    @property
    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._elide()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._elide()

    def _elide(self) -> None:
        elided = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(self.width(), 0)
        )
        if elided != self.text():
            super().setText(elided)


def _card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(8)
    return card, layout


def fit_button(button: QPushButton) -> None:
    """Never let a layout squeeze a button below its text: it keeps its own size hint."""
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def _progress_bar(percent: int) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(percent)
    bar.setTextVisible(False)
    return bar


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

        icon = QLabel()
        icon.setPixmap(
            load_icon("image" if entry.is_photo else "file", tokens.text).pixmap(20, 20)
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(ICON_BOX, ICON_BOX)
        self.name_label = ElidedLabel(entry.name, role="heading")
        self.name_label.setStyleSheet("font-size: 15px;")
        meta_key = recent_meta_key(entry)
        self.meta_label = ElidedLabel(
            tr(
                meta_key,
                language,
                pages=format_pages(entry.pages, language),
                opened=format_opened(entry.opened_at, today, language),
            ),
            role="muted",
        )
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.name_label)
        texts.addWidget(self.meta_label)

        self.remove_button = QPushButton()
        self.remove_button.setIcon(load_icon("close", tokens.secondary))
        self.remove_button.setFixedWidth(ICON_BOX)
        self.remove_button.setToolTip(tr("home.recent_remove", language))
        self.remove_button.setAccessibleName(
            tr("home.recent_remove_named", language, name=entry.name)
        )
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.key))

        self.progress_label = QLabel(
            tr("home.progress", language, percent=entry.progress_percent)
        )
        self.progress_label.setProperty("role", "muted")
        self.open_button = QPushButton(tr("home.recent_open", language))
        self.open_button.setAccessibleName(
            tr("home.recent_open_named", language, name=entry.name)
        )
        self.open_button.clicked.connect(lambda: self.open_requested.emit(self.key))
        fit_button(self.open_button)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        top.addLayout(texts, stretch=1)
        top.addWidget(self.remove_button, alignment=Qt.AlignmentFlag.AlignTop)
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addWidget(_progress_bar(entry.progress_percent), stretch=1)
        bottom.addWidget(self.progress_label)
        bottom.addWidget(self.open_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addLayout(bottom)


class StatCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.value_label = QLabel()
        self.value_label.setProperty("role", "stat")
        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "muted")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(0)
        layout.addWidget(self.value_label)
        layout.addWidget(self.title_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
        self.setAccessibleName(f"{self.title_label.text()}: {value}")


class HomeView(QWidget):
    """Dashboard: continue reading, drop zone, statistics and recent documents."""

    file_chosen = Signal(str)
    sample_requested = Signal()
    recent_open_requested = Signal(str)
    recent_remove_requested = Signal(str)

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__()
        self._tokens = tokens
        self._language = language
        self.recent_items: list[RecentDocument] = []
        self._stats = ReadingStats()
        self._continue_key = ""
        self.setAcceptDrops(True)
        self._build_ui()
        shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.choose_file)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _build_ui(self) -> None:
        self.title_label = QLabel(self._t("home.dashboard_title"))
        self.title_label.setProperty("role", "title")
        self.continue_card = self._build_continue_card()
        self.drop_zone = self._build_drop_zone()
        top = QHBoxLayout()
        top.setSpacing(GRID_SPACING)
        top.addWidget(self.continue_card, stretch=3)
        top.addWidget(self.drop_zone, stretch=2)

        self.stat_words = StatCard(self._t("home.stats.words"))
        self.stat_time = StatCard(self._t("home.stats.time"))
        self.stat_documents = StatCard(self._t("home.stats.documents"))
        stats = QHBoxLayout()
        stats.setSpacing(GRID_SPACING)
        for card in (self.stat_words, self.stat_time, self.stat_documents):
            stats.addWidget(card, stretch=1)
        self.stats_hint = QLabel(self._t("home.stats.hint"))
        self.stats_hint.setProperty("role", "muted")
        self.stats_hint.setWordWrap(True)
        self.stats_box = QWidget()
        stats_layout = QVBoxLayout(self.stats_box)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(8)
        stats_layout.addLayout(stats)
        stats_layout.addWidget(self.stats_hint)

        self.recent_heading = QLabel(self._t("home.recent_title"))
        self.recent_heading.setProperty("role", "heading")
        self._recent_grid = QGridLayout()
        self._recent_grid.setSpacing(GRID_SPACING)
        for column in range(RECENT_COLUMNS):
            self._recent_grid.setColumnStretch(column, 1)

        content = QWidget()
        content.setMaximumWidth(CONTENT_MAX_WIDTH)
        column = QVBoxLayout(content)
        column.setContentsMargins(PAGE_MARGIN, 28, PAGE_MARGIN, PAGE_MARGIN)
        column.setSpacing(20)
        column.addWidget(self.title_label)
        column.addLayout(top)
        column.addWidget(self.stats_box)
        column.addWidget(self.recent_heading)
        column.addLayout(self._recent_grid)
        column.addStretch(1)

        page = QWidget()
        centered = QHBoxLayout(page)
        centered.setContentsMargins(0, 0, 0, 0)
        # Spacers on both sides keep the content centred while it fills the width up to
        # its maximum (an alignment would shrink it to its size hint).
        centered.addStretch(1)
        centered.addWidget(content, stretch=100)
        centered.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(page)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.set_recents([], local_today())

    def _build_continue_card(self) -> QFrame:
        card, layout = _card()
        caption = QLabel(self._t("home.continue_title"))
        caption.setProperty("role", "muted")
        self.continue_name = ElidedLabel(role="heading")
        self.continue_bar = _progress_bar(0)
        self.continue_progress = QLabel()
        self.continue_progress.setProperty("role", "muted")
        self.continue_button = QPushButton(self._t("home.continue_button"))
        self.continue_button.setProperty("variant", "primary")
        self.continue_button.setIcon(load_icon("play", self._tokens.primary_fg))
        self.continue_button.clicked.connect(
            lambda: self.recent_open_requested.emit(self._continue_key)
        )
        fit_button(self.continue_button)
        progress = QHBoxLayout()
        progress.setSpacing(12)
        progress.addWidget(self.continue_bar, stretch=1)
        progress.addWidget(self.continue_progress)
        layout.addWidget(caption)
        layout.addWidget(self.continue_name)
        layout.addStretch(1)
        layout.addLayout(progress)
        layout.addWidget(self.continue_button, alignment=Qt.AlignmentFlag.AlignLeft)
        card.setMinimumHeight(DROP_ZONE_MIN_HEIGHT)
        return card

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setObjectName("DropZone")
        zone.setMinimumSize(DROP_ZONE_MIN_WIDTH, DROP_ZONE_MIN_HEIGHT)
        self.upload_icon = QLabel()
        self.upload_icon.setPixmap(
            load_icon("upload", self._tokens.text).pixmap(20, 20)
        )
        self.drop_title = QLabel(self._t("home.drop_title"))
        self.drop_title.setProperty("role", "heading")
        self.drop_title.setWordWrap(True)
        self.drop_hint = QLabel(self._t("home.formats_hint"))
        self.drop_hint.setProperty("role", "muted")
        self.drop_hint.setWordWrap(True)
        self.choose_button = QPushButton(self._t("home.choose_file"))
        self.choose_button.setIcon(load_icon("folder", self._tokens.primary_fg))
        self.choose_button.setProperty("variant", "primary")
        self.choose_button.setToolTip(f"{self._t('home.choose_file')} (Ctrl+O)")
        self.choose_button.clicked.connect(self.choose_file)
        self.sample_button = QPushButton(self._t("home.try_sample"))
        self.sample_button.clicked.connect(self.sample_requested)
        for button in (self.choose_button, self.sample_button):
            fit_button(button)
        # Side by side when the zone is the whole page, stacked when it shares the row.
        self._zone_buttons = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self._zone_buttons.setSpacing(8)
        self._zone_buttons.addWidget(self.choose_button)
        self._zone_buttons.addWidget(self.sample_button)
        self._zone_buttons.addStretch(1)
        layout = QVBoxLayout(zone)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(self.upload_icon, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.drop_title)
        layout.addWidget(self.drop_hint)
        layout.addStretch(1)
        layout.addLayout(self._zone_buttons)
        return zone

    def apply_theme(self, tokens: ThemeTokens) -> None:
        """Recolour the icons, which are rendered with the theme colours."""
        self._tokens = tokens
        self.upload_icon.setPixmap(load_icon("upload", tokens.text).pixmap(20, 20))
        self.choose_button.setIcon(load_icon("folder", tokens.primary_fg))
        self.continue_button.setIcon(load_icon("play", tokens.primary_fg))
        self.set_recents(self.recent_items, local_today())

    def set_stats(self, stats: ReadingStats) -> None:
        self._stats = stats
        self.stat_words.set_value(format_count(stats.words_read, self._language))
        self.stat_time.set_value(format_duration(stats.seconds_read, self._language))
        self.stat_documents.set_value(
            format_count(len(self.recent_items), self._language)
        )

    def set_recents(self, entries: list[RecentDocument], today: date) -> None:
        while self._recent_grid.count():
            widget = self._recent_grid.takeAt(0).widget()
            if widget is not None:
                widget.hide()  # deleteLater() alone leaves it painted until the loop runs
                widget.setParent(None)
                widget.deleteLater()
        for index, entry in enumerate(entries):
            row = RecentItem(entry, today, self._tokens, self._language)
            row.open_requested.connect(self.recent_open_requested)
            row.remove_requested.connect(self.recent_remove_requested)
            self._recent_grid.addWidget(
                row, index // RECENT_COLUMNS, index % RECENT_COLUMNS
            )
        self.recent_items = entries
        self._show_mode(entries)
        self.set_stats(self._stats)

    def _show_mode(self, entries: list[RecentDocument]) -> None:
        empty = not entries
        self.title_label.setVisible(not empty)
        self.continue_card.setVisible(not empty)
        self.stats_box.setVisible(not empty)
        self.recent_heading.setVisible(not empty)
        self.drop_title.setText(
            self._t("home.empty.title" if empty else "home.drop_title")
        )
        self.drop_hint.setText(
            self._t("home.empty.body" if empty else "home.formats_hint")
        )
        self.drop_zone.setMinimumHeight(260 if empty else DROP_ZONE_MIN_HEIGHT)
        self._zone_buttons.setDirection(
            QBoxLayout.Direction.LeftToRight
            if empty
            else QBoxLayout.Direction.TopToBottom
        )
        if entries:
            latest = entries[0]
            self._continue_key = latest.key
            self.continue_name.set_full_text(latest.name)
            self.continue_bar.setValue(latest.progress_percent)
            self.continue_progress.setText(
                self._t("home.progress", percent=latest.progress_percent)
            )

    def recent_item_widgets(self) -> list[RecentItem]:
        items = (self._recent_grid.itemAt(i) for i in range(self._recent_grid.count()))
        return [i.widget() for i in items if isinstance(i.widget(), RecentItem)]

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
