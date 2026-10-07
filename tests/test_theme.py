"""Contrast of every token (design system 1.3) and the two-colour palette rule (1.1)."""

import colorsys
import re
from pathlib import Path

import pytest

from clearread.core.config import THEME_IDS
from clearread.ui.strings import CATALOG
from clearread.ui.theme import (
    THEMES,
    ThemeId,
    ThemeTokens,
    build_stylesheet,
    syllable_palette,
)

TEXT_MIN = 7.0
NON_TEXT_MIN = 3.0
SRC = Path(__file__).resolve().parents[1] / "src" / "clearread"
ICONS = Path(__file__).resolve().parents[1] / "resources" / "icons"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
HUE_TOLERANCE_DEG = 10.0

# Every colour the app may use, with the brand colour it is a tone of (design system 1.1).
PURPLE_HUE_DEG = 254.0
YELLOW_HUE_DEG = 44.0
PALETTE = {
    "#392F5A": "purple",  # brand
    "#F4D06F": "yellow",  # brand
    "#EDE8F7": "purple",  # light: background
    "#DDD4EF": "purple",  # light: surfaces
    "#D2C7EA": "purple",  # light: ruler, hover
    "#6B5C9E": "purple",  # light: borders
    "#43386B": "purple",  # light: secondary text
    "#4F417C": "purple",  # light: dimmed lines (focus mode)
    "#FBF0CC": "yellow",  # light: odd-syllable fill, pressed primary
    "#F8E3A9": "yellow",  # hover primary
    "#E4DCF3": "purple",  # dark: text
    "#CFC4E8": "purple",  # dark: secondary text, dimmed lines
    "#9B8DC7": "purple",  # dark: borders
    "#2B2344": "purple",  # dark: surfaces
    "#261F3C": "purple",  # dark: tracks, focus ring on yellow
    "#4A3D75": "purple",  # dark: hover
}


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a: str, b: str) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def hue_degrees(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def hue_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


TEXT_PAIRS = [
    ("text", "bg"),
    ("text", "surface"),
    ("text", "ruler_bg"),
    ("text_muted", "bg"),
    ("text_muted", "surface"),
    ("syllable_even", "bg"),
    ("syllable_even", "ruler_bg"),
    ("syllable_odd", "bg"),
    ("syllable_odd", "ruler_bg"),
    ("word_highlight_fg", "word_highlight_bg"),
    ("dim_text", "bg"),
    ("primary_fg", "primary_bg"),
    ("primary_fg", "primary_bg_hover"),
    ("primary_fg", "primary_bg_pressed"),
    ("secondary", "bg"),
    ("secondary", "surface"),
    ("secondary", "secondary_bg_hover"),
    ("disabled_fg", "disabled_bg"),
]
NON_TEXT_PAIRS = [
    ("border", "bg"),
    ("border", "surface"),
    ("focus_ring", "bg"),
    ("focus_ring", "surface"),
    ("focus_ring_primary", "primary_bg"),
    ("track_border", "bg"),
    ("primary_bg", "track"),
    ("word_highlight_bg", "bg"),
    ("primary_border", "bg"),
]


@pytest.mark.parametrize("theme_id", list(ThemeId))
@pytest.mark.parametrize(("fg", "bg"), TEXT_PAIRS)
def test_text_pairs_reach_7_to_1(theme_id: ThemeId, fg: str, bg: str) -> None:
    tokens = THEMES[theme_id]
    assert ratio(getattr(tokens, fg), getattr(tokens, bg)) >= TEXT_MIN


@pytest.mark.parametrize("theme_id", list(ThemeId))
@pytest.mark.parametrize(("fg", "bg"), NON_TEXT_PAIRS)
def test_non_text_pairs_reach_3_to_1(theme_id: ThemeId, fg: str, bg: str) -> None:
    tokens = THEMES[theme_id]
    assert ratio(getattr(tokens, fg), getattr(tokens, bg)) >= NON_TEXT_MIN


def test_odd_syllable_text_reaches_7_to_1_on_its_soft_fill() -> None:
    light = THEMES[ThemeId.LIGHT]
    assert ratio(light.syllable_odd, light.syllable_odd_bg) >= TEXT_MIN


def test_ratios_given_by_the_user_decisions() -> None:
    light, dark = THEMES[ThemeId.LIGHT], THEMES[ThemeId.DARK]
    assert ratio(light.text, light.bg) == pytest.approx(10.12, abs=0.01)
    assert ratio(dark.text, dark.bg) == pytest.approx(9.16, abs=0.01)
    assert ratio(light.primary_fg, light.primary_bg) == pytest.approx(8.16, abs=0.01)
    assert ratio(dark.primary_fg, dark.primary_bg) == pytest.approx(8.16, abs=0.01)
    assert ratio(light.syllable_odd, light.syllable_odd_bg) == pytest.approx(
        10.67, abs=0.01
    )


def test_primary_is_yellow_with_purple_text_in_both_themes() -> None:
    for tokens in THEMES.values():
        assert (tokens.primary_bg, tokens.primary_fg) == ("#F4D06F", "#392F5A")


def test_word_highlight_is_inverted_between_the_themes() -> None:
    light, dark = THEMES[ThemeId.LIGHT], THEMES[ThemeId.DARK]
    assert (light.word_highlight_bg, light.word_highlight_fg) == ("#392F5A", "#F4D06F")
    assert (dark.word_highlight_bg, dark.word_highlight_fg) == ("#F4D06F", "#392F5A")


def test_only_light_and_dark_exist_and_high_contrast_is_gone() -> None:
    assert [t.value for t in ThemeId] == ["light", "dark"]
    assert THEME_IDS == ("light", "dark")
    assert not [key for key in CATALOG if "high_contrast" in key]


def test_no_other_hue_than_the_two_brand_colours() -> None:
    for tone, origin in PALETTE.items():
        expected = PURPLE_HUE_DEG if origin == "purple" else YELLOW_HUE_DEG
        assert hue_distance(hue_degrees(tone), expected) <= HUE_TOLERANCE_DEG, tone


def test_theme_source_only_uses_palette_colours() -> None:
    used = {
        m.upper() for m in HEX.findall((SRC / "ui" / "theme.py").read_text("utf-8"))
    }
    assert used <= set(PALETTE), sorted(used - set(PALETTE))


def test_no_hex_colour_outside_theme_py_or_in_the_icons() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.name != "theme.py" and HEX.search(path.read_text("utf-8"))
    ]
    offenders += [
        p.name for p in ICONS.glob("*.svg") if HEX.search(p.read_text("utf-8"))
    ]
    assert offenders == []


