"""Page bar of the reading view: previous/next, page number and view mode."""

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

from clearread.ui.strings import Language, tr

BAR_MAX_WIDTH = 980
PAGE_SPIN_WIDTH = 72
BAR_PADDING_X = 24
BAR_PADDING_Y = 8
BAR_SPACING = 16


class PageBar(QFrame):
    def __init__(self, language: Language) -> None:
        super().__init__()
        self._language = language
        self.prev_page_button = QPushButton()
        self.next_page_button = QPushButton()
        self.page_spin = QSpinBox()
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.page_spin.setFixedWidth(PAGE_SPIN_WIDTH)
        self.page_total_label = QLabel()
        self.continuous_button = QPushButton()
        self.paged_button = QPushButton()
        group = QButtonGroup(self)
        for button in (self.continuous_button, self.paged_button):
            button.setCheckable(True)
            group.addButton(button)
        self._build_layout()
        self.hide()

    def _build_layout(self) -> None:
        content = QWidget()
        content.setMaximumWidth(BAR_MAX_WIDTH)
        row = QHBoxLayout(content)
        row.setContentsMargins(0, BAR_PADDING_Y, 0, 0)
        row.setSpacing(BAR_SPACING)
        row.addWidget(self.prev_page_button)
        row.addWidget(self.page_spin)
        row.addWidget(self.page_total_label)
        row.addWidget(self.next_page_button)
        row.addStretch(1)
        row.addWidget(self.continuous_button)
        row.addWidget(self.paged_button)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(BAR_PADDING_X, 0, BAR_PADDING_X, 0)
        outer.addWidget(content)

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def refresh_texts(self, total: int) -> None:
        for button, short_key, tip_key, shortcut_key in (
            (
                self.prev_page_button,
                "reading.prev_short",
                "reading.page_prev",
                "reading.key_page_prev",
            ),
            (
                self.next_page_button,
                "reading.next_short",
                "reading.page_next",
                "reading.key_page_next",
            ),
        ):
            button.setText(self._t(short_key))
            button.setToolTip(
                self._t(
                    "reading.tooltip",
                    action=self._t(tip_key),
                    shortcut=self._t(shortcut_key),
                )
            )
        self.page_spin.setAccessibleName(self._t("reading.page_field"))
        self.page_spin.setToolTip(self._t("reading.page_field"))
        self.continuous_button.setText(self._t("reading.mode_continuous"))
        self.paged_button.setText(self._t("reading.mode_paged"))
        for button in (self.continuous_button, self.paged_button):
            button.setToolTip(self._t("reading.mode_tooltip"))
        self.page_total_label.setText(self._t("reading.page_of", total=total))

    def show_page(self, index: int, count: int) -> None:
        """Show page ``index`` (0-based) of ``count`` without emitting the spin's signal."""
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, max(count, 1))
        self.page_spin.setValue(index + 1)
        self.page_spin.blockSignals(False)
        self.prev_page_button.setEnabled(index > 0)
        self.next_page_button.setEnabled(index < count - 1)

    def sync_mode(self, paged: bool) -> None:
        self.continuous_button.setChecked(not paged)
        self.paged_button.setChecked(paged)
