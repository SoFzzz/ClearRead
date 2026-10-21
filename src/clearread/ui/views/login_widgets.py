"""Small widgets of the login screens (design system A.3.11 to A.3.15)."""

from itertools import pairwise

from PySide6.QtCore import QEvent, QObject, QSize, Qt, Signal
from PySide6.QtGui import (
    QAccessible,
    QAccessibleEvent,
    QColor,
    QFocusEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from clearread.ui.focus_ring import KEYBOARD_REASONS
from clearread.ui.icons import load_icon
from clearread.ui.strings import Language, tr
from clearread.ui.theme import ThemeTokens

MARK_SIZE = 20
GOOGLE_ICON_PX = 20
# The same limits the backend enforces.
NAME_MAX_CHARS = 32
EMAIL_MAX_CHARS = 64
PASSWORD_MAX_CHARS = 32


def set_variant(button: QPushButton, variant: str) -> QPushButton:
    button.setProperty("variant", variant)
    return button


def plain(widget: QWidget) -> QWidget:
    """Let the card colour show through a container."""
    widget.setProperty("role", "plain")
    return widget


def link_button(text: str) -> QPushButton:
    button = set_variant(QPushButton(text), "link")
    font = button.font()
    font.setUnderline(True)
    button.setFont(font)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def announce_alert(widget: QWidget) -> None:
    """Tell assistive technology that a message just appeared."""
    QAccessible.updateAccessibility(QAccessibleEvent(widget, QAccessible.Event.Alert))


def announce_name_change(widget: QWidget) -> None:
    """Refresh the accessible name quietly, without the system alert sound."""
    QAccessible.updateAccessibility(
        QAccessibleEvent(widget, QAccessible.Event.NameChanged)
    )


def text_label(text: str, role: str | None = None) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    return label


class InlineMessage(QWidget):
    """Icon "!" and text, never colour alone (A.3.13)."""

    def __init__(self, mark: str = "!") -> None:
        super().__init__()
        plain(self)
        self._mark = QLabel(mark)
        self._mark.setObjectName("InlineMark")
        self._mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mark.setFixedSize(MARK_SIZE, MARK_SIZE)
        self._text = QLabel()
        self._text.setWordWrap(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._mark, alignment=Qt.AlignmentFlag.AlignTop)
        row.addWidget(self._text, stretch=1)
        self.hide()

    @property
    def text(self) -> str:
        return self._text.text()

    def show_message(
        self, text: str, announce: bool = True, urgent: bool = True
    ) -> None:
        """Show ``text``; tell assistive technology only when it is new.

        ``urgent=False`` is for hints that update while the user types: an
        Alert event makes Windows play a system sound, so they use a quiet
        name change instead.
        """
        changed = text != self._text.text() or self.isHidden()
        self._text.setText(text)
        self._text.setAccessibleName(text)
        self.show()
        if not (announce and changed):
            return
        if urgent:
            announce_alert(self._text)
        else:
            announce_name_change(self._text)

    def clear(self) -> None:
        self._text.clear()
        self.hide()


class PasswordField(QFrame):
    """Password edit with a text button that shows or hides it (A.3.12)."""

    def __init__(self, language: Language) -> None:
        super().__init__()
        self.setObjectName("PasswordBox")
        self._language = language
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setMaxLength(PASSWORD_MAX_CHARS)
        self.edit.installEventFilter(self)
        self.toggle = link_button(tr("auth.show_password", language))
        self.toggle.setAccessibleName(tr("auth.show_password_a11y", language))
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self._on_toggled)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 4, 0)
        row.setSpacing(0)
        row.addWidget(self.edit, stretch=1)
        row.addWidget(self.toggle)

    @property
    def revealed(self) -> bool:
        return self.toggle.isChecked()

    def set_blocked(self, blocked: bool) -> None:
        self.edit.setEnabled(not blocked)
        self.toggle.setEnabled(not blocked)
        self.setProperty("blocked", blocked)
        self.style().unpolish(self)
        self.style().polish(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # The box draws the ring around both parts, so it follows the edit's keyboard focus.
        if watched is self.edit:
            if event.type() == QEvent.Type.FocusIn and isinstance(event, QFocusEvent):
                self._mark_focus(event.reason() in KEYBOARD_REASONS)
            elif event.type() == QEvent.Type.FocusOut:
                self._mark_focus(False)
        return False

    def _mark_focus(self, keyboard: bool) -> None:
        self.setProperty("keyFocus", keyboard)
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_toggled(self, shown: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        self.edit.setEchoMode(mode)
        word, accessible = (
            ("auth.hide_password", "auth.hide_password_a11y")
            if shown
            else ("auth.show_password", "auth.show_password_a11y")
        )
        self.toggle.setText(tr(word, self._language))
        self.toggle.setAccessibleName(tr(accessible, self._language))


def make_text_edit(max_chars: int) -> QLineEdit:
    edit = QLineEdit()
    edit.setMaxLength(max_chars)
    edit.setInputMethodHints(
        Qt.InputMethodHint.ImhNoAutoUppercase | Qt.InputMethodHint.ImhNoPredictiveText
    )
    return edit


class FieldBlock(QWidget):
    """Label above the field and its inline message below (A.3.11)."""

    def __init__(
        self, label_text: str, edit: QLineEdit, box: QWidget | None = None
    ) -> None:
        super().__init__()
        plain(self)
        self.edit = edit
        self.label = QLabel(label_text)
        self.label.setProperty("role", "field-label")
        self.label.setBuddy(edit)
        edit.setAccessibleName(label_text)
        self.message = InlineMessage()
        self._box = box
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(self.label)
        column.addWidget(box if box is not None else edit)
        column.addWidget(self.message)

    def set_blocked(self, blocked: bool) -> None:
        if isinstance(self._box, PasswordField):
            self._box.set_blocked(blocked)
        else:
            self.edit.setEnabled(not blocked)


def email_block(label_text: str) -> FieldBlock:
    return FieldBlock(label_text, make_text_edit(EMAIL_MAX_CHARS))


def password_block(
    label_text: str, language: Language
) -> tuple[FieldBlock, PasswordField]:
    field = PasswordField(language)
    return FieldBlock(label_text, field.edit, field), field


class BusyStrip(QWidget):
    """Indeterminate bar, and the "waking the server" line with its Cancel button."""

    cancel_requested = Signal()

    def __init__(self, tokens: ThemeTokens, language: Language) -> None:
        super().__init__()
        plain(self)
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setProperty("compact", True)
        icon = QLabel()
        icon.setPixmap(load_icon("clock", tokens.text).pixmap(20, 20))
        text = text_label(tr("auth.waking", language))
        cancel = set_variant(QPushButton(tr("common.cancel", language)), "ghost")
        cancel.clicked.connect(self.cancel_requested)
        self._waking = plain(QWidget())
        wake_row = QHBoxLayout(self._waking)
        wake_row.setContentsMargins(0, 0, 0, 0)
        wake_row.setSpacing(8)
        wake_row.addWidget(icon, alignment=Qt.AlignmentFlag.AlignTop)
        wake_row.addWidget(text, stretch=1)
        wake_row.addWidget(cancel)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(self._bar)
        column.addWidget(self._waking)
        self.hide()

    @property
    def waking_visible(self) -> bool:
        return not self._waking.isHidden()

    def show_busy(self, waking: bool) -> None:
        self._waking.setVisible(waking)
        self.show()

    def hide_busy(self) -> None:
        self.hide()


class ConsentRow(QWidget):
    """Checkbox with its sentence on the right; the sentence toggles it too (A.3.15)."""

    toggled = Signal(bool)

    def __init__(self, text: str, mark_color: str) -> None:
        super().__init__()
        plain(self)
        self.check = _MarkedCheckBox(mark_color)
        self.check.setAccessibleName(text)
        self.check.toggled.connect(self.toggled)
        self._label = _ClickableLabel(text, self.check)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self.check, alignment=Qt.AlignmentFlag.AlignTop)
        row.addWidget(self._label, stretch=1)


class _MarkedCheckBox(QCheckBox):
    """The yellow box carries a tick, so it reads as checked without the colour."""

    def __init__(self, mark_color: str) -> None:
        super().__init__()
        self._mark_color = QColor(mark_color)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        box = self.style().subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator, option, self
        )
        painter = QPainter(self)
        painter.setPen(self._mark_color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "✓")
        painter.end()


