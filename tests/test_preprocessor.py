import time

import cv2
import numpy as np
import pytest

from clearread.services.preprocessor import OCRPreprocessor, PreprocessSettings


def make_text_page(angle: float = 0.0) -> np.ndarray:
    page = np.full((900, 700), 255, np.uint8)
    for row in range(8):
        y = 120 + row * 80
        cv2.putText(
            page,
            "Hola mundo lectura facil",
            (60, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            0,
            3,
        )
    if angle:
        matrix = cv2.getRotationMatrix2D(
            (350, 450), -angle, 1.0
        )  # +angle = clockwise tilt
        page = cv2.warpAffine(page, matrix, (700, 900), borderValue=255)
    return page


@pytest.mark.parametrize("tilt", [-8.0, -2.0, 1.0, 5.0, 12.0])
def test_estimate_skew_recovers_known_tilt(tilt: float) -> None:
    estimated = OCRPreprocessor.estimate_skew(make_text_page(tilt))
    assert estimated == pytest.approx(tilt, abs=0.7)


def test_deskew_straightens_the_page() -> None:
    tilted = make_text_page(6.0)
    straightened = OCRPreprocessor.deskew(tilted)
    assert abs(OCRPreprocessor.estimate_skew(straightened)) < 0.7


def test_deskew_leaves_straight_page_untouched() -> None:
    page = make_text_page(0.0)
    assert OCRPreprocessor.deskew(page) is page


def test_deskew_ignores_tilt_beyond_45_degrees() -> None:
    sideways = np.rot90(make_text_page(0.0))
    assert abs(OCRPreprocessor.estimate_skew(np.ascontiguousarray(sideways))) <= 45.0


def test_blank_page_has_no_skew() -> None:
    assert OCRPreprocessor.estimate_skew(np.full((300, 300), 255, np.uint8)) == 0.0


def test_remove_shadows_flattens_gradient_but_keeps_text() -> None:
    page = make_text_page().astype(np.float32)
    gradient = np.linspace(0.45, 1.0, page.shape[1], dtype=np.float32)
    shadowed = (page * gradient).astype(np.uint8)
    cleaned = OCRPreprocessor.remove_shadows(shadowed)
    dark_side, bright_side = cleaned[:, :20].mean(), cleaned[:, -20:].mean()
    assert abs(float(bright_side) - float(dark_side)) < 10
    assert cleaned.min() < 80  # strokes survive


def test_process_returns_gray_of_same_size_for_rgb_input() -> None:
    rgb = cv2.cvtColor(make_text_page(), cv2.COLOR_GRAY2RGB)
    out = OCRPreprocessor().process(rgb)
    assert out.shape == rgb.shape[:2]
    assert out.dtype == np.uint8


def test_settings_disable_every_stage() -> None:
    off = PreprocessSettings(False, False, False, False)
    rgb = cv2.cvtColor(make_text_page(5.0), cv2.COLOR_GRAY2RGB)
    out = OCRPreprocessor(off).process(rgb)
    assert np.array_equal(out, make_text_page(5.0))


def test_shadow_removal_is_skipped_for_non_photos() -> None:
    only_shadows = PreprocessSettings(True, False, False, False)
    gray = make_text_page()
    out = OCRPreprocessor(only_shadows).process(gray, is_camera_photo=False)
    assert np.array_equal(out, gray)


def test_full_pipeline_on_a4_300dpi_is_under_800_ms() -> None:
    a4 = np.full((3508, 2480, 3), 255, np.uint8)
    cv2.putText(
        a4, "Hola mundo lectura facil", (200, 600), cv2.FONT_HERSHEY_SIMPLEX, 4, 0, 8
    )
    everything = PreprocessSettings(True, True, True, True)
    started = time.perf_counter()
    OCRPreprocessor(everything).process(a4)
    assert (time.perf_counter() - started) * 1000 <= 800