def test_every_theme_defines_every_token() -> None:
    assert set(THEMES) == set(ThemeId)
    for tokens in THEMES.values():
        for name, value in vars(tokens).items():
            assert isinstance(value, str), name
            assert value == "" or value.upper() in PALETTE, (name, value)


def test_syllable_palette_comes_from_the_theme() -> None:
    dark = syllable_palette(THEMES[ThemeId.DARK])
    assert (dark.color_even, dark.color_odd, dark.background_odd) == (
        "#F4D06F",
        "#E4DCF3",
        None,
    )
    light = syllable_palette(THEMES[ThemeId.LIGHT])
    assert light.background_odd == "#FBF0CC"


def test_stylesheet_has_no_unfilled_placeholder() -> None:
    for tokens in THEMES.values():
        sheet = build_stylesheet(tokens)
        assert "$" not in sheet
        assert tokens.focus_ring in sheet


def test_focus_ring_only_for_keyboard_focus_in_the_stylesheet() -> None:
    sheet = build_stylesheet(THEMES[ThemeId.LIGHT])
    assert ":focus" not in sheet
    assert 'QPushButton[keyFocus="true"]' in sheet


def test_tokens_are_immutable() -> None:
    with pytest.raises(AttributeError):
        THEMES[ThemeId.LIGHT].bg = "#000000"  # type: ignore[misc]


def test_theme_ids_are_the_values_stored_in_appconfig() -> None:
    assert isinstance(THEMES[ThemeId.LIGHT], ThemeTokens)
