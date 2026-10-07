"""Theme tokens (design system 1.2) and the QSS built from them.

Only two brand colours exist: purple ``#392F5A`` and yellow ``#F4D06F``. Every other hex in
this module is a lighter or darker tone of one of them (design system 1.1); a test walks the
source and fails on any hex that is not.
"""

from dataclasses import asdict, dataclass
from enum import Enum
from string import Template

from clearread.services.text_formatter import SyllablePalette


class ThemeId(str, Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class ThemeTokens:
    bg: str
    surface: str
    text: str
    text_muted: str
    syllable_even: str
    syllable_odd: str
    syllable_odd_bg: str  # empty: odd syllables carry no background
    word_highlight_bg: str
    word_highlight_fg: str
    ruler_bg: str
    dim_text: str  # lines other than the active one in focus mode
    focus_ring: str
    focus_ring_primary: str
    primary_bg: str
    primary_fg: str
    primary_bg_hover: str
    primary_bg_pressed: str
    primary_border: str
    secondary: str
    secondary_bg_hover: str
    border: str
    track: str  # groove of sliders and progress bars
    track_border: str
    disabled_fg: str
    disabled_bg: str


THEMES: dict[ThemeId, ThemeTokens] = {
    ThemeId.LIGHT: ThemeTokens(
        bg="#EDE8F7",
        surface="#DDD4EF",
        text="#392F5A",
        text_muted="#43386B",
        syllable_even="#392F5A",
        syllable_odd="#392F5A",
        syllable_odd_bg="#FBF0CC",
        word_highlight_bg="#392F5A",
        word_highlight_fg="#F4D06F",
        ruler_bg="#D2C7EA",
        dim_text="#4F417C",
        focus_ring="#392F5A",
        focus_ring_primary="#392F5A",
        primary_bg="#F4D06F",
        primary_fg="#392F5A",
        primary_bg_hover="#F8E3A9",
        primary_bg_pressed="#FBF0CC",
        primary_border="#392F5A",
        secondary="#392F5A",
        secondary_bg_hover="#D2C7EA",
        border="#6B5C9E",
        track="#392F5A",
        track_border="#392F5A",
        disabled_fg="#43386B",
        disabled_bg="#DDD4EF",
    ),
    ThemeId.DARK: ThemeTokens(
        bg="#392F5A",
        surface="#2B2344",
        text="#E4DCF3",
        text_muted="#CFC4E8",
        syllable_even="#F4D06F",
        syllable_odd="#E4DCF3",
        syllable_odd_bg="",
        word_highlight_bg="#F4D06F",
        word_highlight_fg="#392F5A",
        ruler_bg="#2B2344",
        dim_text="#CFC4E8",
        focus_ring="#F4D06F",
        focus_ring_primary="#261F3C",
        primary_bg="#F4D06F",
        primary_fg="#392F5A",
        primary_bg_hover="#F8E3A9",
        primary_bg_pressed="#FBF0CC",
        primary_border="#F4D06F",
        secondary="#E4DCF3",
        secondary_bg_hover="#4A3D75",
        border="#9B8DC7",
        track="#261F3C",
        track_border="#9B8DC7",
        disabled_fg="#CFC4E8",
        disabled_bg="#2B2344",
    ),
}

# The focus ring shows only for keyboard focus (Tab / Backtab): the ``keyFocus`` property
# is set by ui/focus_ring.py, so a mouse click never draws it.
_STYLESHEET = Template(
    """
QWidget { background: $bg; color: $text; font-family: "Segoe UI"; font-size: 15px; }
QFrame#PlayBar { background: $surface; border: none; border-top: 1px solid $border; }
QLabel, QWidget#PlayBarContent { background: transparent; }
QLabel[role="muted"] { color: $text_muted; }

QPushButton { min-height: 40px; padding: 0 18px; border-radius: 8px;
              border: 2px solid $secondary; background: transparent; color: $secondary;
              font-weight: 600; }
QPushButton:hover { background: $secondary_bg_hover; }
QPushButton[keyFocus="true"] { border: 3px solid $focus_ring; padding: 0 17px; }
QPushButton:disabled { border: 2px dashed $border; background: $disabled_bg;
                       color: $disabled_fg; }
QPushButton[variant="primary"] { background: $primary_bg; color: $primary_fg;
                                 border-color: $primary_border; }
QPushButton[variant="primary"]:hover { background: $primary_bg_hover; }
QPushButton[variant="primary"]:pressed { background: $primary_bg_pressed; }
QPushButton[variant="primary"][keyFocus="true"] { border: 3px solid $focus_ring_primary; }
QPushButton[variant="ghost"] { border-color: transparent; }
QPushButton[variant="ghost"][keyFocus="true"] { border: 3px solid $focus_ring; }
QPushButton:checked { background: $secondary_bg_hover; }

QSlider::groove:horizontal { height: 8px; border-radius: 4px; background: $track;
                             border: 1px solid $track_border; }
QSlider::sub-page:horizontal { border-radius: 4px; background: $primary_bg; }
QSlider::handle:horizontal { width: 20px; height: 20px; margin: -8px 0;
                             border-radius: 12px; background: $primary_bg;
                             border: 2px solid $track_border; }
QSlider[keyFocus="true"]::handle:horizontal { border: 3px solid $focus_ring; }

QFrame#TopBar { background: $surface; border: none; border-bottom: 1px solid $border; }
QLabel#Brand { font-size: 18px; font-weight: 700; }
QLabel[role="heading"] { font-size: 20px; font-weight: 700; }
QLabel[role="title"] { font-size: 24px; font-weight: 700; }
QLabel[role="stat"] { font-size: 28px; font-weight: 700; }
QFrame#DropZone { border: 2px dashed $border; border-radius: 16px; background: transparent; }
QFrame#DropZone[dragging="true"] { border-color: $text; background: $ruler_bg; }
QFrame#RecentItem, QFrame#Card { background: $surface; border: 1px solid $border;
                                 border-radius: 12px; }
QFrame#RecentItem:hover { background: $secondary_bg_hover; }
QFrame#RecentItem QLabel, QFrame#Card QLabel, QFrame#DropZone QLabel { border: none; }
QFrame#ProcessingCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#ProcessingCard QLabel { border: none; }
QProgressBar { min-height: 12px; max-height: 12px; border: 1px solid $track_border;
               border-radius: 6px; background: $track; text-align: center; color: transparent; }
QProgressBar::chunk { background: $primary_bg; border-radius: 5px; }
QDialog#ErrorDialog { background: $bg; border: 2px solid $text; }
QFrame#ActionBox { background: $surface; border: 1px solid $border; border-radius: 8px; }
QFrame#ActionBox QLabel { border: none; }
QLabel#ErrorMark { border: 3px solid $text; border-radius: 22px; color: $text;
                   font-size: 22px; font-weight: 700; }

QFrame#ThemeCard { border: 2px solid $border; border-radius: 12px; background: transparent; }
QFrame#ThemeCard[selected="true"] { border: 3px solid $text; }
QFrame#PreviewCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#PreviewCard QLabel { border: none; }
QComboBox, QLineEdit { min-height: 40px; padding: 0 12px; border: 2px solid $border;
                       border-radius: 8px; background: $bg; color: $text; }
QComboBox[keyFocus="true"], QLineEdit[keyFocus="true"] { border: 3px solid $focus_ring;
                                                         padding: 0 11px; }
QComboBox::drop-down { border: none; width: 32px; }
QComboBox QAbstractItemView { background: $bg; color: $text; border: 2px solid $border;
                              selection-background-color: $secondary_bg_hover;
                              selection-color: $text; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 22px; height: 22px; border: 2px solid $secondary;
                       border-radius: 6px; background: transparent; }
QCheckBox::indicator:checked { background: $primary_bg; border-color: $secondary; }
QCheckBox[keyFocus="true"]::indicator { border: 3px solid $focus_ring; }
QRadioButton { spacing: 8px; }
QRadioButton::indicator { width: 18px; height: 18px; border: 2px solid $secondary;
                          border-radius: 11px; background: transparent; }
QRadioButton::indicator:checked { background: $primary_bg; }
QRadioButton[keyFocus="true"]::indicator { border: 3px solid $focus_ring; }
QMessageBox { background: $bg; }
QMenu { background: $bg; color: $text; border: 1px solid $border; padding: 4px; }
QMenu::item { padding: 8px 20px; border-radius: 6px; }
QMenu::item:selected { background: $secondary_bg_hover; color: $text; }
QScrollBar:vertical { width: 14px; background: $bg; }
QScrollBar::handle:vertical { background: $border; border-radius: 6px; min-height: 32px;
                              margin: 2px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: $bg; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }

QFrame#AIPanel { background: $surface; border: none; border-left: 1px solid $border; }
QWidget#AIPage, QStackedWidget#AIPage { background: transparent; }
QFrame#AICard { background: $bg; border: 1px solid $border; border-radius: 12px; }
QFrame#PrivacyCard { background: $bg; border: 2px solid $text; border-radius: 12px; }
QFrame#AICard QLabel, QFrame#PrivacyCard QLabel { border: none; }
QFrame#AICard QLabel#ErrorMark { border: 3px solid $text; border-radius: 20px; }
QLabel#WordChip { background: $word_highlight_bg; color: $word_highlight_fg;
                  border-radius: 8px; padding: 4px 12px; font-weight: 700; }
QLabel#OfflineBadge { border: 1px solid $border; border-radius: 12px; padding: 2px 10px;
                      font-size: 13px; font-weight: 600; }
QPushButton#AssistantToggle:checked { background: $secondary_bg_hover; }

QToolTip { background: $text; color: $bg; border: none; padding: 8px 12px; font-size: 13px; }
"""
)


def build_stylesheet(tokens: ThemeTokens) -> str:
    return _STYLESHEET.substitute(asdict(tokens))


def syllable_palette(tokens: ThemeTokens) -> SyllablePalette:
    return SyllablePalette(
        color_even=tokens.syllable_even,
        color_odd=tokens.syllable_odd,
        background_odd=tokens.syllable_odd_bg or None,
    )
