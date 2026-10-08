import difflib
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest
from samples.make_samples import EXPECTED_LINES, SAMPLES_DIR

from clearread.services.ocr_engine import (
    ClearReadOCR,
    OCRSettings,
    TextBox,
    build_paragraphs,
    is_letter_noise,
    merge_lines,
)

SPECIAL_CHARS = set("áéíóúüñÑ¿¡")


def box(
    text: str, left: float, top: float, width: float = 200, height: float = 20
) -> TextBox:
    return TextBox(text, left, top, left + width, top + height)


def test_reading_order_is_top_to_bottom_whatever_the_input_order() -> None:
    boxes = [box("tercera", 10, 100), box("primera", 10, 20), box("segunda", 10, 60)]
    assert build_paragraphs(boxes) == ["primera segunda tercera"]


def test_two_boxes_at_same_height_form_one_line_left_to_right() -> None:
    boxes = [box("mundo", 300, 22), box("Hola", 10, 20), box("abajo", 10, 60)]
    assert build_paragraphs(boxes) == ["Hola mundo abajo"]


def test_slightly_misaligned_fragments_stay_on_one_line() -> None:
    boxes = [box("uno", 10, 20), box("dos", 250, 27), box("tres", 10, 60)]
    assert build_paragraphs(boxes) == ["uno dos tres"]


def test_large_vertical_gap_starts_a_new_paragraph() -> None:
    boxes = [box("a", 10, 20), box("b", 10, 50), box("c", 10, 150)]
    assert build_paragraphs(boxes) == ["a b", "c"]


def test_empty_input_gives_no_paragraphs() -> None:
    assert build_paragraphs([]) == []


def test_end_of_line_hyphen_is_removed() -> None:
    assert merge_lines(["la cons-", "trucción de casas"]) == "la construcción de casas"


def test_hyphen_inside_a_word_is_kept() -> None:
    assert (
        merge_lines(["el hispano-americano", "llegó ayer"])
        == "el hispano-americano llegó ayer"
    )


def test_hyphen_before_uppercase_is_kept_without_space() -> None:
    assert (
        merge_lines(["la ruta Madrid-", "Barcelona es larga"])
        == "la ruta Madrid-Barcelona es larga"
    )


def test_dash_after_space_is_not_dehyphenated() -> None:
    assert merge_lines(["esto -", "aquello"]) == "esto - aquello"


def test_hyphenated_line_inside_paragraph_is_merged_end_to_end() -> None:
    boxes = [box("la cons-", 10, 20), box("trucción nueva", 10, 45)]
    assert build_paragraphs(boxes) == ["la construcción nueva"]


@pytest.fixture(scope="module")
def engine() -> ClearReadOCR:
    return ClearReadOCR()


def render_scanned_sample() -> np.ndarray:
    document = pdfium.PdfDocument(str(SAMPLES_DIR / "sample_page_scanned.pdf"))
    try:
        return np.array(document[0].render(scale=300 / 72).to_pil().convert("RGB"))
    finally:
        document.close()


def special_hits(expected: str, obtained: str) -> int:
    matcher = difflib.SequenceMatcher(None, expected, obtained, autojunk=False)
    return sum(
        ch in SPECIAL_CHARS
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes()
        if tag == "equal"
        for ch in expected[i1:i2]
    )


def test_scanned_sample_recognises_all_21_special_characters(
    engine: ClearReadOCR,
) -> None:
    result = engine.process_image(render_scanned_sample(), page_number=3)
    expected = " ".join(EXPECTED_LINES)
    assert sum(ch in SPECIAL_CHARS for ch in expected) == 21
    assert special_hits(expected, " ".join(result.raw_text.split())) == 21
    assert result.page_number == 3
    assert result.processing_time_ms > 0


def test_blank_page_returns_empty_text_with_real_elapsed_time(
    engine: ClearReadOCR,
) -> None:
    result = engine.process_image(np.full((200, 300, 3), 255, np.uint8))
    assert result.raw_text == ""
    assert result.processing_time_ms > 0


def test_grayscale_input_is_accepted(engine: ClearReadOCR) -> None:
    gray = render_scanned_sample().mean(axis=2).astype(np.uint8)
    assert "niño" in engine.process_image(gray).raw_text.lower()


def test_missing_recognition_model_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ClearReadOCR(rec_model_path=tmp_path / "absent.onnx")


def test_confidence_threshold_above_one_drops_everything() -> None:
    strict = ClearReadOCR(OCRSettings(min_confidence=1.01))
    assert strict.process_image(render_scanned_sample()).raw_text == ""


def test_result_reports_line_count_and_mean_confidence(engine: ClearReadOCR) -> None:
    result = engine.process_image(render_scanned_sample())
    assert result.line_count == len(EXPECTED_LINES)
    assert 0.8 < result.mean_confidence <= 1.0


def test_blank_page_has_zero_confidence_and_no_lines(engine: ClearReadOCR) -> None:
    result = engine.process_image(np.full((200, 300, 3), 255, np.uint8))
    assert (result.line_count, result.mean_confidence) == (0, 0.0)


@pytest.mark.parametrize(
    ("text", "score", "noise"),
    [
        ("n n e e d", 0.6, True),
        ("n", 0.55, True),
        ("ee", 0.7, True),
        ("n n e e d", 0.95, False),  # read with certainty: kept
        ("y", 0.99, False),
        ("de la", 0.6, True),
        ("casa", 0.6, False),  # a real word is never noise
        ("1 2 3", 0.6, False),  # digits are not letter noise
        ("3", 0.6, False),
        ("n n casa", 0.6, False),
    ],
)
def test_letter_noise_needs_only_short_letter_fragments_and_low_confidence(
    text: str, score: float, noise: bool
) -> None:
    assert is_letter_noise(text, score, OCRSettings().noise_confidence) is noise
