"""Keyboard-only focus ring (design system 2.1).

The QSS draws the ring for widgets whose ``keyFocus`` property is true. This filter sets it
when a widget gains focus through Tab or Backtab and clears it for any other reason, so a
mouse click never shows the ring.
"""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtWidgets import QWidget

KEYBOARD_REASONS = (
    Qt.FocusReason.TabFocusReason,
    Qt.FocusReason.BacktabFocusReason,
)


class KeyboardFocusRing(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QWidget):
            if event.type() == QEvent.Type.FocusIn and isinstance(event, QFocusEvent):
                self._mark(watched, event.reason() in KEYBOARD_REASONS)
            elif event.type() == QEvent.Type.FocusOut:
                self._mark(watched, False)
        return False

    @staticmethod
    def _mark(widget: QWidget, keyboard: bool) -> None:
        if bool(widget.property("keyFocus")) == keyboard:
            return
        widget.setProperty("keyFocus", keyboard)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
