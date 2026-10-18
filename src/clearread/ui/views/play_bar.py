"""Play bar of the reading view: play/pause, stop, focus mode, speed and word counter."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from clearread.services.tts_controller import (
    DEFAULT_RATE_WPM,
    MAX_RATE_WPM,
    MIN_RATE_WPM,
)
from clearread.ui.views.page_bar import (
    BAR_MAX_WIDTH,
    BAR_PADDING_X,
    BAR_PADDING_Y,
    BAR_SPACING,
)

PLAY_BAR_HEIGHT = 80
PLAY_BUTTON_SIZE = (148, 48)
SPEED_SLIDER_WIDTH = 230


class PlayBar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PlayBar")
        self.setFixedHeight(PLAY_BAR_HEIGHT)
        self.play_button = QPushButton()
        self.play_button.setProperty("variant", "primary")
        self.play_button.setFixedSize(*PLAY_BUTTON_SIZE)
        self.stop_button = QPushButton()
        self.stop_button.setFixedHeight(PLAY_BUTTON_SIZE[1])
        self.focus_button = QPushButton()
        self.focus_button.setCheckable(True)
        self.focus_button.setFixedHeight(PLAY_BUTTON_SIZE[1])
        self.speed_label = QLabel()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(MIN_RATE_WPM, MAX_RATE_WPM)
        self.speed_slider.setValue(DEFAULT_RATE_WPM)
        self.speed_slider.setFixedWidth(SPEED_SLIDER_WIDTH)
        self.speed_value_label = QLabel()
        self.counter_label = QLabel()
        self._build_layout()

    def _speed_column(self) -> QVBoxLayout:
        header = QHBoxLayout()
        header.addWidget(self.speed_label)
        header.addStretch(1)
        header.addWidget(self.speed_value_label)
        speed = QVBoxLayout()
        speed.setSpacing(0)
        speed.addLayout(header)
        speed.addWidget(self.speed_slider)
        return speed

    def _build_layout(self) -> None:
        info = QVBoxLayout()
        info.setSpacing(0)
        info.addWidget(self.counter_label)

        content = QWidget()
        content.setObjectName("PlayBarContent")
        content.setMaximumWidth(BAR_MAX_WIDTH)
        row = QHBoxLayout(content)
        row.setContentsMargins(0, BAR_PADDING_Y, 0, BAR_PADDING_Y)
        row.setSpacing(BAR_SPACING)
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.focus_button)
        row.addLayout(self._speed_column())
        row.addStretch(1)
        row.addLayout(info)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(BAR_PADDING_X, 0, BAR_PADDING_X, 0)
        outer.addStretch(1)
        outer.addWidget(content, stretch=3)
        outer.addStretch(1)
