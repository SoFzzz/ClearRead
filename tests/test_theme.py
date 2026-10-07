"""Every contrast ratio of design system section 1.3 is recomputed with the W3C formula."""

import pytest

from clearread.ui.theme import (
    THEMES,
    ThemeId,
    ThemeTokens,
    build_stylesheet,
    syllable_palette,
)

TEXT_MIN = 7.0
NON_TEXT_MIN = 3.0


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(a: str, b: str) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


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
    ("primary_fg", "primary_bg"),
    ("primary_fg", "primary_bg_hover"),
    ("primary_fg", "primary_bg_pressed"),
    ("disabled_fg", "disabled_bg"),
]
NON_TEXT_PAIRS = [
    ("border", "bg"),
    ("focus_ring", "bg"),
    ("error", "bg"),
    ("primary_bg", "bg"),
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


def test_documented_light_ratios_match_the_design_system() -> None:
    light = THEMES[ThemeId.LIGHT]
    assert ratio(light.text, light.bg) == pytest.approx(11.54, abs=0.01)
    assert ratio(light.syllable_odd, light.bg) == pytest.approx(8.84, abs=0.01)
    assert ratio(light.word_highlight_fg, light.word_highlight_bg) == pytest.approx(
        8.16, abs=0.01
    )


def test_every_theme_defines_every_token() -> None:
    assert set(THEMES) == set(ThemeId)
    assert all(
        isinstance(value, str) and value.startswith("#")
        for t in THEMES.values()
        for value in vars(t).values()
    )


def test_syllable_palette_comes_from_the_theme() -> None:
    palette = syllable_palette(THEMES[ThemeId.DARK])
    assert (palette.color_even, palette.color_odd) == ("#F4D06F", "#9DD9D2")


def test_stylesheet_has_no_unfilled_placeholder() -> None:
    for tokens in THEMES.values():
        sheet = build_stylesheet(tokens)
        assert "$" not in sheet
        assert tokens.focus_ring in sheet


def test_tokens_are_immutable() -> None:
    with pytest.raises(AttributeError):
        THEMES[ThemeId.LIGHT].bg = "#000000"  # type: ignore[misc]


def test_theme_ids_are_the_values_stored_in_appconfig() -> None:
    assert [t.value for t in ThemeId] == ["light", "dark", "high_contrast"]
    assert isinstance(THEMES[ThemeId.LIGHT], ThemeTokens)
