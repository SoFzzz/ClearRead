"""Reading view: syllable-coloured text with word highlight driven by the token map."""

from enum import Enum

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QKeySequence,
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
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clearread.services.text_formatter import FormattedDocument, WordToken
from clearread.services.tts_controller import (
    DEFAULT_RATE_WPM,
    TTSController,
    TTSErrorKind,
)
from clearread.ui.fonts import READING_FONT_FAMILY
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, ThemeTokens

COLUMN_MIN_WIDTH = 550
COLUMN_MAX_WIDTH = 820
READER_MARGIN_X = 40
READER_MARGIN_TOP = 32
PLAY_BAR_HEIGHT = 80
PLAY_BUTTON_SIZE = (148, 48)
SPEED_RANGE_WPM = (100, 280)
SPEED_SLIDER_WIDTH = 210
BAR_PADDING_X = 24
BAR_PADDING_Y = 8
BAR_SPACING = 16
BOLD_WEIGHT = 700
READING_FONT_PT = 16
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

    def __init__(self, tokens: ThemeTokens) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportMargins(READER_MARGIN_X, READER_MARGIN_TOP, READER_MARGIN_X, 0)
        self._word_format = QTextCharFormat()
        self._ruler_format = QTextCharFormat()
        self._line_spacing = DEFAULT_LINE_SPACING
        self.apply_theme(tokens)

    def apply_theme(self, tokens: ThemeTokens) -> None:
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.bg))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
        self.setPalette(palette)

        word = QTextCharFormat()
        word.setBackground(QColor(tokens.word_highlight_bg))
        word.setForeground(QColor(tokens.word_highlight_fg))
        word.setFontWeight(BOLD_WEIGHT)
        word.setFontUnderline(True)
        word.setUnderlineColor(QColor(tokens.word_highlight_fg))
        self._word_format = word

        ruler = QTextCharFormat()
        ruler.setBackground(QColor(tokens.ruler_bg))
        ruler.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self._ruler_format = ruler

    def set_content(self, html_content: str) -> None:
        self.setHtml(html_content)
        self._apply_line_spacing()

    def _apply_line_spacing(self) -> None:
        # Qt's proportional height is relative to the font's own line pitch (1.8 times
        # the font size for OpenDyslexic), so the design's "multiple of the font size"
        # is converted to a percentage of that pitch.
        font = self.font()
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
        self._build_ui()
        self._connect_signals()
        self._refresh_texts()

    def _build_ui(self) -> None:
        self.editor = ReaderWidget(self._tokens)
        self.editor.setFont(QFont(READING_FONT_FAMILY, READING_FONT_PT))
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._centered(column), stretch=1)
        layout.addWidget(self._build_play_bar())

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
        self.speed_slider.setRange(*SPEED_RANGE_WPM)
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
        self._tts.word_spoken.connect(self._on_word_spoken)
        self._tts.playback_ended.connect(self._on_playback_ended)
        self._tts.error_occurred.connect(self._on_error)
        shortcuts = (
            (Qt.Key.Key_Space, self.toggle_play),
            (Qt.Key.Key_Escape, self.stop_reading),
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
        self.token_map = document.token_map
        self.tts_script = document.tts_script
        self.current_word_idx = 0
        self.editor.set_content(document.html_content)
        self.editor.clear_highlights()
        self.status_label.hide()
        self._set_state(PlaybackState.IDLE)

    def apply_theme(self, theme: ThemeId, html_content: str) -> None:
        """Switch theme with html regenerated from the same text: positions are unchanged."""
        self._tokens = THEMES[theme]
        self.editor.apply_theme(self._tokens)
        self.editor.set_content(html_content)
        self.editor.clear_highlights()
        if self.state is not PlaybackState.IDLE and self.token_map:
            self.editor.highlight_token(self.token_map[self.current_word_idx])
        self._refresh_texts()

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
        self.status_label.hide()
        self.current_word_idx = word_index
        remaining = " ".join(token.spoken_text for token in self.token_map[word_index:])
        self._set_state(PlaybackState.PLAYING)
        self._tts.speak_text(remaining, start_offset=word_index)

    def stop_reading(self) -> None:
        self._tts.stop()
        self.current_word_idx = 0
        self.editor.clear_highlights()
        self._set_state(PlaybackState.IDLE)

    def _on_speed_changed(self, wpm: int) -> None:
        self.speed_value_label.setText(self._t("reading.speed_value", wpm=wpm))
        self._tts.set_speed(wpm)

    @Slot(int)
    def _on_word_spoken(self, word_index: int) -> None:
        if not 0 <= word_index < len(self.token_map):
            return
        self.current_word_idx = word_index
        self.editor.highlight_token(self.token_map[word_index])
        self._refresh_counter()

    @Slot()
    def _on_playback_ended(self) -> None:
        self.current_word_idx = 0
        self.editor.clear_highlights()
        self._set_state(PlaybackState.IDLE)

    @Slot(str)
    def _on_error(self, kind_name: str) -> None:
        self.status_label.setText(self._t(_ERROR_KEYS[kind_name]))
        self.status_label.show()
        self._set_state(PlaybackState.IDLE)
