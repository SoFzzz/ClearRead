"""Day 3 preparation spike: Spanish accuracy of Latin recognition models.

Compares the default ch_PP-OCRv4 recognizer against the Latin ONNX models in
resources/models on tests/samples/sample_page_scanned.pdf, at 300 and 200 DPI.
Detection and angle classification keep RapidOCR's bundled models.

Usage: python tests/spike_ocr_latin.py
"""

import difflib
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR
from samples.make_samples import EXPECTED_LINES, SAMPLES_DIR

MODELS_DIR = Path(__file__).parents[1] / "resources" / "models"
CANDIDATES = {
    "ch_PP-OCRv4 (default)": None,
    "latin_PP-OCRv5_mobile": MODELS_DIR / "latin_PP-OCRv5_rec_mobile.onnx",
}
DPIS = (300, 200)
TIMED_RUNS = 3
SPECIAL_CHARS = set("áéíóúüñÑ¿¡")
EXPECTED_SPECIALS = sum(ch in SPECIAL_CHARS for line in EXPECTED_LINES for ch in line)


def render_scanned_page(dpi: int) -> np.ndarray:
    doc = pdfium.PdfDocument(str(SAMPLES_DIR / "sample_page_scanned.pdf"))
    try:
        return np.array(doc[0].render(scale=dpi / 72).to_pil().convert("RGB"))
    finally:
        doc.close()


def specials_in_place(expected: str, obtained: str) -> int:
    matcher = difflib.SequenceMatcher(None, expected, obtained, autojunk=False)
    return sum(
        ch in SPECIAL_CHARS
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes()
        if tag == "equal"
        for ch in expected[i1:i2]
    )


def evaluate(name: str, rec_model: Path | None, dpi: int) -> None:
    engine = RapidOCR(rec_model_path=str(rec_model)) if rec_model else RapidOCR()
    image = render_scanned_page(dpi)
    engine(image)  # warm-up: first inference includes one-off graph setup
    timings_ms = []
    for _ in range(TIMED_RUNS):
        t_start = time.perf_counter()
        result, _ = engine(image)
        timings_ms.append((time.perf_counter() - t_start) * 1000)
    obtained = [text for _box, text, _score in result or []]
    hits = sum(specials_in_place(e, o) for e, o in zip(EXPECTED_LINES, obtained))
    print(
        f"\n== {name} @ {dpi} DPI | specials {hits}/{EXPECTED_SPECIALS} "
        f"({hits / EXPECTED_SPECIALS:.0%}) | inference median "
        f"{statistics.median(timings_ms):.0f} ms (min {min(timings_ms):.0f}, "
        f"max {max(timings_ms):.0f}, {TIMED_RUNS} warm runs, perf_counter)"
    )
    if len(obtained) != len(EXPECTED_LINES):
        print(
            f"   WARNING: {len(obtained)} lines detected, {len(EXPECTED_LINES)} expected"
        )
    for expected, got in zip(EXPECTED_LINES, obtained):
        mark = "=" if expected == got else "≠"
        print(f"   {mark} esperado: {expected}\n     obtenido: {got}")


def main() -> None:
    for dpi in DPIS:
        for name, rec_model in CANDIDATES.items():
            evaluate(name, rec_model, dpi)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
