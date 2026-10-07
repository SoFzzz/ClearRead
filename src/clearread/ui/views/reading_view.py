"""Reading view: syllable-coloured text with word highlight driven by the token map."""

from enum import Enum

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetricsF,
    QKeySequence,
    QMouseEvent,
    QPalette,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clearread.services.ai_text import word_query
from clearread.services.text_formatter import (
    FormattedDocument,
    ReadingStyle,
    WordToken,
    token_index_at,
)
from clearread.services.tts_controller import (
    DEFAULT_RATE_WPM,
    MAX_RATE_WPM,
    MIN_RATE_WPM,
    TTSController,
    TTSErrorKind,
)
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, ThemeTokens
from clearread.ui.views.ai_panel import AIPanel

COLUMN_MIN_WIDTH = 550
COLUMN_MAX_WIDTH = 820
READER_MARGIN_X = 40
READER_MARGIN_TOP = 32
PLAY_BAR_HEIGHT = 80
PLAY_BUTTON_SIZE = (148, 48)
SPEED_SLIDER_WIDTH = 210
BAR_PADDING_X = 24
BAR_PADDING_Y = 8
BAR_SPACING = 16
DEFAULT_LINE_SPACING = 1.8  # multiple of the font size (design system 1.4)
POINTS_PER_INCH = 72.0
_ERROR_KEYS = {
    TTSErrorKind.INIT_FAILED.name: "reading.error.tts_init",
    TTSErrorKind.PLAYBACK_FAILED.name: "reading.error.tts_playback",
}


class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"


class ReaderWidget(QTextEdit):
    """Read-only text with a spoken-word highlight and a full-width line ruler."""

    char_clicked = Signal(int)  # document position of the character that was pressed
    context_menu_requested = Signal(int, QPoint)  # character position, global point

    def __init__(self, tokens: ThemeTokens) -> None:
        super().__init__()
        self._clickable = False
        self._context_menu_enabled = False
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(READER_MARGIN_X, READER_MARGIN_TOP, READER_MARGIN_X, 0)
        self._word_format = QTextCharFormat()
        self._ruler_format = QTextCharFormat()
        self._line_spacing = DEFAULT_LINE_SPACING
        self.reading_font = QFont(
            ReadingStyle().font_family, ReadingStyle().font_size_pt
        )
        self.apply_theme(tokens)

    def enable_char_clicks(self) -> None:
        """Turn presses into ``char_clicked`` instead of a caret or a text selection."""
        self._clickable = True
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def enable_context_menu(self, enabled: bool) -> None:
        self._context_menu_enabled = enabled

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._context_menu_enabled:
            position = self._char_under(event.pos())
            self.context_menu_requested.emit(position, event.globalPos())
        else:
            super().contextMenuEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._clickable:
            super().mousePressEvent(event)
        elif event.button() == Qt.MouseButton.LeftButton:
            self.char_clicked.emit(self._char_under(event.position().toPoint()))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self._clickable:
            super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._clickable:
            super().mouseMoveEvent(event)

    def _char_under(self, point: QPoint) -> int:
        # cursorForPosition() answers with the nearest gap between characters: the right
        # half of a letter would resolve to the character after it. The gap's own x tells
        # which side of it the press landed on.
        gap = self.cursorForPosition(point)
        gap_x = self.cursorRect(gap).x()
        return gap.position() - 1 if point.x() < gap_x else gap.position()

    def fit_height(self, text_width: int, minimum: int, maximum: int) -> None:
        """Make the widget as tall as its text at ``text_width``, within the limits.

        There is no scroll bar: beyond ``maximum`` the text is cut and the view stays
        on the highlighted word.
        """
        self.document().setTextWidth(text_width)
        margins = self.viewportMargins()
        needed = (
            round(self.document().size().height()) + margins.top() + margins.bottom()
        )
        self.setFixedHeight(max(minimum, min(maximum, needed)))

    def apply_theme(self, tokens: ThemeTokens) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.bg))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
        self.setPalette(palette)

        word = QTextCharFormat()
        word.setBackground(QColor(tokens.word_highlight_bg))
        word.setForeground(QColor(tokens.word_highlight_fg))
        word.setFontUnderline(True)
        word.setUnderlineColor(QColor(tokens.word_highlight_fg))
        self._word_format = word

        ruler = QTextCharFormat()
        ruler.setBackground(QColor(tokens.ruler_bg))
        ruler.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self._ruler_format = ruler

    def set_line_spacing(self, line_spacing: float) -> None:
        self._line_spacing = line_spacing

    def set_reading_font(self, font: QFont) -> None:
        # Kept apart from font(): the window's QSS sets a UI font on every widget, and
        # the line spacing must be computed from the font the text is drawn with.
        self.reading_font = font
        self.setFont(font)

    def set_content(self, html_content: str) -> None:
        self.setHtml(html_content)
        self._apply_line_spacing()

    def _apply_line_spacing(self) -> None:
        # Qt's proportional height is relative to the font's own line pitch (1.8 times
        # the font size for OpenDyslexic), so the design's "multiple of the font size"
        # is converted to a percentage of that pitch.
        font = self.reading_font
        em_px = font.pointSizeF() * self.logicalDpiY() / POINTS_PER_INCH
        natural_px = QFontMetricsF(font).lineSpacing()
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            100.0 * self._line_spacing * em_px / natural_px,
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(block_format)

    def highlight_token(self, token: WordToken) -> None:
        document = self.document()
        word_cursor = QTextCursor(document)
        word_cursor.setPosition(token.doc_start_pos)
        word_cursor.setPosition(token.doc_end_pos, QTextCursor.MoveMode.KeepAnchor)
        ruler_cursor = QTextCursor(document)
        ruler_cursor.setPosition(token.doc_start_pos)

        ruler_selection = QTextEdit.ExtraSelection()
        ruler_selection.cursor = ruler_cursor
        ruler_selection.format = self._ruler_format
        word_selection = QTextEdit.ExtraSelection()
        word_selection.cursor = word_cursor
        word_selection.format = self._word_format
        self.setExtraSelections([ruler_selection, word_selection])

        caret = QTextCursor(document)
        caret.setPosition(token.doc_start_pos)
        self.setTextCursor(caret)
        self.ensureCursorVisible()

    def highlighted_range(self) -> tuple[int, int] | None:
        """Character range of the word currently highlighted, if any."""
        selections = self.extraSelections()
        if not selections:
            return None
        cursor = selections[-1].cursor
        return cursor.selectionStart(), cursor.selectionEnd()

    def clear_highlights(self) -> None:
        self.setExtraSelections([])


