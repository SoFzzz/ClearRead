"""Main window: Home -> Processing -> Reading, plus Settings and My words (design system 7)."""

from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clearread.core.config import FONT_SIZE_RANGE_PT, AppConfig
from clearread.core.paths import get_resource_path
from clearread.services.account_client import AccountErrorKind
from clearread.services.ai_client import AIClient
from clearread.services.document_library import (
    CachedDocument,
    DocumentLibrary,
    RecentDocument,
    compute_cache_key,
)
from clearread.services.glossary import GlossaryEntry, GlossaryStore
from clearread.services.groups import (
    NO_GROUP,
    GroupStore,
)
from clearread.services.ingestor import DocumentIngestor
from clearread.services.network_monitor import NetworkMonitor
from clearread.services.ocr_engine import OCREngine
from clearread.services.preprocessor import OCRPreprocessor
from clearread.services.profile_sync import MACHINE_SPECIFIC_FIELDS
from clearread.services.reading_stats import StatsStore
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FormattedDocument,
    ReadingStyle,
    TextFormatter,
)
from clearread.services.tts_controller import TTSController, VoiceInfo, choose_voice
from clearread.ui.account_state import AccountInfo, SyncStatus
from clearread.ui.ai_assistant import AIAssistant
from clearread.ui.dialogs import (
    AccessibleErrorDialog,
    NamePromptDialog,
    make_info_box,
)
from clearread.ui.focus_ring import KeyboardFocusRing
from clearread.ui.icons import load_icon
from clearread.ui.library_controller import LibraryController
from clearread.ui.processing_runner import PendingDocument, ProcessingRunner
from clearread.ui.strings import Language, tr
from clearread.ui.theme import (
    THEMES,
    ThemeId,
    ThemeTokens,
    build_stylesheet,
    syllable_palette,
)
from clearread.ui.views.home_view import HomeView, ProcessingView, local_today
from clearread.ui.views.reading_view import (
    ZOOM_RESET,
    ReadingView,
    ViewMode,
)
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


def _synced_part(config: AppConfig) -> dict[str, object]:
    return {
        key: value
        for key, value in asdict(config).items()
        if key not in MACHINE_SPECIFIC_FIELDS
    }


class Screen(Enum):
    HOME = 0
    PROCESSING = 1
    READING = 2
    SETTINGS = 3
    WORDS = 4


