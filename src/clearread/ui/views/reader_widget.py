"""Read-only text widget: spoken-word highlight, line ruler and page labels."""

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QFontMetricsF,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QFrame, QTextEdit

from clearread.services.text_formatter import ReadingStyle, WordToken, page_index_at
from clearread.ui.theme import ThemeTokens

READER_MARGIN_X = 40
READER_MARGIN_TOP = 32
DEFAULT_LINE_SPACING = 1.5  # multiple of the font size (design system 1.4)
POINTS_PER_INCH = 72.0
PAGE_GAP = 48  # px above the first paragraph of a page, where its label is painted
PAGE_LABEL_SCALE = 0.6  # label size relative to the reading font
PAGE_LABEL_MIN_PT = 11.0
PROBE_OFFSET = 2  # px below the top of the text used to tell which page is on screen


class ReaderWidget(QTextEdit):
    """Read-only text with a spoken-word highlight and a full-width line ruler."""

    char_clicked = Signal(int)  # document position of the character that was pressed
    context_menu_requested = Signal(int, QPoint)  # character position, global point
    scrolled = Signal()  # the text moved, except by a jump the view itself asked for

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
        self._dim_format = QTextCharFormat()
        self._active_token: WordToken | None = None
        self._focus_mode = False
        self._page_starts: tuple[int, ...] = ()
        self._page_labels: Sequence[str] = ()
        self._paged = False
        self._shown_page = 0
        self._silent_scroll = False
        self._label_color = QColor(tokens.text_muted)
        self._rule_color = QColor(tokens.border)
        self.reading_font = QFont(
            ReadingStyle().font_family, ReadingStyle().font_size_pt
        )
        self.apply_theme(tokens)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_value)

    def enable_char_clicks(self) -> None:
        """Report plain clicks as ``char_clicked``; selecting text keeps working."""
        self._clickable = True

    def enable_context_menu(self, enabled: bool) -> None:
        self._context_menu_enabled = enabled

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        if self._context_menu_enabled:
            position = self._char_under(event.pos())
            self.context_menu_requested.emit(position, event.globalPos())
        else:
            super().contextMenuEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        is_click = (
            self._clickable
            and event.button() == Qt.MouseButton.LeftButton
            and not self.textCursor().hasSelection()
        )
        if is_click:
            self.char_clicked.emit(self._char_under(event.position().toPoint()))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)  # selects the word
        if self._clickable and self._context_menu_enabled:
            position = self._char_under(event.position().toPoint())
            self.context_menu_requested.emit(position, event.globalPosition().toPoint())

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

        dim = QTextCharFormat()
        dim.setForeground(QColor(tokens.dim_text))
        dim.setBackground(QColor(tokens.bg))
        self._dim_format = dim
        self._label_color = QColor(tokens.text_muted)
        self._rule_color = QColor(tokens.border)

        ruler = QTextCharFormat()
        ruler.setBackground(QColor(tokens.ruler_bg))
        ruler.setProperty(QTextFormat.Property.FullWidthSelection, True)
        self._ruler_format = ruler
        self._refresh_selections()

    def set_line_spacing(self, line_spacing: float) -> None:
        self._line_spacing = line_spacing

    def set_reading_font(self, font: QFont) -> None:
        # Kept apart from font(): the window's QSS sets a UI font on every widget, and
        # the line spacing must be computed from the font the text is drawn with.
        self.reading_font = font
        self.setFont(font)
        # A wheel notch moves three steps: about two lines of text.
        line_px = font.pointSizeF() * self.logicalDpiY() / POINTS_PER_INCH
        self.verticalScrollBar().setSingleStep(max(1, round(line_px / 1.5)))

    def set_content(
        self, html_content: str, page_starts: tuple[int, ...] | None = None
    ) -> None:
        """Show the html; ``page_starts`` is given when it is a new document."""
        self.setHtml(html_content)
        self._apply_line_spacing()
        if page_starts is not None:
            self._page_starts = page_starts
            self._shown_page = 0
        self._apply_page_layout()

    def set_page_labels(self, labels: Sequence[str]) -> None:
        self._page_labels = labels
        self.viewport().update()

    @property
    def multi_page(self) -> bool:
        return len(self._page_starts) > 1

    @property
    def _labels_shown(self) -> bool:
        return self.multi_page and not self._paged

    def set_paged(self, paged: bool) -> None:
        """Show every page one after another, or only the page set by ``show_page``."""
        self._paged = paged
        self._apply_page_layout()

    def show_page(self, index: int) -> None:
        self._shown_page = max(0, min(index, max(len(self._page_starts) - 1, 0)))
        self._apply_page_layout()
        self._scroll_silently(0)

    def _apply_page_layout(self) -> None:
        """Hide the other pages (page mode) and leave room for the labels (continuous).

        Neither changes a character position, so the token map stays valid.
        """
        document = self.document()
        hide_others = self._paged and self.multi_page
        block = document.begin()
        while block.isValid():
            page = page_index_at(self._page_starts, block.position())
            block.setVisible(not hide_others or page == self._shown_page)
            block = block.next()
        for start in self._page_starts:
            self._set_top_margin(start, PAGE_GAP if self._labels_shown else 0)
        document.markContentsDirty(0, document.characterCount())

    def _set_top_margin(self, position: int, margin: int) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(position)
        block_format = QTextBlockFormat()
        block_format.setTopMargin(margin)
        cursor.mergeBlockFormat(block_format)

    def _on_scroll_value(self) -> None:
        if not self._silent_scroll:
            self.scrolled.emit()

    def _scroll_silently(self, value: int) -> None:
        self._silent_scroll = True
        try:
            self.verticalScrollBar().setValue(value)
        finally:
            self._silent_scroll = False

    def scroll_to_position(self, position: int) -> None:
        """Put the line of ``position`` at the top; a page start also shows its label."""
        document = self.document()
        document.size()  # lays the whole text out, so the scroll range is current
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        line_top = self.cursorRect(cursor).y() + self.verticalScrollBar().value()
        gap = PAGE_GAP if self._labels_shown and position in self._page_starts else 0
        self._scroll_silently(max(0, line_top - gap))

    def first_visible_position(self) -> int:
        probe = PROBE_OFFSET + (PAGE_GAP if self._labels_shown else 0)
        return self.cursorForPosition(QPoint(0, probe)).position()

    def visible_page(self) -> int:
        """Page in the middle of the screen; the last one once the end is reached."""
        bar = self.verticalScrollBar()
        if bar.maximum() > 0 and bar.value() >= bar.maximum():
            return max(len(self._page_starts) - 1, 0)
        middle = self.cursorForPosition(QPoint(0, self.viewport().height() // 2))
        return page_index_at(self._page_starts, middle.position())

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._labels_shown:
            self._paint_page_labels()

    def _paint_page_labels(self) -> None:
        painter = QPainter(self.viewport())
        font = QFont(self.reading_font)
        font.setPointSizeF(max(PAGE_LABEL_MIN_PT, font.pointSizeF() * PAGE_LABEL_SCALE))
        font.setBold(True)
        painter.setFont(font)
        layout = self.document().documentLayout()
        scroll = self.verticalScrollBar().value()
        for start, label in zip(self._page_starts, self._page_labels, strict=False):
            block = self.document().findBlock(start)
            box_top = round(layout.blockBoundingRect(block).top()) - scroll - PAGE_GAP
            if PAGE_GAP + box_top < 0 or box_top > self.viewport().height():
                continue
            self._paint_label(painter, label, box_top)
        painter.end()

    def _paint_label(self, painter: QPainter, label: str, top: int) -> None:
        painter.setPen(self._label_color)
        text_width = painter.fontMetrics().horizontalAdvance(label)
        painter.drawText(
            0, top, text_width, PAGE_GAP, Qt.AlignmentFlag.AlignVCenter, label
        )
        painter.setPen(self._rule_color)
        middle = top + PAGE_GAP // 2
        painter.drawLine(text_width + 12, middle, self.viewport().width(), middle)

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

    def set_focus_mode(self, enabled: bool) -> None:
        """Dim every line except the active one (READ-F02)."""
        self._focus_mode = enabled
        self._refresh_selections()

    @property
    def focus_mode(self) -> bool:
        return self._focus_mode

    def highlight_token(self, token: WordToken, center: bool = False) -> None:
        """Highlight ``token``; ``center`` puts it mid-screen when it was out of view."""
        was_in_view = self._in_view(token.doc_start_pos)
        self._active_token = token
        self._refresh_selections()
        caret = QTextCursor(self.document())
        caret.setPosition(token.doc_start_pos)
        self.setTextCursor(caret)  # scrolls the least that shows the caret
        if center and not was_in_view:
            self._center_on_caret()
        else:
            self.ensureCursorVisible()

    def _in_view(self, position: int) -> bool:
        self.document().size()  # lays the whole text out: the rect is exact
        cursor = QTextCursor(self.document())
        cursor.setPosition(position)
        return self.viewport().rect().contains(self.cursorRect(cursor).center())

    def _center_on_caret(self) -> None:
        bar = self.verticalScrollBar()
        middle = self.viewport().height() // 2
        bar.setValue(bar.value() + self.cursorRect().center().y() - middle)

    def _refresh_selections(self) -> None:
        token = self._active_token
        if token is None:
            self.setExtraSelections([])
            return
        document = self.document()
        selections: list[QTextEdit.ExtraSelection] = []
        if self._focus_mode:
            line_start, line_end = self._line_range(token.doc_start_pos)
            for start, end in (
                (0, line_start),
                (line_end, document.characterCount() - 1),
            ):
                if end > start:
                    selections.append(self._selection(start, end, self._dim_format))
        ruler_cursor = QTextCursor(document)
        ruler_cursor.setPosition(token.doc_start_pos)
        ruler = QTextEdit.ExtraSelection()
        ruler.cursor = ruler_cursor
        ruler.format = self._ruler_format
        selections.append(ruler)
        selections.append(
            self._selection(token.doc_start_pos, token.doc_end_pos, self._word_format)
        )
        self.setExtraSelections(selections)

    def _selection(
        self, start: int, end: int, text_format: QTextCharFormat
    ) -> QTextEdit.ExtraSelection:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = text_format
        return selection

    def _line_range(self, position: int) -> tuple[int, int]:
        """Document range of the visual line that holds ``position``."""
        document = self.document()
        block = document.findBlock(position)
        document.documentLayout().blockBoundingRect(block)  # makes Qt lay the block out
        layout = block.layout()
        line = layout.lineForTextPosition(position - block.position())
        if layout is None or not line.isValid():
            return block.position(), block.position() + block.length() - 1
        start = block.position() + line.textStart()
        return start, start + line.textLength()

    def highlighted_range(self) -> tuple[int, int] | None:
        """Character range of the word currently highlighted, if any."""
        selections = self.extraSelections()
        if not selections:
            return None
        cursor = selections[-1].cursor
        return cursor.selectionStart(), cursor.selectionEnd()

    def clear_highlights(self) -> None:
        self._active_token = None
        self.setExtraSelections([])
