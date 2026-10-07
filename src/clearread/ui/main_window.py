"""Main window: Home -> Processing -> Reading, plus Settings and My words (design system 7)."""

from dataclasses import replace
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
from clearread.core.paths import get_resource_path
from clearread.services.ai_client import AIClient
from clearread.services.document_library import (
    CachedDocument,
    DocumentLibrary,
    compute_cache_key,
)
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.services.ingestor import DocumentIngestor
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import OCREngine
from clearread.services.preprocessor import OCRPreprocessor
from clearread.services.reading_stats import StatsStore
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FormattedDocument,
    ReadingStyle,
    TextFormatter,
)
from clearread.services.tts_controller import TTSController
from clearread.ui.ai_assistant import AIAssistant
from clearread.ui.dialogs import AccessibleErrorDialog
from clearread.ui.focus_ring import KeyboardFocusRing
from clearread.ui.icons import load_icon
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
from clearread.ui.views.settings_view import SettingsView
from clearread.ui.views.words_view import WordsView
from clearread.workers.ocr_worker import (
    DocumentProcessWorker,
    ProcessedDocument,
    ProcessingErrorKind,
)

MIN_WINDOW_SIZE = (1024, 700)
TOP_BAR_HEIGHT = 56
TITLE_MAX_CHARS = 60
SAMPLE_RESOURCE = Path("resources") / "samples" / "ejemplo_es.txt"


