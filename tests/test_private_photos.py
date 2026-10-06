"""Smoke test on real photos; skipped when tests/samples/private/ has no photo + .txt pairs.

Never prints recognised or expected text (CLAUDE.md §n).
"""

import pytest
from calibrate_ocr import PRIVATE_DIR, character_error_rate, load_private_cases

from clearread.services.ocr_engine import ClearReadOCR
from clearread.services.preprocessor import OCRPreprocessor

MAX_CER = 0.5


def test_private_photos_are_readable_end_to_end() -> None:
    cases = load_private_cases()
    if not cases:
        pytest.skip(f"no photo + .txt pairs in {PRIVATE_DIR}")
    engine, preprocessor = ClearReadOCR(), OCRPreprocessor()
    failures = []
    for case in cases:
        text = engine.process_image(preprocessor.process(case.image)).raw_text
        cer = character_error_rate(case.expected, text)
        if cer > MAX_CER:
            failures.append(f"{case.name}: CER {cer:.0%}")
    assert not failures, "; ".join(failures)
