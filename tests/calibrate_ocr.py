"""Day 3 calibration: OCR accuracy and timing with and without preprocessing.

Not a pytest test. Run from the repo root:

    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py              # real photos
    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --ablation   # + one stage on/off at a time
    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --sweep      # + OCR parameter grid
    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --synthetic  # degraded copies of the sample page

Real photos live in tests/samples/private/ (git-ignored), each with a
<name>.txt holding the expected text. Privacy (CLAUDE.md §n): this script prints
file names and metrics only, never recognised or expected text.

CER = Levenshtein distance / expected length, after collapsing whitespace.
"Specials" counts ñ, tildes, ü, ¿ and ¡ of the expected text that appear in
place in the OCR output. Timings use time.perf_counter().
"""

import argparse
import difflib
import itertools
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

import cv2
import numpy as np
from samples.make_samples import EXPECTED_TEXT, SAMPLES_DIR

from clearread.services.ingestor import DocumentIngestor
from clearread.services.ocr_engine import ClearReadOCR, OCRSettings
from clearread.services.preprocessor import OCRPreprocessor, PreprocessSettings

PRIVATE_DIR = SAMPLES_DIR / "private"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPECIAL_CHARS = set("áéíóúüñÑ¿¡")
STAGES = ("remove_shadows", "denoise", "deskew", "enhance_contrast")
SWEEP_BOX_THRESH = (0.4, 0.5, 0.6)
SWEEP_UNCLIP = (1.6, 2.0)
SWEEP_CONFIDENCE = (0.3, 0.45, 0.6)


@dataclass(frozen=True)
class Case:
    name: str
    image: np.ndarray
    expected: str


@dataclass(frozen=True)
class Measurement:
    cer: float
    specials: int
    specials_total: int
    pre_ms: float
    ocr_ms: float


def normalise(text: str) -> str:
    return " ".join(text.split())


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current
    return previous[-1]


def character_error_rate(expected: str, obtained: str) -> float:
    reference = normalise(expected)
    return levenshtein(reference, normalise(obtained)) / max(len(reference), 1)


def special_hits(expected: str, obtained: str) -> tuple[int, int]:
    reference, candidate = normalise(expected), normalise(obtained)
    matcher = difflib.SequenceMatcher(None, reference, candidate, autojunk=False)
    hits = sum(
        ch in SPECIAL_CHARS
        for tag, i1, i2, _j1, _j2 in matcher.get_opcodes()
        if tag == "equal"
        for ch in reference[i1:i2]
    )
    return hits, sum(ch in SPECIAL_CHARS for ch in reference)


def timed(
    action: Callable[[], np.ndarray], stage_ms: dict[str, float], stage: str
) -> np.ndarray:
    started = time.perf_counter()
    result = action()
    stage_ms[stage] = (
        stage_ms.get(stage, 0.0) + (time.perf_counter() - started) * 1000.0
    )
    return result


def run_stages(
    settings: PreprocessSettings | None, image: np.ndarray
) -> tuple[np.ndarray, dict[str, float]]:
    """Same order as OCRPreprocessor.process, timing each stage separately."""
    stage_ms: dict[str, float] = {}
    if settings is None:
        return image, stage_ms
    pre = OCRPreprocessor
    gray = timed(lambda: cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), stage_ms, "gray")
    if settings.remove_shadows:
        gray = timed(lambda: pre.remove_shadows(gray), stage_ms, "remove_shadows")
    if settings.denoise:
        gray = timed(lambda: pre.denoise(gray), stage_ms, "denoise")
    if settings.deskew:
        gray = timed(lambda: pre.deskew(gray), stage_ms, "deskew")
    if settings.enhance_contrast:
        gray = timed(lambda: pre.enhance_contrast(gray), stage_ms, "enhance_contrast")
    return gray, stage_ms


def measure(
    engine: ClearReadOCR, case: Case, settings: PreprocessSettings | None
) -> tuple[Measurement, dict[str, float]]:
    prepared, stage_ms = run_stages(settings, case.image)
    result = engine.process_image(prepared)
    hits, total = special_hits(case.expected, result.raw_text)
    return (
        Measurement(
            cer=character_error_rate(case.expected, result.raw_text),
            specials=hits,
            specials_total=total,
            pre_ms=sum(stage_ms.values()),
            ocr_ms=result.processing_time_ms,
        ),
        stage_ms,
    )


def load_private_cases() -> list[Case]:
    if not PRIVATE_DIR.is_dir():
        return []
    ingestor = DocumentIngestor()
    cases = []
    for photo in sorted(PRIVATE_DIR.iterdir()):
        expected_path = photo.with_suffix(".txt")
        if photo.suffix.lower() not in IMAGE_SUFFIXES or not expected_path.is_file():
            continue
        page = next(iter(ingestor.load(photo)))
        cases.append(
            Case(photo.name, page.image, expected_path.read_text(encoding="utf-8"))
        )
    return cases


