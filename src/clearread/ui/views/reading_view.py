"""Reading view: syllable-coloured text with word highlight driven by the token map."""

import time
from collections.abc import Callable
from enum import Enum

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import (
    QFont,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from clearread.services.ai_text import word_query
from clearread.services.text_formatter import (
    FormattedDocument,
    ReadingStyle,
    WordToken,
    page_index_at,
    speech_from,
    token_index_at,
)
from clearread.services.tts_controller import (
    TTSController,
    TTSErrorKind,
)
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId
from clearread.ui.views.ai_panel import AIPanel
from clearread.ui.views.page_bar import PageBar
from clearread.ui.views.play_bar import PlayBar
from clearread.ui.views.reader_widget import ReaderWidget

COLUMN_MIN_WIDTH = 550
COLUMN_MAX_WIDTH = 820
ZOOM_IN, ZOOM_OUT, ZOOM_RESET = 1, -1, 0
_ERROR_KEYS = {
    TTSErrorKind.INIT_FAILED.name: "reading.error.tts_init",
    TTSErrorKind.PLAYBACK_FAILED.name: "reading.error.tts_playback",
}


class ViewMode(Enum):
    """The value is what AppConfig.reading_view_mode stores."""

    CONTINUOUS = "continuous"
    PAGED = "paged"


class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"


class ReadingView(QWidget):
    speed_changed = Signal(int)  # words per minute chosen with the bar's slider
    explain_requested = Signal(str, str)  # word, sentence that holds it
    simplify_requested = Signal(str)  # paragraph or selection
    assistant_open_changed = Signal(bool)
    aside_finished = Signal()  # the assistant's answer stopped being read aloud
    reading_session = Signal(int, float)  # words spoken, seconds spent playing
    view_mode_changed = Signal(str)  # ViewMode value chosen with the page bar
    zoom_requested = Signal(int)  # ZOOM_IN, ZOOM_OUT or ZOOM_RESET

    def __init__(
        self,
        tts: TTSController,
        theme: ThemeId = ThemeId.LIGHT,
        language: Language = Language.ES,
        clock: Callable[[], float] = time.monotonic,
        view_mode: ViewMode = ViewMode.CONTINUOUS,
    ) -> None:
        super().__init__()
        self._clock = clock
        self._session_words = 0
        self._play_started: float | None = None
        self.resume_index = 0  # last word read: where the document is picked up again
        self._tts = tts
        self._language = language
        self._tokens = THEMES[theme]
        self.token_map: list[WordToken] = []
        self.tts_script = ""
        self.current_word_idx = 0
        self.page_starts: tuple[int, ...] = (0,)
        self.current_page = 0
        self.view_mode = view_mode
        self.state = PlaybackState.IDLE
        self._aside = False  # the voice reads an assistant answer, not the document
        self._ai_anchor: int | None = None  # where the last assistant request pointed
        self._build_ui()
        self._connect_signals()
        self._refresh_texts()

    def _build_ui(self) -> None:
        self.editor = ReaderWidget(self._tokens)
        self.editor.enable_char_clicks()
        self.status_label = QLabel()
        self.status_label.setProperty("role", "muted")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        self.resume_banner = self._build_resume_banner()
        self.page_bar = PageBar(self._language)
        self.prev_page_button = self.page_bar.prev_page_button
        self.next_page_button = self.page_bar.next_page_button
        self.page_spin = self.page_bar.page_spin
        self.page_total_label = self.page_bar.page_total_label
        self.continuous_button = self.page_bar.continuous_button
        self.paged_button = self.page_bar.paged_button
        self.page_bar.sync_mode(self.view_mode is ViewMode.PAGED)
        self.play_bar = PlayBar()
        self.play_button = self.play_bar.play_button
        self.stop_button = self.play_bar.stop_button
        self.focus_button = self.play_bar.focus_button
        self.speed_label = self.play_bar.speed_label
        self.speed_slider = self.play_bar.speed_slider
        self.speed_value_label = self.play_bar.speed_value_label
        self.counter_label = self.play_bar.counter_label

        column = QFrame()
        column.setMinimumWidth(COLUMN_MIN_WIDTH)
        column.setMaximumWidth(COLUMN_MAX_WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(self.resume_banner)
        column_layout.addWidget(self.editor, stretch=1)
        column_layout.addWidget(self.status_label)

        reader = QVBoxLayout()
        reader.setContentsMargins(0, 0, 0, 0)
        reader.setSpacing(0)
        reader.addWidget(self.page_bar)
        reader.addLayout(self._centered(column), stretch=1)
        reader.addWidget(self.play_bar)

        self.ai_panel = AIPanel(self._tokens, self._language)
        self.ai_panel.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(reader, stretch=1)
        layout.addWidget(self.ai_panel)

    def _build_resume_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("Card")
        self.resume_title = QLabel()
        self.resume_title.setProperty("role", "heading")
        self.resume_title.setStyleSheet("font-size: 16px;")
        self.resume_detail = QLabel()
        self.resume_detail.setProperty("role", "muted")
        self.resume_detail.setWordWrap(True)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.resume_title)
        texts.addWidget(self.resume_detail)
        self.resume_continue_button = QPushButton()
        self.resume_continue_button.setProperty("variant", "primary")
        self.resume_continue_button.clicked.connect(self._resume_here)
        self.resume_restart_button = QPushButton()
        self.resume_restart_button.clicked.connect(self._dismiss_resume)
        row = QHBoxLayout(banner)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)
        row.addLayout(texts, stretch=1)
        row.addWidget(self.resume_restart_button)
        row.addWidget(self.resume_continue_button)
        banner.hide()
        return banner

    @staticmethod
    def _centered(widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(widget, stretch=3)
        row.addStretch(1)
        return row

    def _connect_signals(self) -> None:
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop_reading)
        self.focus_button.toggled.connect(self.set_focus_mode)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        self.editor.char_clicked.connect(self._on_char_clicked)
        self.editor.context_menu_requested.connect(self._show_context_menu)
        self.editor.scrolled.connect(self._on_editor_scrolled)
        self.prev_page_button.clicked.connect(
            lambda: self.go_to_page(self.current_page - 1)
        )
        self.next_page_button.clicked.connect(
            lambda: self.go_to_page(self.current_page + 1)
        )
        self.page_spin.valueChanged.connect(lambda number: self.go_to_page(number - 1))
        self.continuous_button.clicked.connect(
            lambda: self._choose_view_mode(ViewMode.CONTINUOUS)
        )
        self.paged_button.clicked.connect(
            lambda: self._choose_view_mode(ViewMode.PAGED)
        )
        self.ai_panel.close_clicked.connect(lambda: self.set_assistant_open(False))
        self._tts.word_spoken.connect(self._on_word_spoken)
        self._tts.playback_ended.connect(self._on_playback_ended)
        self._tts.error_occurred.connect(self._on_error)
        shortcuts = (
            (Qt.Key.Key_Space, self.toggle_play),
            (Qt.Key.Key_Escape, self._on_escape),
            (Qt.Key.Key_F, self.focus_button.toggle),
            (Qt.Key.Key_PageDown, lambda: self._scroll_page(1)),
            (Qt.Key.Key_PageUp, lambda: self._scroll_page(-1)),
            ("Ctrl+Right", lambda: self.go_to_page(self.current_page + 1)),
            ("Ctrl+Left", lambda: self.go_to_page(self.current_page - 1)),
            ("Ctrl+Home", lambda: self.go_to_page(0)),
            ("Ctrl+End", lambda: self.go_to_page(self.page_count - 1)),
            ("Ctrl++", lambda: self.zoom_requested.emit(ZOOM_IN)),
            ("Ctrl+=", lambda: self.zoom_requested.emit(ZOOM_IN)),
            ("Ctrl+-", lambda: self.zoom_requested.emit(ZOOM_OUT)),
            ("Ctrl+0", lambda: self.zoom_requested.emit(ZOOM_RESET)),
        )
        for key, slot in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def _refresh_texts(self) -> None:
        labels = {
            PlaybackState.IDLE: ("reading.play", "play"),
            PlaybackState.PLAYING: ("reading.pause", "pause"),
            PlaybackState.PAUSED: ("reading.resume", "play"),
        }
        key, icon = labels[self.state]
        play = self._t(key)
        self.play_button.setText(play)
        self.play_button.setIcon(load_icon(icon, self._tokens.primary_fg))
        self.play_button.setToolTip(
            self._t(
                "reading.tooltip", action=play, shortcut=self._t("reading.key_space")
            )
        )
        stop = self._t("reading.stop")
        self.stop_button.setText(stop)
        self.stop_button.setIcon(load_icon("stop", self._tokens.secondary))
        self.stop_button.setToolTip(
            self._t("reading.tooltip", action=stop, shortcut=self._t("reading.key_esc"))
        )
        focus = self._t("reading.focus")
        self.focus_button.setText(focus)
        self.focus_button.setIcon(load_icon("focus", self._tokens.secondary))
        self.focus_button.setToolTip(
            self._t("reading.tooltip", action=focus, shortcut=self._t("reading.key_f"))
        )
        self._refresh_page_bar_texts()
        self.resume_title.setText(self._t("reading.resume_title"))
        self.resume_continue_button.setText(self._t("reading.resume_continue"))
        self.resume_restart_button.setText(self._t("reading.resume_restart"))
        self.speed_label.setText(self._t("reading.speed"))
        self.speed_value_label.setText(
            self._t("reading.speed_value", wpm=self.speed_slider.value())
        )
        self._refresh_counter()

    def _refresh_page_bar_texts(self) -> None:
        self.page_bar.refresh_texts(self.page_count)
        self.editor.set_page_labels(
            [
                self._t("reading.page_label", number=n + 1)
                for n in range(self.page_count)
            ]
        )

    def _refresh_counter(self) -> None:
        total = len(self.token_map)
        shown = 0 if self.state is PlaybackState.IDLE else self.current_word_idx + 1
        self.counter_label.setText(
            self._t("reading.word_counter", current=min(shown, total), total=total)
        )

    def _set_state(self, state: PlaybackState) -> None:
        was_playing = self.state is PlaybackState.PLAYING
        self.state = state
        if state is PlaybackState.PLAYING and not was_playing:
            self._play_started = self._clock()
        elif was_playing and state is not PlaybackState.PLAYING:
            self._end_session()
        self._refresh_texts()

    def _end_session(self) -> None:
        started, self._play_started = self._play_started, None
        words, self._session_words = self._session_words, 0
        seconds = 0.0 if started is None else self._clock() - started
        if words > 0 or seconds >= 1:
            self.reading_session.emit(words, seconds)

    def set_focus_mode(self, enabled: bool) -> None:
        self.editor.set_focus_mode(enabled)
        if self.focus_button.isChecked() != enabled:
            self.focus_button.setChecked(enabled)

    def _resume_here(self) -> None:
        self.resume_banner.hide()
        if 0 <= self.resume_index < len(self.token_map):
            self._move_start_to(self.resume_index)

    def _dismiss_resume(self) -> None:
        self.resume_banner.hide()
        self.resume_index = 0

    @Slot(FormattedDocument)
    def load_document(self, document: FormattedDocument, resume_at: int = 0) -> None:
        self._tts.stop()
        self._set_state(PlaybackState.IDLE)
        self._end_aside()
        self._ai_anchor = None
        self.token_map = document.token_map
        self.tts_script = document.tts_script
        self.current_word_idx = 0
        self.page_starts = document.page_starts
        self.editor.set_content(document.html_content, document.page_starts)
        self.editor.set_paged(self.view_mode is ViewMode.PAGED)
        self.editor.clear_highlights()
        self._set_current_page(0)
        self._refresh_page_bar_texts()
        self.page_bar.setVisible(self.page_count > 1)
        self.status_label.hide()
        self.resume_index = resume_at
        offer = 0 < resume_at < len(self.token_map) - 1
        self.resume_detail.setText(
            self._t(
                "reading.resume_detail",
                current=resume_at + 1,
                total=len(self.token_map),
            )
        )
        self.resume_banner.setVisible(offer)
        self._set_state(PlaybackState.IDLE)

    def apply_appearance(
        self,
        theme: ThemeId,
        style: ReadingStyle,
        line_spacing: float,
        html_content: str,
    ) -> None:
        """Re-render with new colours and typography from html generated for the same text.

        The positions of the token map do not change, so the word being read stays
        highlighted.
        """
        self._tokens = THEMES[theme]
        self.ai_panel.apply_theme(self._tokens)
        self.editor.apply_theme(self._tokens)
        self.editor.set_reading_font(QFont(style.font_family, style.font_size_pt))
        self.editor.set_line_spacing(line_spacing)
        anchor = self.editor.first_visible_position()
        self.editor.set_content(html_content)
        self.editor.clear_highlights()
        self.editor.scroll_to_position(anchor)
        if self.state is not PlaybackState.IDLE and self.token_map:
            self._highlight_word(self.current_word_idx)
        self._refresh_texts()

    @property
    def page_count(self) -> int:
        return len(self.page_starts)

    def go_to_page(self, index: int) -> None:
        """Show page ``index`` (0-based); it never starts or stops the voice."""
        index = max(0, min(index, self.page_count - 1))
        if self.view_mode is ViewMode.PAGED:
            self._turn_to_page(index, force=True)
        else:
            self.editor.scroll_to_position(self.page_starts[index])
            self._set_current_page(index)

    def _turn_to_page(self, index: int, force: bool = False) -> None:
        if force or index != self.current_page:
            self.editor.show_page(index)
        self._set_current_page(index)

    def _set_current_page(self, index: int) -> None:
        self.current_page = index
        self.page_bar.show_page(index, self.page_count)

    def _on_editor_scrolled(self) -> None:
        if self.view_mode is ViewMode.CONTINUOUS and self.page_count > 1:
            self._set_current_page(self.editor.visible_page())

    def _scroll_page(self, direction: int) -> None:
        """PageUp/PageDown scroll a screen; in page mode they turn the page at its end."""
        bar = self.editor.verticalScrollBar()
        edge = bar.maximum() if direction > 0 else bar.minimum()
        target = self.current_page + direction
        turns = self.view_mode is ViewMode.PAGED and 0 <= target < self.page_count
        if turns and bar.value() == edge:
            self.go_to_page(target)
            if direction < 0:
                bar.setValue(bar.maximum())
        else:
            bar.setValue(bar.value() + direction * bar.pageStep())

    def _anchor_position(self) -> int:
        """Character to keep on screen when the view mode changes."""
        if self.state is not PlaybackState.IDLE and self.token_map:
            return self.token_map[self.current_word_idx].doc_start_pos
        return self.editor.first_visible_position()

    def set_view_mode(self, mode: ViewMode) -> None:
        """Switch between continuous and page mode, keeping the current word in view."""
        if mode is self.view_mode:
            return
        anchor = self._anchor_position()
        self.view_mode = mode
        self.editor.set_paged(mode is ViewMode.PAGED)
        self.editor.show_page(page_index_at(self.page_starts, anchor))
        self.editor.scroll_to_position(anchor)
        self._set_current_page(page_index_at(self.page_starts, anchor))
        self._sync_mode_buttons()

    def _choose_view_mode(self, mode: ViewMode) -> None:
        self.set_view_mode(mode)
        self.view_mode_changed.emit(mode.value)

    def _sync_mode_buttons(self) -> None:
        self.page_bar.sync_mode(self.view_mode is ViewMode.PAGED)

    def set_speed(self, wpm: int) -> None:
        self.speed_slider.setValue(wpm)

    def toggle_play(self) -> None:
        if not self.token_map:
            return
        if self.state is PlaybackState.PLAYING:
            self._tts.stop()
            self._set_state(PlaybackState.PAUSED)
        elif self.state is PlaybackState.PAUSED:
            self._speak_from(self.current_word_idx)
        else:
            self._speak_from(0)

    def _speak_from(self, word_index: int) -> None:
        self._end_aside()
        self.resume_banner.hide()
        self.status_label.hide()
        self.current_word_idx = word_index
        self.resume_index = word_index
        speech = speech_from(self.tts_script, self.token_map, word_index)
        self._set_state(PlaybackState.PLAYING)
        self._highlight_word(word_index)
        self._tts.speak_text(
            speech.text, start_offset=word_index, word_spans=speech.word_spans
        )

    def _move_start_to(self, word_index: int) -> None:
        """Silently choose where Play will read from; only Play starts the voice."""
        self._tts.stop()
        self._end_aside()
        self.resume_banner.hide()
        self.current_word_idx = word_index
        self.resume_index = word_index
        self._highlight_word(word_index, center=True)
        self._set_state(PlaybackState.PAUSED)

    @Slot(int)
    def _on_char_clicked(self, char_index: int) -> None:
        if self.token_map:
            self._move_start_to(token_index_at(self.token_map, char_index))

    def _highlight_word(self, word_index: int, center: bool = False) -> None:
        token = self.token_map[word_index]
        if self.view_mode is ViewMode.PAGED:
            self._turn_to_page(page_index_at(self.page_starts, token.doc_start_pos))
        self.editor.highlight_token(token, center)

    def stop_reading(self) -> None:
        self._tts.stop()
        self._end_aside()
        self.current_word_idx = 0
        self.editor.clear_highlights()
        self._set_state(PlaybackState.IDLE)

    def _on_speed_changed(self, wpm: int) -> None:
        self.speed_value_label.setText(self._t("reading.speed_value", wpm=wpm))
        self._tts.set_speed(wpm)
        self.speed_changed.emit(wpm)

    @Slot(int)
    def _on_word_spoken(self, word_index: int) -> None:
        if self._aside or self.state is PlaybackState.PAUSED:
            return
        if not 0 <= word_index < len(self.token_map):
            return
        self.current_word_idx = word_index
        self.resume_index = word_index
        self._session_words += 1
        self._highlight_word(word_index)
        self._refresh_counter()

    @Slot()
    def _on_playback_ended(self) -> None:
        if self._aside:
            self._end_aside()
            return
        if self.state is PlaybackState.PAUSED:
            return
        self.resume_index = max(len(self.token_map) - 1, 0)
        self.current_word_idx = 0
        self.editor.clear_highlights()
        self._set_state(PlaybackState.IDLE)

    @Slot(str)
    def _on_error(self, kind_name: str) -> None:
        self._end_aside()
        self.status_label.setText(self._t(_ERROR_KEYS[kind_name]))
        self.status_label.show()
        self._set_state(PlaybackState.IDLE)

    def _on_escape(self) -> None:
        if self.assistant_open:
            self.set_assistant_open(False)
        else:
            self.stop_reading()

    def set_assistant_available(self, available: bool) -> None:
        self.editor.enable_context_menu(available)

    @property
    def assistant_open(self) -> bool:
        return not self.ai_panel.isHidden()

    def set_assistant_open(self, opened: bool) -> None:
        if opened == self.assistant_open:
            return
        self.ai_panel.setVisible(opened)
        if opened:
            self.pause_reading()
        else:
            self.stop_aside()
            self.editor.setFocus()
        self.assistant_open_changed.emit(opened)

    def pause_reading(self) -> None:
        if self.state is PlaybackState.PLAYING:
            self._tts.stop()
            self._set_state(PlaybackState.PAUSED)

    def speak_aside(self, text: str) -> None:
        """Read ``text`` with the document's voice, leaving the document's place alone."""
        self.pause_reading()
        self._aside = True
        self._tts.speak_text(text)

    def stop_aside(self) -> None:
        if self._aside:
            self._tts.stop()
            self._end_aside()

    def _end_aside(self) -> None:
        if self._aside:
            self._aside = False
            self.aside_finished.emit()

    def assistant_anchor(self) -> int | None:
        """Character the assistant works on when there was no new right-click."""
        if self._ai_anchor is not None:
            return self._ai_anchor
        if self.token_map and self.state is not PlaybackState.IDLE:
            return self.token_map[self.current_word_idx].doc_start_pos
        return None

    def explain_at(self, position: int) -> None:
        if not self.token_map:
            return
        token = self.token_map[token_index_at(self.token_map, position)]
        query = word_query(
            self.editor.toPlainText(), token.doc_start_pos, token.doc_end_pos
        )
        self._ai_anchor = token.doc_start_pos
        self.explain_requested.emit(query.word, query.context_sentence)

    def simplify_at(self, position: int) -> None:
        text = " ".join(self._text_to_simplify(position).split())
        if text:
            self._ai_anchor = position
            self.simplify_requested.emit(text)

    def _text_to_simplify(self, position: int) -> str:
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and (
            cursor.selectionStart() <= position <= cursor.selectionEnd()
        ):
            return cursor.selectedText()
        return self.editor.document().findBlock(position).text()

    def _word_at(self, position: int) -> bool:
        if not self.token_map:
            return False
        token = self.token_map[token_index_at(self.token_map, position)]
        return token.doc_start_pos <= position < token.doc_end_pos

    @Slot(int, QPoint)
    def _show_context_menu(self, position: int, global_point: QPoint) -> None:
        menu = QMenu(self)
        if self._word_at(position):
            explain = menu.addAction(self._t("ai.menu_explain"))
            explain.triggered.connect(lambda: self.explain_at(position))
        simplify = menu.addAction(self._t("ai.menu_simplify"))
        simplify.triggered.connect(lambda: self.simplify_at(position))
        menu.exec(global_point)
