"""Main window: Home -> Processing -> Reading -> (Back) Home (design system 7)."""

from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clearread.core.config import AppConfig
from clearread.services.document_library import (
    CachedDocument,
    DocumentLibrary,
    compute_cache_key,
)
from clearread.services.ingestor import DocumentIngestor
from clearread.services.ocr_engine import OCREngine
from clearread.services.preprocessor import OCRPreprocessor
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import FormattedDocument, TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.dialogs import AccessibleErrorDialog
from clearread.ui.strings import Language, tr
from clearread.ui.theme import (
    THEMES,
    ThemeId,
    ThemeTokens,
    build_stylesheet,
    syllable_palette,
)
from clearread.ui.views.home_view import HomeView, ProcessingView, local_today
from clearread.ui.views.reading_view import ReadingView
from clearread.workers.ocr_worker import (
    DocumentProcessWorker,
    ProcessedDocument,
    ProcessingErrorKind,
)

MIN_WINDOW_SIZE = (1024, 700)
TOP_BAR_HEIGHT = 56
TITLE_MAX_CHARS = 60


class Screen(Enum):
    HOME = 0
    PROCESSING = 1
    READING = 2


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: AppConfig,
        ocr_engine: OCREngine,
        tts: TTSController,
        library: DocumentLibrary,
    ) -> None:
        super().__init__()
        self._config = config
        self._language = Language(config.ui_language)
        self._theme = ThemeId(config.theme)
        self._ocr_engine = ocr_engine
        self._tts = tts
        self._library = library
        self._ingestor = DocumentIngestor()
        self._preprocessor = OCRPreprocessor()
        self._syllabifier = SpanishSyllabifier()
        self._worker: DocumentProcessWorker | None = None
        self._retired_workers: set[DocumentProcessWorker] = set()
        self._pending: tuple[Path, str] | None = None
        self.error_dialog: AccessibleErrorDialog | None = None
        self._build_ui()
        self.setStyleSheet(build_stylesheet(self.tokens))
        self.show_screen(Screen.HOME)

    @property
    def screen_shown(self) -> Screen:
        return Screen(self._stack.currentIndex())

    @property
    def worker(self) -> DocumentProcessWorker | None:
        return self._worker

    @property
    def tokens(self) -> ThemeTokens:
        return THEMES[self._theme]

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _build_ui(self) -> None:
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.setWindowTitle("ClearRead")
        self.home_view = HomeView(self.tokens, self._language)
        self.processing_view = ProcessingView(self._language)
        self.reading_view = ReadingView(self._tts, self._theme, self._language)
        self._stack = QStackedWidget()
        for view in (self.home_view, self.processing_view, self.reading_view):
            self._stack.addWidget(view)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_top_bar())
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self.home_view.file_chosen.connect(self.open_document)
        self.home_view.recent_open_requested.connect(self.open_recent)
        self.home_view.recent_remove_requested.connect(self.remove_recent)
        self.processing_view.cancel_requested.connect(self.cancel_processing)
        self.back_button.clicked.connect(self.go_back)
        shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        shortcut.activated.connect(self.go_back)

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(TOP_BAR_HEIGHT)
        self.back_button = QPushButton(self._t("nav.back_home"))
        self.back_button.setToolTip(f"{self._t('nav.back_home')} (Alt+←)")
        self.brand_label = QLabel("ClearRead")
        self.brand_label.setObjectName("Brand")
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 0, 24, 0)
        row.addWidget(self.back_button)
        row.addWidget(self.brand_label)
        row.addWidget(self.title_label, stretch=1)
        return bar

    def show_screen(self, screen: Screen) -> None:
        self._stack.setCurrentIndex(screen.value)
        reading = screen is Screen.READING
        self.back_button.setVisible(reading)
        self.brand_label.setVisible(not reading)
        self.title_label.setVisible(reading)
        if screen is Screen.HOME:
            self.home_view.set_recents(self._library.recents(), local_today())
            self.home_view.choose_button.setFocus()
        elif screen is Screen.READING:
            self.reading_view.editor.setFocus()

    def open_document(self, path: str) -> None:
        if self._worker is not None:
            return
        source = Path(path)
        try:
            key = compute_cache_key(source)
        except OSError:
            self._show_error(ProcessingErrorKind.FILE_NOT_FOUND)
            return
        if self._library.has(key) and self._show_cached(key, source.name):
            self._library.touch(key)
            return
        self._pending = (source, key)
        self._start_worker(source)

    def _start_worker(self, source: Path) -> None:
        formatter = TextFormatter(self._syllabifier, syllable_palette(self.tokens))
        worker = DocumentProcessWorker(
            str(source),
            self._ingestor,
            self._preprocessor,
            self._ocr_engine,
            formatter,
        )
        worker.progress_changed.connect(self.processing_view.set_progress)
        worker.formatting_started.connect(self.processing_view.set_preparing)
        worker.document_ready.connect(self._on_document_ready)
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(lambda: self._on_worker_finished(worker))
        self._worker = worker
        self.processing_view.start(source.name)
        self.show_screen(Screen.PROCESSING)
        worker.start()

    def _on_worker_finished(self, worker: DocumentProcessWorker) -> None:
        self._retired_workers.discard(worker)
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def cancel_processing(self) -> None:
        worker = self._worker
        if worker is None:
            return
        worker.cancel()
        self._detach(worker)
        self.show_screen(Screen.HOME)

    def _detach(self, worker: DocumentProcessWorker) -> None:
        for signal in (
            worker.progress_changed,
            worker.formatting_started,
            worker.document_ready,
            worker.error_occurred,
        ):
            signal.disconnect()
        self._retired_workers.add(worker)
        self._worker = None
        self._pending = None

    def _release_worker(self) -> tuple[Path, str] | None:
        """Stop tracking the finished worker as current but keep it joinable on close."""
        if self._worker is not None:
            self._retired_workers.add(self._worker)
            self._worker = None
        pending, self._pending = self._pending, None
        return pending

    def _on_document_ready(self, processed: ProcessedDocument) -> None:
        pending = self._release_worker()
        if pending is None:
            return
        source, key = pending
        cached = CachedDocument(
            processed.raw_text, processed.formatted, self._theme.value
        )
        self._library.store(
            key, source, cached, processed.page_count, processed.is_photo
        )
        self._show_reading(processed.formatted, source.name)

    def _on_error(self, kind_value: str) -> None:
        if self._release_worker() is None:
            return
        self.show_screen(Screen.HOME)
        self._show_error(ProcessingErrorKind(kind_value))

    def open_recent(self, key: str) -> None:
        recent = next((r for r in self._library.recents() if r.key == key), None)
        if recent is None or not self._show_cached(key, recent.name):
            self._library.remove(key)
            self.show_screen(Screen.HOME)
            self._show_error(ProcessingErrorKind.UNREADABLE)
            return
        self._library.touch(key)

    def _show_cached(self, key: str, name: str) -> bool:
        cached = self._library.load(key)
        if cached is None:
            return False
        formatted = cached.formatted
        if cached.theme != self._theme.value:
            formatted = self._format(cached.raw_text)
        self._show_reading(formatted, name)
        return True

    def _format(self, raw_text: str) -> FormattedDocument:
        formatter = TextFormatter(self._syllabifier, syllable_palette(self.tokens))
        return formatter.format_document(raw_text)

    def _show_reading(self, formatted: FormattedDocument, name: str) -> None:
        self.reading_view.load_document(formatted)
        shown = name if len(name) <= TITLE_MAX_CHARS else name[:TITLE_MAX_CHARS] + "…"
        self.title_label.setText(shown)
        self.show_screen(Screen.READING)

    def remove_recent(self, key: str) -> None:
        self._library.remove(key)
        self.home_view.set_recents(self._library.recents(), local_today())

    def go_back(self) -> None:
        if self.screen_shown is Screen.PROCESSING:
            self.cancel_processing()
        elif self.screen_shown is Screen.READING:
            self.reading_view.stop_reading()
            self.show_screen(Screen.HOME)

    def _show_error(self, kind: ProcessingErrorKind) -> None:
        dialog = AccessibleErrorDialog(self, kind, self.tokens, self._language)
        dialog.finished.connect(lambda: self._on_error_closed(dialog))
        self.error_dialog = dialog
        dialog.open()

    def _on_error_closed(self, dialog: AccessibleErrorDialog) -> None:
        wants_other = dialog.choose_other_requested
        dialog.deleteLater()
        if self.error_dialog is dialog:
            self.error_dialog = None
        if wants_other:
            self.home_view.choose_file()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._tts.stop()
        if self._worker is not None:
            self._worker.cancel()
            self._detach(self._worker)
        for worker in list(self._retired_workers):
            worker.wait()
        self._tts.shutdown()
        event.accept()