def synthetic_cases() -> list[Case]:
    """Degraded copies of the scanned sample page (not real photos)."""
    page = next(
        iter(DocumentIngestor().load(SAMPLES_DIR / "sample_page_scanned.pdf"))
    ).image
    height, width = page.shape[:2]
    rng = np.random.default_rng(0)
    gradient = np.linspace(0.4, 1.0, width, dtype=np.float32)[None, :, None]

    def rotated(degrees: float) -> np.ndarray:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -degrees, 1.0)
        return cv2.warpAffine(
            page, matrix, (width, height), borderValue=(255, 255, 255)
        )

    shadowed = (page * gradient).astype(np.uint8)
    noisy = np.clip(page + rng.normal(0, 25, page.shape), 0, 255).astype(np.uint8)
    combined_matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -4.0, 1.0)
    combined = cv2.warpAffine(
        shadowed, combined_matrix, (width, height), borderValue=(255,) * 3
    )
    combined = np.clip(combined + rng.normal(0, 15, combined.shape), 0, 255).astype(
        np.uint8
    )
    variants = {
        "synthetic_clean": page,
        "synthetic_rot3": rotated(3.0),
        "synthetic_rot10": rotated(10.0),
        "synthetic_shadow": shadowed,
        "synthetic_noise": noisy,
        "synthetic_rot4_shadow_noise": combined,
    }
    return [Case(name, image, EXPECTED_TEXT) for name, image in variants.items()]


def preprocess_configs(ablation: bool) -> dict[str, PreprocessSettings | None]:
    configs: dict[str, PreprocessSettings | None] = {
        "original": None,
        "preprocessed": PreprocessSettings(),
    }
    if ablation:
        for stage in STAGES:
            configs[f"without_{stage}"] = replace(
                PreprocessSettings(), **{stage: False}
            )
        none = PreprocessSettings(False, False, False, False)
        for stage in STAGES:
            configs[f"only_{stage}"] = replace(none, **{stage: True})
    return configs


def print_row(case: str, config: str, m: Measurement) -> None:
    print(
        f"{case:34} {config:26} CER {m.cer:6.1%}  especiales {m.specials:3}/{m.specials_total:<3} "
        f"pre {m.pre_ms:6.0f} ms  ocr {m.ocr_ms:6.0f} ms"
    )


def print_means(rows: dict[str, list[Measurement]]) -> None:
    print("\n== MEDIA por configuración ==")
    for config, items in rows.items():
        specials = sum(m.specials for m in items)
        total = sum(m.specials_total for m in items)
        print(
            f"{'media':34} {config:26} CER {statistics.fmean(m.cer for m in items):6.1%}  "
            f"especiales {specials:3}/{total:<3} pre {statistics.fmean(m.pre_ms for m in items):6.0f} ms  "
            f"ocr {statistics.fmean(m.ocr_ms for m in items):6.0f} ms"
        )


def print_stage_times(stage_totals: dict[str, list[float]], count: int) -> None:
    print(
        f"\n== Tiempo medio por etapa (preprocesado por defecto, {count} imágenes) =="
    )
    for stage, values in stage_totals.items():
        print(f"{stage:20} {statistics.fmean(values):7.0f} ms (máx {max(values):.0f})")


def run_comparison(cases: list[Case], engine: ClearReadOCR, ablation: bool) -> None:
    configs = preprocess_configs(ablation)
    rows: dict[str, list[Measurement]] = {name: [] for name in configs}
    default_stages: dict[str, list[float]] = {}
    for case in cases:
        for name, settings in configs.items():
            measurement, stage_ms = measure(engine, case, settings)
            rows[name].append(measurement)
            print_row(case.name, name, measurement)
            if name == "preprocessed":
                for stage, ms in stage_ms.items():
                    default_stages.setdefault(stage, []).append(ms)
    print_means(rows)
    print_stage_times(default_stages, len(cases))


def run_sweep(cases: list[Case], settings: PreprocessSettings | None) -> None:
    label = "preprocessed" if settings else "original"
    print(f"\n== Barrido de parámetros OCR sobre imagen '{label}' ==")
    for box_thresh, unclip, confidence in itertools.product(
        SWEEP_BOX_THRESH, SWEEP_UNCLIP, SWEEP_CONFIDENCE
    ):
        engine = ClearReadOCR(OCRSettings(confidence, box_thresh, unclip))
        engine.process_image(cases[0].image)  # warm-up
        items = [measure(engine, case, settings)[0] for case in cases]
        specials = sum(m.specials for m in items)
        total = sum(m.specials_total for m in items)
        print(
            f"box_thresh {box_thresh:.1f}  unclip {unclip:.1f}  confianza {confidence:.2f}  "
            f"CER {statistics.fmean(m.cer for m in items):6.1%}  especiales {specials}/{total}  "
            f"ocr {statistics.fmean(m.ocr_ms for m in items):6.0f} ms"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ablation", action="store_true", help="try each stage alone / removed"
    )
    parser.add_argument("--sweep", action="store_true", help="grid over OCR parameters")
    parser.add_argument(
        "--synthetic", action="store_true", help="use degraded sample pages"
    )
    parser.add_argument(
        "--sweep-preprocessed",
        action="store_true",
        help="sweep on the preprocessed image",
    )
    args = parser.parse_args()

    cases = synthetic_cases() if args.synthetic else load_private_cases()
    if not cases:
        print(
            f"Sin fotos que calibrar: {PRIVATE_DIR} no existe o no tiene pares "
            "<foto>.jpg|png + <foto>.txt. Copia las fotos allí y vuelve a ejecutar "
            "(o usa --synthetic para ver el script con páginas sintéticas)."
        )
        return 0

    engine = ClearReadOCR()
    engine.process_image(
        cases[0].image
    )  # warm-up: the first inference includes model setup
    print(
        f"{len(cases)} imágenes ({'sintéticas' if args.synthetic else 'privadas'}); 1 pasada tras calentar.\n"
    )
    run_comparison(cases, engine, args.ablation)
    if args.sweep:
        run_sweep(cases, PreprocessSettings() if args.sweep_preprocessed else None)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