class MainWindow(QMainWindow):
    # A local change of the synced profile: settings, words or topics.
    profile_changed = Signal()
    device_preferences_changed = Signal(str, str)  # theme, interface language
    sign_out_requested = Signal()
    delete_account_requested = Signal()
    google_link_requested = Signal()
    google_cancel_requested = Signal()
    session_check_requested = Signal()  # the assistant was told to sign in again

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
        folders: GroupStore | None = None,
        topics: GroupStore | None = None,
        account: AccountInfo | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._account = account
        self._config_dir = config_dir
        self._language = Language(config.ui_language)
        self._theme = ThemeId(config.theme)
        self._ocr_engine = ocr_engine
        self._tts = tts
        self._library = library
        self._glossary = glossary or GlossaryStore()
        self._stats = stats or StatsStore()
        self._folders = folders or GroupStore()
        self._topics = topics or GroupStore()
        self._ingestor = DocumentIngestor()
        self._preprocessor = OCRPreprocessor()
        self._syllabifier = SpanishSyllabifier()
        self._raw_text: str | None = None  # text of the document in the reading view
        self._reading_title = ""
        self._reading_key: str | None = None
        self._settings_origin = Screen.HOME
        self._words_origin = Screen.HOME
        self._online = network.is_online if network else True
        self.assistant: AIAssistant | None = None
        self.error_dialog: AccessibleErrorDialog | None = None
        self.notice_box: QMessageBox | None = None
        self.restart_requested = False  # read by main() once the event loop ends
        self._focus_ring = KeyboardFocusRing(self)
        self._build_ui()
        self._build_assistant(ai_client)
        if network is not None:
            network.online_changed.connect(self._on_online_changed)
        self.settings_view.set_online(self._online)
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
        return self._runner.worker

    @property
    def _retired_workers(self) -> set[DocumentProcessWorker]:
        return self._runner.retired_workers

    @property
    def confirm_box(self) -> QMessageBox | None:
        return self._library_controller.confirm_box

    @property
    def prompt_dialog(self) -> NamePromptDialog | None:
        return self._library_controller.prompt_dialog

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
        self.reading_view = ReadingView(
            self._tts,
            self._theme,
            self._language,
            view_mode=ViewMode(self._config.reading_view_mode),
        )
        self.settings_view = SettingsView(
            replace(self._config), self._language, self._syllabifier, self._account
        )
        self.words_view = WordsView(self.tokens, self._language)
        self._library_controller = LibraryController(
            self,
            self._language,
            self._library,
            self._folders,
            self._topics,
            self._glossary,
            self.words_view,
            self._refresh_home,
            self.profile_changed.emit,
        )
        self._library_controller.refresh_words()
        self._runner = ProcessingRunner(
            self.processing_view,
            self._ingestor,
            self._preprocessor,
            self._ocr_engine,
            self._on_document_ready,
            self._on_error,
        )
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
        self.home_view.recent_remove_requested.connect(self.ask_remove_document)
        self.home_view.recent_move_requested.connect(self.move_document)
        self.home_view.folder_add_requested.connect(self.create_folder)
        self.home_view.folder_rename_requested.connect(self.rename_folder)
        self.home_view.folder_delete_requested.connect(self.ask_delete_folder)
        self.processing_view.cancel_requested.connect(self.cancel_processing)
        self.reading_view.speed_changed.connect(self._on_reading_speed_changed)
        self.reading_view.reading_session.connect(self._on_reading_session)
        self.reading_view.view_mode_changed.connect(self._on_view_mode_changed)
        self.reading_view.zoom_requested.connect(self._on_zoom_requested)
        self.reading_view.syllables_toggled.connect(self._on_syllables_toggled)
        self.settings_view.config_changed.connect(self._on_settings_changed)
        self.settings_view.clear_recents_requested.connect(self.clear_recents)
        self.settings_view.back_requested.connect(self.go_back)
        self.settings_view.restart_requested.connect(self._restart)
        self.settings_view.sign_out_requested.connect(self.sign_out_requested)
        self.settings_view.delete_account_requested.connect(
            self.delete_account_requested
        )
        self.settings_view.google_link_requested.connect(self.google_link_requested)
        self.settings_view.google_cancel_requested.connect(self.google_cancel_requested)
        self.settings_view.set_voices(self._tts.voices)
        self._tts.voices_listed.connect(self.settings_view.set_voices)
        self.words_view.listen_requested.connect(self.reading_view.speak_aside)
        self.words_view.delete_requested.connect(
            self._library_controller.ask_delete_word
        )
        self.words_view.topic_changed.connect(self._library_controller.set_word_topic)
        self.words_view.topic_add_requested.connect(
            self._library_controller.create_topic
        )
        self.words_view.topic_rename_requested.connect(self.rename_topic)
        self.words_view.topic_delete_requested.connect(self.ask_delete_topic)
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

    def _build_assistant(self, client: AIClient | None) -> None:
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
        self.assistant.sign_in_required.connect(self.session_check_requested)
        self.assistant_button.clicked.connect(self.toggle_assistant)
        self.reading_view.assistant_open_changed.connect(
            self.assistant_button.setChecked
        )
        self.assistant.set_online(self._online)
        self._refresh_assistant_button()

    def toggle_assistant(self) -> None:
        if self.assistant is not None and self.screen_shown is Screen.READING:
            self.assistant.toggle_panel()

    def _on_online_changed(self, online: bool) -> None:
        self._online = online
        self.settings_view.set_online(online)
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
                topic=self._default_topic(),
            )
        )
        self._library_controller.refresh_words()
        self.profile_changed.emit()

    def _default_topic(self) -> str:
        """The topic named like the folder of the open document, if there is one."""
        entry = self._library.recent(self._reading_key) if self._reading_key else None
        folder = self._folders.get(entry.folder_id) if entry else None
        topic = self._topics.find_by_name(folder.name) if folder else None
        return topic.id if topic else NO_GROUP

    def _refresh_words(self) -> None:
        self.words_view.set_entries(self._glossary.entries(), self._topics.groups())

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
        self.home_view.set_recents(
            self._library.recents(), local_today(), self._folders.groups()
        )
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
            self._library_controller.refresh_words()
            self.show_screen(Screen.WORDS)

    def open_document(self, path: str) -> None:
        if self._runner.worker is not None:
            return
        source = Path(path)
        try:
            key = compute_cache_key(source)
        except OSError:
            self._show_error(ProcessingErrorKind.FILE_NOT_FOUND)
            return
        if self._library.has(key) and self._show_cached(key, source.name):
            self._library.touch(key)
            self._announce_stored(key, True)
            return
        self._start_worker(
            PendingDocument(source, key, self.home_view.current_folder_id)
        )

    def open_sample(self) -> None:
        """Open the bundled Spanish example: its text needs no OCR."""
        if self._runner.worker is not None:
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
            self._announce_stored(key, True)
            return
        formatted = self._format(raw_text)
        cached = CachedDocument(raw_text, formatted, self._appearance_key())
        self._library.store(
            key,
            source,
            cached,
            1,
            False,
            display_name=name,
            folder_id=self.home_view.current_folder_id,
        )
        self._announce_stored(key, False)
        self._show_reading(formatted, name, raw_text, key)

    def _announce_stored(self, key: str, already: bool) -> None:
        """A document already in the library keeps its folder, whatever the destination."""
        stored = self._library.recent(key)
        if stored is not None:
            self.home_view.confirm_saved(stored.folder_id, already)

    def _start_worker(self, pending: PendingDocument) -> None:
        self._runner.start(
            pending,
            self._make_formatter(),
            self._config.syllables_enabled,
            lambda: self.show_screen(Screen.PROCESSING),
        )

    def cancel_processing(self) -> None:
        if self._runner.cancel():
            self.show_screen(Screen.HOME)

    def _on_document_ready(
        self, processed: ProcessedDocument, pending: PendingDocument
    ) -> None:
        cached = CachedDocument(
            processed.raw_text, processed.formatted, self._appearance_key()
        )
        self._library.store(
            pending.key,
            pending.source,
            cached,
            processed.page_count,
            processed.is_photo,
            folder_id=pending.folder_id,
        )
        self._announce_stored(pending.key, False)
        self._show_reading(
            processed.formatted, pending.source.name, processed.raw_text, pending.key
        )

    def _on_error(self, kind: ProcessingErrorKind) -> None:
        self.show_screen(Screen.HOME)
        self._show_error(kind)

    def open_recent(self, key: str) -> None:
        recent = self._library.recent(key)
        if recent is None:
            self._refresh_home()
            self._show_error(ProcessingErrorKind.UNREADABLE)
            return
        if self._library.needs_processing(key) or not self._show_cached(
            recent.key, recent.name
        ):
            self._reprocess(recent)
            return
        self._library.touch(key)

    def _reprocess(self, recent: RecentDocument) -> None:
        """The cache is missing or outdated: build it again from the original file."""
        if Path(recent.path).name == SAMPLE_RESOURCE.name:
            self.open_sample()
        elif Path(recent.path).is_file():
            self.open_document(recent.path)
        else:
            self._show_error(
                ProcessingErrorKind.LIBRARY_FILE_MISSING, remove_key=recent.key
            )

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
        self.reading_view.set_syllables_checked(self._config.syllables_enabled)

    def _on_settings_changed(self, new: AppConfig) -> None:
        old = self._config
        # The settings screen keeps its own copy, which never learns about the notice.
        new = replace(
            new,
            ai_privacy_accepted=old.ai_privacy_accepted,
            reading_view_mode=old.reading_view_mode,
        )
        self._apply_config(new)
        if _synced_part(old) == _synced_part(new):
            self._persist_config()  # only this computer's own settings changed
        else:
            self._save_config()

    def _apply_config(self, new: AppConfig) -> None:
        old = self._config
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
        self.reading_view.set_syllables_checked(new.syllables_enabled)
        if new.reading_speed_wpm != old.reading_speed_wpm:
            self.reading_view.set_speed(new.reading_speed_wpm)
        if new.voice_id != old.voice_id:
            self._tts.set_voice(new.voice_id)

    def apply_remote_config(self, config: AppConfig) -> None:
        """The account's profile won a sync: show it, without sending it back."""
        self._apply_config(config)
        self.settings_view.set_config(replace(config))
        self._library_controller.refresh_words()
        self._persist_config()
        if config.ui_language != self._language.value:
            self.show_notice("profile.language_pending")

    def show_notice(self, key: str) -> None:
        box = make_info_box(self, self._t(key), self._language)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.finished.connect(lambda: self._forget_notice(box))
        self.notice_box = box
        box.open()

    def _forget_notice(self, box: QMessageBox) -> None:
        if self.notice_box is box:
            self.notice_box = None

    @property
    def config(self) -> AppConfig:
        return replace(self._config)

    def set_account(self, account: AccountInfo) -> None:
        self.settings_view.set_account(account)

    def set_sync_status(self, status: SyncStatus) -> None:
        self.settings_view.set_sync_status(status)

    def set_account_busy(self, busy: bool) -> None:
        self.settings_view.set_account_busy(busy)

    def show_account_error(self, kind: AccountErrorKind) -> None:
        self.settings_view.show_account_error(kind)

    def set_google_starting(self, starting: bool) -> None:
        self.settings_view.set_google_starting(starting)

    def show_google_waiting(self) -> None:
        self.settings_view.show_google_waiting()

    def close_google_waiting(self) -> None:
        self.settings_view.close_google_waiting()

    def follow_language_voice(self) -> None:
        """Keep the reading voice in the interface language, now and once voices are listed."""
        self._tts.voices_listed.connect(self._adopt_language_voice)
        if self._tts.voices:
            self._adopt_language_voice(self._tts.voices)

    def _adopt_language_voice(self, voices: list[VoiceInfo]) -> None:
        chosen = choose_voice(voices, self._config.ui_language, self._config.voice_id)
        if chosen == self._config.voice_id:
            return
        self._config.voice_id = chosen
        self._tts.set_voice(chosen)
        self.settings_view.set_config(replace(self._config))
        self._persist_config()  # the voice belongs to this computer, not to the profile

    def _on_reading_speed_changed(self, wpm: int) -> None:
        if wpm == self._config.reading_speed_wpm:
            return
        self._config.reading_speed_wpm = wpm
        self.settings_view.set_speed(wpm)
        self._save_config()

    def _on_view_mode_changed(self, mode_value: str) -> None:
        self._config.reading_view_mode = mode_value
        self._save_config()

    def _on_zoom_requested(self, direction: int) -> None:
        """Ctrl++ / Ctrl+- move the size one step; Ctrl+0 goes back to the default."""
        size = (
            AppConfig().font_size_pt
            if direction == ZOOM_RESET
            else self._config.font_size_pt + direction
        )
        size = max(FONT_SIZE_RANGE_PT[0], min(FONT_SIZE_RANGE_PT[1], size))
        if size == self._config.font_size_pt:
            return
        resized = replace(self._config, font_size_pt=size)
        self.settings_view.set_config(replace(resized))
        self._on_settings_changed(resized)

    def _on_syllables_toggled(self, enabled: bool) -> None:
        if enabled == self._config.syllables_enabled:
            return
        changed = replace(self._config, syllables_enabled=enabled)
        self.settings_view.set_config(replace(changed))
        self._on_settings_changed(changed)

    def _restart(self) -> None:
        self.restart_requested = True
        self.close()

    def _save_config(self) -> None:
        self._persist_config()
        self.profile_changed.emit()

    def _persist_config(self) -> None:
        self.device_preferences_changed.emit(
            self._config.theme, self._config.ui_language
        )
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

    def ask_remove_document(self, key: str) -> None:
        self._library_controller.ask_remove_document(key)

    def remove_recent(self, key: str) -> None:
        self._library_controller.remove_recent(key)

    def move_document(self, key: str, folder_id: str) -> None:
        self._library_controller.move_document(key, folder_id)

    def create_folder(self) -> None:
        self._library_controller.create_folder()

    def rename_folder(self, folder_id: str) -> None:
        self._library_controller.rename_folder(folder_id)

    def ask_delete_folder(self, folder_id: str) -> None:
        self._library_controller.ask_delete_folder(folder_id)

    def rename_topic(self, topic_id: str) -> None:
        self._library_controller.rename_topic(topic_id)

    def ask_delete_topic(self, topic_id: str) -> None:
        self._library_controller.ask_delete_topic(topic_id)

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

    def _show_error(
        self, kind: ProcessingErrorKind, remove_key: str | None = None
    ) -> None:
        """With ``remove_key`` the dialog offers to take that document out of the library."""
        dialog = AccessibleErrorDialog(
            self,
            kind,
            self.tokens,
            self._language,
            offer_choose_other=remove_key is None,
            offer_remove=remove_key is not None,
        )
        dialog.finished.connect(lambda: self._on_error_closed(dialog, remove_key))
        self.error_dialog = dialog
        dialog.open()

    def _on_error_closed(
        self, dialog: AccessibleErrorDialog, remove_key: str | None = None
    ) -> None:
        wants_other = dialog.choose_other_requested
        wants_remove = dialog.remove_requested
        dialog.deleteLater()
        if self.error_dialog is dialog:
            self.error_dialog = None
        if wants_other:
            self.home_view.choose_file()
        if wants_remove and remove_key is not None:
            self.remove_recent(remove_key)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.reading_view.stop_reading()
        self._save_position()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._focus_ring)
        self._runner.shutdown()
        self._tts.shutdown()
        event.accept()