class _ClickableLabel(QLabel):
    def __init__(self, text: str, target: QCheckBox) -> None:
        super().__init__(text)
        self._target = target
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._target.isEnabled():
            self._target.toggle()
        super().mousePressEvent(event)


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    return line


def google_button(text: str) -> QPushButton:
    """Secondary button with Google's own multicolour "G" (design doc A.11)."""
    button = QPushButton(text)
    button.setIcon(load_icon("google_g", ""))
    button.setIconSize(QSize(GOOGLE_ICON_PX, GOOGLE_ICON_PX))
    return button


def divider_with_text(text: str) -> QWidget:
    """A thin line, a short muted text and another line (A.4.11)."""
    row = plain(QWidget())
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    layout.addWidget(separator(), stretch=1)
    layout.addWidget(text_label(text, "note"))
    layout.addWidget(separator(), stretch=1)
    return row


def height_at_width(layout: QLayout, width: int) -> int:
    """Height a column needs at ``width``; wrapped text needs less than at its own hint."""
    if layout.hasHeightForWidth():
        return layout.totalHeightForWidth(width)
    return layout.totalSizeHint().height()


class CurrentPageStack(QStackedWidget):
    """A stack as big as the page shown, not as the tallest page it holds."""

    def __init__(self) -> None:
        super().__init__()
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def sizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.sizeHint() if page is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        page = self.currentWidget()
        return page.minimumSizeHint() if page is not None else super().minimumSizeHint()


class WrappingColumn(QWidget):
    """A column of fixed width whose height follows the wrapped text inside it."""

    def __init__(self, width: int, spacing: int) -> None:
        super().__init__()
        plain(self)
        self._width = width
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(spacing)

    def sizeHint(self) -> QSize:
        return QSize(self._width, height_at_width(self.column, self._width))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def hasHeightForWidth(self) -> bool:
        return False  # the size hint already is the height at the fixed width


def chain_tab_order(widgets: tuple[QWidget, ...]) -> None:
    for first, second in pairwise(widgets):
        QWidget.setTabOrder(first, second)