class Screen(Enum):
    HOME = 0
    PROCESSING = 1
    READING = 2
    SETTINGS = 3
    WORDS = 4


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: AppConfig,
        ocr_engine: OCREngine,
        tts: TTSController,
        library: DocumentLibrary,
        config_dir: Path | None = None,
        ai_client: AIClient | None = None,
        network: NetworkMonitor | None = None,
        glossary: GlossaryStore | None = None,
        stats: StatsStore | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._config_dir = config_dir
        self._language = Language(config.ui_language)
        self._theme = ThemeId(config.theme)
        self._ocr_engine = ocr_engine
        self._tts = tts
        self._library = library
        self._glossary = glossary or GlossaryStore()
        self._stats = stats or StatsStore()
        self._ingestor = DocumentIngestor()
        self._preprocessor = OCRPreprocessor()
        self._syllabifier = SpanishSyllabifier()
        self._worker: DocumentProcessWorker | None = None
        self._retired_workers: set[DocumentProcessWorker] = set()
        self._pending: tuple[Path, str] | None = None
        self._raw_text: str | None = None  # text of the document in the reading view
        self._reading_title = ""
        self._reading_key: str | None = None
        self._settings_origin = Screen.HOME
        self._words_origin = Screen.HOME
        self._online = network.is_online if network else True
        self.assistant: AIAssistant | None = None
        self.error_dialog: AccessibleErrorDialog | None = None
        self._focus_ring = KeyboardFocusRing(self)
        self._build_ui()
        self._build_assistant(ai_client, network)
        self.setStyleSheet(build_stylesheet(self.tokens))
        self._apply_speech_settings()
        self._refresh_reading()
        self._install_focus_ring()
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

    def _install_focus_ring(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._focus_ring)

    def _build_ui(self) -> None:
        self.setMinimumSize(*MIN_WINDOW_SIZE)
        self.setWindowTitle("ClearRead")
        self.home_view = HomeView(self.tokens, self._language)
        self.processing_view = ProcessingView(self._language)
        self.reading_view = ReadingView(self._tts, self._theme, self._language)
        self.settings_view = SettingsView(
            replace(self._config), self._language, self._syllabifier
        )
        self.words_view = WordsView(self.tokens, self._language)
        self.words_view.set_entries(self._glossary.entries())
        self._stack = QStackedWidget()
        for view in (
            self.home_view,
            self.processing_view,
            self.reading_view,
            self.settings_view,
            self.words_view,
        ):
            self._stack.addWidget(view)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_top_bar())
        layout.addWidget(self._stack, stretch=1)
        self.setCentralWidget(central)

        self.home_view.file_chosen.connect(self.open_document)
        self.home_view.sample_requested.connect(self.open_sample)
        self.home_view.recent_open_requested.connect(self.open_recent)
        self.home_view.recent_remove_requested.connect(self.remove_recent)
        self.processing_view.cancel_requested.connect(self.cancel_processing)
        self.reading_view.speed_changed.connect(self._on_reading_speed_changed)
        self.reading_view.reading_session.connect(self._on_reading_session)
        self.settings_view.config_changed.connect(self._on_settings_changed)
        self.settings_view.clear_recents_requested.connect(self.clear_recents)
        self.settings_view.back_requested.connect(self.go_back)
        self.settings_view.set_voices(self._tts.voices)
        self._tts.voices_listed.connect(self.settings_view.set_voices)
        self.words_view.listen_requested.connect(self.reading_view.speak_aside)
        self.words_view.delete_requested.connect(self.delete_word)
        self.back_button.clicked.connect(self.go_back)
        self.settings_button.clicked.connect(self.open_settings)
        self.words_button.clicked.connect(self.open_words)
        for sequence, slot in (
            ("Alt+Left", self.go_back),
            ("Ctrl+,", self.open_settings),
            ("Ctrl+I", self.toggle_assistant),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

    def _build_assistant(
        self, client: AIClient | None, network: NetworkMonitor | None
    ) -> None:
        if client is None:
            return
        self.assistant = AIAssistant(
            client,
            self.reading_view,
            self._config.ai_privacy_accepted,
            parent=self,
            saves_words=True,
        )
        self.assistant.privacy_accepted.connect(self._on_privacy_accepted)
        self.assistant.word_explained.connect(self._on_word_explained)
        self.assistant_button.clicked.connect(self.toggle_assistant)
        self.reading_view.assistant_open_changed.connect(
            self.assistant_button.setChecked
        )
        if network is not None:
            network.online_changed.connect(self._on_online_changed)
        self.assistant.set_online(self._online)
        self._refresh_assistant_button()

    def toggle_assistant(self) -> None:
        if self.assistant is not None and self.screen_shown is Screen.READING:
            self.assistant.toggle_panel()

    def _on_online_changed(self, online: bool) -> None:
        self._online = online
        if self.assistant is not None:
            self.assistant.set_online(online)
        self._refresh_assistant_button()

    def _refresh_assistant_button(self) -> None:
        available = self.assistant is not None and self.screen_shown is Screen.READING
        self.assistant_button.setVisible(available)
        self.assistant_button.setEnabled(self._online)
        self.offline_badge.setVisible(available and not self._online)
        tooltip_key = "ai.toggle_tooltip" if self._online else "ai.offline_tooltip"
        self.assistant_button.setToolTip(self._t(tooltip_key))
        self.assistant_button.setIcon(load_icon("assistant", self.tokens.secondary))

    def _on_privacy_accepted(self) -> None:
        self._config.ai_privacy_accepted = True
        self._save_config()

    def _on_word_explained(self, word: str, explanation: str) -> None:
        self._glossary.add(
            GlossaryEntry(
                word=word,
                explanation=explanation,
                document=self._reading_title,
                added_on=local_today().isoformat(),
            )
        )
        self.words_view.set_entries(self._glossary.entries())

    def delete_word(self, word: str) -> None:
        self._glossary.remove(word)
        self.words_view.set_entries(self._glossary.entries())

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(TOP_BAR_HEIGHT)
        self.back_button = QPushButton()
        self.settings_button = QPushButton(self._t("nav.settings"))
        self.settings_button.setProperty("variant", "ghost")
        self.settings_button.setIcon(load_icon("settings", self.tokens.secondary))
        self.settings_button.setToolTip(f"{self._t('nav.settings')} (Ctrl+,)")
        self.words_button = QPushButton(self._t("nav.my_words"))
        self.words_button.setProperty("variant", "ghost")
        self.words_button.setIcon(load_icon("words", self.tokens.secondary))
        self.assistant_button = QPushButton(self._t("nav.assistant"))
        self.assistant_button.setObjectName("AssistantToggle")
        self.assistant_button.setCheckable(True)
        self.assistant_button.hide()
        self.offline_badge = QLabel(self._t("ai.offline_badge"))
        self.offline_badge.setObjectName("OfflineBadge")
        self.offline_badge.hide()
        self.brand_label = QLabel("ClearRead")
        self.brand_label.setObjectName("Brand")
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 0, 24, 0)
        row.addWidget(self.back_button)
        row.addWidget(self.brand_label, stretch=1)
        row.addWidget(self.title_label, stretch=1)
        row.addWidget(self.offline_badge)
        row.addWidget(self.assistant_button)
        row.addWidget(self.words_button)
        row.addWidget(self.settings_button)
        return bar

    def show_screen(self, screen: Screen) -> None:
        self._stack.setCurrentIndex(screen.value)
        has_title = screen in (Screen.READING, Screen.SETTINGS, Screen.WORDS)
        self.back_button.setVisible(has_title)
        self.brand_label.setVisible(not has_title)
        self.title_label.setVisible(has_title)
        self.settings_button.setVisible(screen not in (Screen.SETTINGS, Screen.WORDS))
        self.settings_button.setEnabled(screen is not Screen.PROCESSING)
        self.words_button.setVisible(screen in (Screen.HOME, Screen.READING))
        if self.assistant is not None:
            self._refresh_assistant_button()
        if has_title:
            self._show_title(screen)
        if screen is Screen.HOME:
            self._refresh_home()
            self.home_view.choose_button.setFocus()
        elif screen is Screen.READING:
            self.reading_view.editor.setFocus()

    def _refresh_home(self) -> None:
        self.home_view.set_recents(self._library.recents(), local_today())
        self.home_view.set_stats(self._stats.stats)

    def _show_title(self, screen: Screen) -> None:
        back_key = "nav.back_home" if screen is Screen.READING else "nav.back"
        titles = {
            Screen.READING: self._reading_title,
            Screen.SETTINGS: self._t("settings.title"),
            Screen.WORDS: self._t("words.title"),
        }
        self.back_button.setText(self._t(back_key))
        self.back_button.setToolTip(f"{self._t(back_key)} (Alt+←)")
        self.title_label.setText(titles[screen])

    def open_settings(self) -> None:
        if self.screen_shown in (Screen.HOME, Screen.READING):
            self._settings_origin = self.screen_shown
            self.show_screen(Screen.SETTINGS)

    def open_words(self) -> None:
        if self.screen_shown in (Screen.HOME, Screen.READING):
            self._words_origin = self.screen_shown
            self.words_view.set_entries(self._glossary.entries())
            self.show_screen(Screen.WORDS)

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

    def open_sample(self) -> None:
        """Open the bundled Spanish example: its text needs no OCR."""
        if self._worker is not None:
            return
        source = get_resource_path(SAMPLE_RESOURCE)
        name = self._t("home.sample_title")
        try:
            key = compute_cache_key(source)
            raw_text = source.read_text(encoding="utf-8")
        except OSError:
            self._show_error(ProcessingErrorKind.FILE_NOT_FOUND)
            return
        if self._library.has(key) and self._show_cached(key, name):
            self._library.touch(key)
            return
        formatted = self._format(raw_text)
        cached = CachedDocument(raw_text, formatted, self._appearance_key())
        self._library.store(key, source, cached, 1, False, display_name=name)
        self._show_reading(formatted, name, raw_text, key)

    def _start_worker(self, source: Path) -> None:
        formatter = self._make_formatter()
        worker = DocumentProcessWorker(
            str(source),
            self._ingestor,
            self._preprocessor,
            self._ocr_engine,
            formatter,
            self._config.syllables_enabled,
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
            processed.raw_text, processed.formatted, self._appearance_key()
        )
        self._library.store(
            key, source, cached, processed.page_count, processed.is_photo
        )
        self._show_reading(processed.formatted, source.name, processed.raw_text, key)

    def _on_error(self, kind_value: str) -> None:
        if self._release_worker() is None:
            return
        self.show_screen(Screen.HOME)
        self._show_error(ProcessingErrorKind(kind_value))

    def open_recent(self, key: str) -> None:
        recent = self._library.recent(key)
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
        if cached.appearance != self._appearance_key():
            formatted = self._format(cached.raw_text)
        recent = self._library.recent(key)
        position = recent.position if recent else 0
        self._show_reading(formatted, name, cached.raw_text, key, position)
        return True

    def _style(self) -> ReadingStyle:
        return ReadingStyle(
            font_family=self._config.reading_font,
            font_size_pt=self._config.font_size_pt,
            letter_spacing_em=self._config.letter_spacing_em,
            word_spacing_em=self._config.word_spacing_em,
        )

    def _appearance_key(self, config: AppConfig | None = None) -> str:
        config = config or self._config
        return (
            f"{config.theme}|{config.reading_font}|{config.font_size_pt}|"
            f"{config.letter_spacing_em:g}|{config.word_spacing_em:g}|"
            f"{config.syllables_enabled}"
        )

    def _make_formatter(self) -> TextFormatter:
        return TextFormatter(
            self._syllabifier, syllable_palette(self.tokens), self._style()
        )

    def _format(self, raw_text: str) -> FormattedDocument:
        return self._make_formatter().format_document(
            raw_text, self._config.syllables_enabled
        )

    def _show_reading(
        self,
        formatted: FormattedDocument,
        name: str,
        raw_text: str,
        key: str | None = None,
        position: int = 0,
    ) -> None:
        self._save_position()
        self._raw_text = raw_text
        self.reading_view.load_document(formatted, position)
        self._reading_key = key
        self._reading_title = (
            name if len(name) <= TITLE_MAX_CHARS else name[:TITLE_MAX_CHARS] + "…"
        )
        self.show_screen(Screen.READING)

    def _save_position(self) -> None:
        """Remember where the open document was left (READ-F01)."""
        if self._reading_key and self.reading_view.token_map:
            self._library.set_position(
                self._reading_key, self.reading_view.resume_index
            )

    def _on_reading_session(self, words: int, seconds: float) -> None:
        self._stats.add(words, seconds)
        self._save_position()

    def _refresh_reading(self) -> None:
        """Re-render the open document: same text, so the token map stays valid."""
        html = self._format(self._raw_text).html_content if self._raw_text else ""
        self.reading_view.apply_appearance(
            self._theme, self._style(), self._config.line_spacing, html
        )

    def _apply_speech_settings(self) -> None:
        self._tts.set_voice(self._config.voice_id)
        self.reading_view.set_speed(self._config.reading_speed_wpm)

    def _on_settings_changed(self, new: AppConfig) -> None:
        old = self._config
        # The settings screen keeps its own copy, which never learns about the notice.
        new = replace(new, ai_privacy_accepted=old.ai_privacy_accepted)
        self._config = new
        if new.theme != old.theme:
            self._theme = ThemeId(new.theme)
            self.setStyleSheet(build_stylesheet(self.tokens))
            self.home_view.apply_theme(self.tokens)
            self.words_view.apply_theme(self.tokens)
            self.settings_button.setIcon(load_icon("settings", self.tokens.secondary))
            self.words_button.setIcon(load_icon("words", self.tokens.secondary))
            self._refresh_assistant_button()
        if (
            self._appearance_key(old) != self._appearance_key()
            or old.line_spacing != new.line_spacing
        ):
            self._refresh_reading()
        if new.reading_speed_wpm != old.reading_speed_wpm:
            self.reading_view.set_speed(new.reading_speed_wpm)
        if new.voice_id != old.voice_id:
            self._tts.set_voice(new.voice_id)
        self._save_config()

    def _on_reading_speed_changed(self, wpm: int) -> None:
        if wpm == self._config.reading_speed_wpm:
            return
        self._config.reading_speed_wpm = wpm
        self.settings_view.set_speed(wpm)
        self._save_config()

    def _save_config(self) -> None:
        try:
            self._config.save(self._config_dir)
        except OSError:
            self.settings_view.show_save_error(True)
        else:
            self.settings_view.show_save_error(False)

    def clear_recents(self) -> None:
        self._library.clear()
        self.home_view.set_recents([], local_today())
        self.settings_view.show_recents_cleared()

    def remove_recent(self, key: str) -> None:
        self._library.remove(key)
        self._refresh_home()

    def go_back(self) -> None:
        if self.screen_shown is Screen.PROCESSING:
            self.cancel_processing()
        elif self.screen_shown is Screen.SETTINGS:
            self.show_screen(self._settings_origin)
        elif self.screen_shown is Screen.WORDS:
            self.reading_view.stop_aside()
            self.show_screen(self._words_origin)
        elif self.screen_shown is Screen.READING:
            self.reading_view.stop_reading()
            self.reading_view.set_assistant_open(False)
            self._save_position()
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
        self.reading_view.stop_reading()
        self._save_position()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._focus_ring)
        if self._worker is not None:
            self._worker.cancel()
            self._detach(self._worker)
        for worker in list(self._retired_workers):
            worker.wait()
        self._tts.shutdown()
        event.accept()
