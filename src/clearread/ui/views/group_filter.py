"""A row of chips to pick a group (library folder or glossary topic) plus its actions."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from clearread.services.groups import FILTER_ALL, NO_GROUP, Group
from clearread.ui.strings import Language, tr
from clearread.ui.views.flow_layout import FlowLayout

CHIP_NAME_CHARS = 24
CHIP_SPACING = 8


def _fixed(button: QPushButton) -> QPushButton:
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


class GroupFilter(QWidget):
    """``prefix`` picks the catalog keys: "folder" for the library, "topic" for words."""

    selection_changed = Signal(str)  # FILTER_ALL, NO_GROUP or a group id
    add_requested = Signal()
    rename_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, prefix: str, language: Language) -> None:
        super().__init__()
        self._prefix = prefix
        self._language = language
        self._selected = FILTER_ALL
        self.chips: dict[str, QPushButton] = {}
        self._flow = FlowLayout(spacing=CHIP_SPACING)
        chips_box = QWidget()
        chips_box.setLayout(self._flow)
        chips_box.setAccessibleName(self._t(f"{prefix}.label"))

        self.add_button = _fixed(QPushButton(self._t(f"{prefix}.add")))
        self.add_button.setProperty("variant", "chip")
        self.add_button.clicked.connect(self.add_requested)
        self.rename_button = _fixed(QPushButton(self._t(f"{prefix}.rename")))
        self.rename_button.setProperty("variant", "ghost")
        self.rename_button.clicked.connect(
            lambda: self.rename_requested.emit(self._selected)
        )
        self.delete_button = _fixed(QPushButton(self._t(f"{prefix}.delete")))
        self.delete_button.setProperty("variant", "ghost")
        self.delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self._selected)
        )
        self._actions = QWidget()
        actions = QHBoxLayout(self._actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.rename_button)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(CHIP_SPACING)
        layout.addWidget(chips_box)
        layout.addWidget(self._actions)

    @property
    def selected(self) -> str:
        return self._selected

    def _t(self, key: str, **params: object) -> str:
        return tr(key, self._language, **params)

    def set_groups(
        self, groups: list[Group], counts: dict[str, int], total: int
    ) -> None:
        """``counts`` maps a group id (or NO_GROUP) to how many items it holds."""
        valid = {FILTER_ALL, NO_GROUP, *(g.id for g in groups)}
        if self._selected not in valid:
            self._selected = FILTER_ALL
        self._clear_chips()
        self._add_chip(FILTER_ALL, self._t(f"{self._prefix}.all"), total)
        self._add_chip(
            NO_GROUP, self._t(f"{self._prefix}.none"), counts.get(NO_GROUP, 0)
        )
        for group in groups:
            self._add_chip(group.id, group.name, counts.get(group.id, 0))
        self._flow.addWidget(self.add_button)
        self._actions.setVisible(self._selected not in (FILTER_ALL, NO_GROUP))

    def _clear_chips(self) -> None:
        for chip in self.chips.values():
            self._flow.removeWidget(chip)
            chip.hide()
            chip.setParent(None)
            chip.deleteLater()
        self._flow.removeWidget(self.add_button)
        self.chips = {}

    def _add_chip(self, value: str, name: str, count: int) -> None:
        short = (
            name if len(name) <= CHIP_NAME_CHARS else name[: CHIP_NAME_CHARS - 1] + "…"
        )
        chip = _fixed(QPushButton(self._t("group.chip", name=short, count=count)))
        chip.setProperty("variant", "chip")
        chip.setCheckable(True)
        chip.setChecked(value == self._selected)
        chip.setToolTip(name)
        chip.setAccessibleName(self._t("group.chip", name=name, count=count))
        chip.clicked.connect(lambda: self._choose(value))
        self._flow.addWidget(chip)
        self.chips[value] = chip

    def _choose(self, value: str) -> None:
        self._selected = value
        for key, chip in self.chips.items():
            chip.setChecked(key == value)
        self._actions.setVisible(value not in (FILTER_ALL, NO_GROUP))
        self.selection_changed.emit(value)
