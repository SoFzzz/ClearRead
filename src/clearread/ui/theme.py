"""Theme tokens (design system section 1.2) and the QSS built from them."""

from dataclasses import asdict, dataclass
from enum import Enum
from string import Template

from clearread.services.text_formatter import SyllablePalette


class ThemeId(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    HIGH_CONTRAST = "high_contrast"


@dataclass(frozen=True)
class ThemeTokens:
    bg: str
    surface: str
    text: str
    text_muted: str
    syllable_even: str
    syllable_odd: str
    word_highlight_bg: str
    word_highlight_fg: str
    ruler_bg: str
    focus_ring: str
    primary_bg: str
    primary_fg: str
    primary_bg_hover: str
    primary_bg_pressed: str
    secondary: str
    secondary_bg_hover: str
    border: str
    error: str
    success: str
    disabled_fg: str
    disabled_bg: str


THEMES: dict[ThemeId, ThemeTokens] = {
    ThemeId.LIGHT: ThemeTokens(
        bg="#FFF8F0",
        surface="#F5EEE8",
        text="#392F5A",
        text_muted="#4F417C",
        syllable_even="#392F5A",
        syllable_odd="#703800",
        word_highlight_bg="#F4D06F",
        word_highlight_fg="#392F5A",
        ruler_bg="#E2EFE7",
        focus_ring="#2E766D",
        primary_bg="#392F5A",
        primary_fg="#FFF8F0",
        primary_bg_hover="#4A3D75",
        primary_bg_pressed="#261F3C",
        secondary="#392F5A",
        secondary_bg_hover="#E2EFE7",
        border="#7968B0",
        error="#A85400",
        success="#2E766D",
        disabled_fg="#4F417C",
        disabled_bg="#F5EEE8",
    ),
    ThemeId.DARK: ThemeTokens(
        bg="#392F5A",
        surface="#2B2344",
        text="#FFF8F0",
        text_muted="#D7D0D2",
        syllable_even="#F4D06F",
        syllable_odd="#9DD9D2",
        word_highlight_bg="#F4D06F",
        word_highlight_fg="#392F5A",
        ruler_bg="#2B2344",
        focus_ring="#9DD9D2",
        primary_bg="#F4D06F",
        primary_fg="#392F5A",
        primary_bg_hover="#F8E3A9",
        primary_bg_pressed="#FFF8F0",
        secondary="#FFF8F0",
        secondary_bg_hover="#2B2344",
        border="#9C94A5",
        error="#FF8811",
        success="#9DD9D2",
        disabled_fg="#D7D0D2",
        disabled_bg="#2B2344",
    ),
    ThemeId.HIGH_CONTRAST: ThemeTokens(
        bg="#000000",
        surface="#000000",
        text="#FFFFFF",
        text_muted="#FFFFFF",
        syllable_even="#FFFFFF",
        syllable_odd="#9DD9D2",
        word_highlight_bg="#F4D06F",
        word_highlight_fg="#000000",
        ruler_bg="#333333",
        focus_ring="#9DD9D2",
        primary_bg="#FFFFFF",
        primary_fg="#000000",
        primary_bg_hover="#F4D06F",
        primary_bg_pressed="#9DD9D2",
        secondary="#FFFFFF",
        secondary_bg_hover="#333333",
        border="#FFFFFF",
        error="#FF8811",
        success="#9DD9D2",
        disabled_fg="#FFFFFF",
        disabled_bg="#000000",
    ),
}

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
QPushButton:focus { border: 3px solid $focus_ring; padding: 0 17px; }
QPushButton:disabled { border: 2px dashed $border; background: $disabled_bg;
                       color: $disabled_fg; }
QPushButton[variant="primary"] { background: $primary_bg; color: $primary_fg;
                                 border-color: $primary_bg; }
QPushButton[variant="primary"]:hover { background: $primary_bg_hover;
                                       border-color: $primary_bg_hover; }
QPushButton[variant="primary"]:pressed { background: $primary_bg_pressed;
                                         border-color: $primary_bg_pressed; }
QPushButton[variant="primary"]:focus { border: 3px solid $focus_ring; }

QSlider::groove:horizontal { height: 6px; border-radius: 3px; background: $border; }
QSlider::sub-page:horizontal { border-radius: 3px; background: $primary_bg; }
QSlider::handle:horizontal { width: 20px; height: 20px; margin: -7px 0;
                             border-radius: 10px; background: $primary_bg;
                             border: 2px solid $bg; }

QFrame#TopBar { background: $surface; border: none; border-bottom: 1px solid $border; }
QLabel#Brand { font-size: 18px; font-weight: 700; }
QLabel[role="heading"] { font-size: 20px; font-weight: 700; }
QLabel[role="title"] { font-size: 24px; font-weight: 700; }
QFrame#DropZone { border: 2px dashed $border; border-radius: 16px; background: transparent; }
QFrame#DropZone[dragging="true"] { border-color: $focus_ring; background: $ruler_bg; }
QFrame#RecentItem { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#RecentItem:hover { background: $secondary_bg_hover; }
QFrame#RecentItem QLabel, QFrame#DropZone QLabel { border: none; }
QFrame#ProcessingCard { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#ProcessingCard QLabel { border: none; }
QProgressBar { min-height: 14px; max-height: 14px; border: 1px solid $border; border-radius: 7px;
               background: $bg; text-align: center; color: transparent; }
QProgressBar::chunk { background: $primary_bg; border-radius: 6px; }
QDialog#ErrorDialog { background: $bg; border: 2px solid $text; }
QFrame#ActionBox { background: $surface; border: 1px solid $border; border-radius: 8px; }
QFrame#ActionBox QLabel { border: none; }
QLabel#ErrorMark { border: 3px solid $error; border-radius: 22px; color: $error;
                   font-size: 22px; font-weight: 700; }

QToolTip { background: $text; color: $bg; border: none; padding: 8px 12px; font-size: 13px; }
"""
)


def build_stylesheet(tokens: ThemeTokens) -> str:
    return _STYLESHEET.substitute(asdict(tokens))


def syllable_palette(tokens: ThemeTokens) -> SyllablePalette:
    return SyllablePalette(
        color_even=tokens.syllable_even, color_odd=tokens.syllable_odd
    )