class ReadingView(QWidget):
    speed_changed = Signal(int)  # words per minute chosen with the bar's slider
    explain_requested = Signal(str, str)  # word, sentence that holds it
    simplify_requested = Signal(str)  # paragraph or selection
    assistant_open_changed = Signal(bool)
    aside_finished = Signal()  # the assistant's answer stopped being read aloud

    def __init__(
        self,
        tts: TTSController,
        theme: ThemeId = ThemeId.LIGHT,
        language: Language = Language.ES,
    ) -> None:
        super().__init__()
        self._tts = tts
        self._language = language
        self._tokens = THEMES[theme]
        self.token_map: list[WordToken] = []
        self.tts_script = ""
        self.current_word_idx = 0
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

        column = QFrame()
        column.setMinimumWidth(COLUMN_MIN_WIDTH)
        column.setMaximumWidth(COLUMN_MAX_WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(self.editor, stretch=1)
        column_layout.addWidget(self.status_label)

        reader = QVBoxLayout()
        reader.setContentsMargins(0, 0, 0, 0)
        reader.setSpacing(0)
        reader.addLayout(self._centered(column), stretch=1)
        reader.addWidget(self._build_play_bar())

        self.ai_panel = AIPanel(self._tokens, self._language)
        self.ai_panel.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(reader, stretch=1)
        layout.addWidget(self.ai_panel)

    @staticmethod
    def _centered(widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(widget, stretch=3)
        row.addStretch(1)
        return row

    def _build_play_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("PlayBar")
        bar.setFixedHeight(PLAY_BAR_HEIGHT)

        self.play_button = QPushButton()
        self.play_button.setProperty("variant", "primary")
        self.play_button.setFixedSize(*PLAY_BUTTON_SIZE)
        self.stop_button = QPushButton()
        self.stop_button.setFixedHeight(PLAY_BUTTON_SIZE[1])

        self.speed_label = QLabel()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(MIN_RATE_WPM, MAX_RATE_WPM)
        self.speed_slider.setValue(DEFAULT_RATE_WPM)
        self.speed_slider.setFixedWidth(SPEED_SLIDER_WIDTH)
        self.speed_value_label = QLabel()
        speed_header = QHBoxLayout()
        speed_header.addWidget(self.speed_label)
        speed_header.addStretch(1)
        speed_header.addWidget(self.speed_value_label)
        speed = QVBoxLayout()
        speed.setSpacing(0)
        speed.addLayout(speed_header)
        speed.addWidget(self.speed_slider)

        self.counter_label = QLabel()
        self.shortcuts_label = QLabel()
        self.shortcuts_label.setProperty("role", "muted")
        info = QVBoxLayout()
        info.setSpacing(0)
        info.addWidget(self.counter_label)
        info.addWidget(self.shortcuts_label)

        content = QWidget()
        content.setObjectName("PlayBarContent")
        content.setMaximumWidth(COLUMN_MAX_WIDTH)
        row = QHBoxLayout(content)
        row.setContentsMargins(0, BAR_PADDING_Y, 0, BAR_PADDING_Y)
        row.setSpacing(BAR_SPACING)
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addLayout(speed)
        row.addStretch(1)
        row.addLayout(info)

        outer = QHBoxLayout(bar)
        outer.setContentsMargins(BAR_PADDING_X, 0, BAR_PADDING_X, 0)
        outer.addStretch(1)
        outer.addWidget(content, stretch=3)
        outer.addStretch(1)
        return bar

    def _connect_signals(self) -> None:
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop_reading)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        self.editor.char_clicked.connect(self._on_char_clicked)
        self.editor.context_menu_requested.connect(self._show_context_menu)
        self.ai_panel.close_clicked.connect(lambda: self.set_assistant_open(False))
        self._tts.word_spoken.connect(self._on_word_spoken)
        self._tts.playback_ended.connect(self._on_playback_ended)
        self._tts.error_occurred.connect(self._on_error)
        shortcuts = (
            (Qt.Key.Key_Space, self.toggle_play),
            (Qt.Key.Key_Escape, self._on_escape),
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
        self.speed_label.setText(self._t("reading.speed"))
        self.speed_value_label.setText(
            self._t("reading.speed_value", wpm=self.speed_slider.value())
        )
        self.shortcuts_label.setText(self._t("reading.shortcuts"))
        self._refresh_counter()

    def _refresh_counter(self) -> None:
        total = len(self.token_map)
        shown = 0 if self.state is PlaybackState.IDLE else self.current_word_idx + 1
        self.counter_label.setText(
            self._t("reading.word_counter", current=min(shown, total), total=total)
        )

    def _set_state(self, state: PlaybackState) -> None:
        self.state = state
        self._refresh_texts()

    @Slot(FormattedDocument)
    def load_document(self, document: FormattedDocument) -> None:
        self._tts.stop()
        self._end_aside()
        self._ai_anchor = None
        self.token_map = document.token_map
        self.tts_script = document.tts_script
        self.current_word_idx = 0
        self.editor.set_content(document.html_content)
        self.editor.clear_highlights()
        self.status_label.hide()
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
        self.editor.set_content(html_content)
        self.editor.clear_highlights()
        if self.state is not PlaybackState.IDLE and self.token_map:
            self.editor.highlight_token(self.token_map[self.current_word_idx])
        self._refresh_texts()

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
        self.status_label.hide()
        self.current_word_idx = word_index
        remaining = " ".join(token.spoken_text for token in self.token_map[word_index:])
        self._set_state(PlaybackState.PLAYING)
        self.editor.highlight_token(self.token_map[word_index])
        self._tts.speak_text(remaining, start_offset=word_index)

    @Slot(int)
    def _on_char_clicked(self, char_index: int) -> None:
        if self.token_map:
            self._speak_from(token_index_at(self.token_map, char_index))

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
        if self._aside:
            return
        if not 0 <= word_index < len(self.token_map):
            return
        self.current_word_idx = word_index
        self.editor.highlight_token(self.token_map[word_index])
        self._refresh_counter()

    @Slot()
    def _on_playback_ended(self) -> None:
        if self._aside:
            self._end_aside()
            return
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
