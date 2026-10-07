"""Day 3 calibration: OCR accuracy and timing with and without preprocessing.

Not a pytest test. Run from the repo root (modes are exclusive):

    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --pdf-render   # PDF pages rendered, digital text as reference
    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --photos       # phone photos named <Ficha>_p<N>_<condition>.jpg
    .\\.venv\\Scripts\\python tests\\calibrate_ocr.py --synthetic    # degraded copies of the sample page

Options: --ablation (each preprocessing stage on/off), --sweep (OCR parameter
grid), --sweep-preprocessed, --limit-pages N (first N pages of each PDF).

Reference text. PDF pages and photos use the digital text layer of the page
(photos name their page: "Poema_p3_sombra.jpg" -> page 3 of the PDF whose name
contains "Poema"). Legacy pairs "<photo>.jpg" + "<photo>.txt" also work.

Privacy (CLAUDE.md §n): prints file names, page numbers and metrics only,
never recognised or reference text.

Metrics. CER = Levenshtein distance / reference length after collapsing
whitespace. Word F1 = bag-of-words F1 (case-insensitive): unlike CER it ignores
reading order, which differs from the digital text on cards with columns or
boxes. "Specials" counts ñ, tildes, ü, ¿ and ¡ of the reference that the OCR
output also contains (per-character multiset, order independent). Timings use
time.perf_counter().
"""

import argparse
import itertools
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

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
PHOTO_NAME = re.compile(r"^(?P<ficha>.+)_p(?P<page>\d+)_(?P<condition>.+)$")
WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Case:
    name: str
    image: np.ndarray
    expected: str
    is_camera_photo: bool


CaseSource = Callable[[], Iterator[Case]]


@dataclass(frozen=True)
class Measurement:
    cer: float
    f1: float
    specials: int
    specials_total: int
    pre_ms: float
    ocr_ms: float


def normalise(text: str) -> str:
    return " ".join(text.split())


def levenshtein(a: str, b: str) -> int:
    """Edit distance with the Myers/Hyyrö bit-vector algorithm (fast for long pages)."""
    if not a or not b:
        return len(a) or len(b)
    mask = (1 << len(a)) - 1
    high = 1 << (len(a) - 1)
    match_bits: dict[str, int] = {}
    for position, char in enumerate(a):
        match_bits[char] = match_bits.get(char, 0) | (1 << position)
    plus, minus, score = mask, 0, len(a)
    for char in b:
        eq = match_bits.get(char, 0)
        xv = eq | minus
        xh = (((eq & plus) + plus) ^ plus) | eq
        ph = minus | (~(xh | plus) & mask)
        mh = plus & xh
        if ph & high:
            score += 1
        elif mh & high:
            score -= 1
        ph = ((ph << 1) | 1) & mask
        mh = (mh << 1) & mask
        plus = mh | (~(xv | ph) & mask)
        minus = ph & xv
    return score


def character_error_rate(expected: str, obtained: str) -> float:
    reference = normalise(expected)
    return levenshtein(reference, normalise(obtained)) / max(len(reference), 1)


def word_f1(expected: str, obtained: str) -> float:
    reference = Counter(WORD.findall(expected.lower()))
    candidate = Counter(WORD.findall(obtained.lower()))
    overlap = sum((reference & candidate).values())
    if not overlap:
        return 0.0
    precision = overlap / sum(candidate.values())
    recall = overlap / sum(reference.values())
    return 2 * precision * recall / (precision + recall)


def special_hits(expected: str, obtained: str) -> tuple[int, int]:
    reference = Counter(ch for ch in expected if ch in SPECIAL_CHARS)
    candidate = Counter(ch for ch in obtained if ch in SPECIAL_CHARS)
    return sum((reference & candidate).values()), sum(reference.values())


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
    settings: PreprocessSettings | None, case: Case
) -> tuple[np.ndarray, dict[str, float]]:
    """Same order as OCRPreprocessor.process, timing each stage separately."""
    stage_ms: dict[str, float] = {}
    if settings is None:
        return case.image, stage_ms
    pre = OCRPreprocessor
    gray = timed(lambda: cv2.cvtColor(case.image, cv2.COLOR_RGB2GRAY), stage_ms, "gray")
    if settings.remove_shadows and case.is_camera_photo:
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
    prepared, stage_ms = run_stages(settings, case)
    result = engine.process_image(prepared)
    hits, total = special_hits(case.expected, result.raw_text)
    return (
        Measurement(
            cer=character_error_rate(case.expected, result.raw_text),
            f1=word_f1(case.expected, result.raw_text),
            specials=hits,
            specials_total=total,
            pre_ms=sum(stage_ms.values()),
            ocr_ms=result.processing_time_ms,
        ),
        stage_ms,
    )


def private_pdfs() -> list[Path]:
    if not PRIVATE_DIR.is_dir():
        return []
    return sorted(PRIVATE_DIR.glob("*.pdf"))


def pdf_page_cases(limit_pages: int | None) -> Iterator[Case]:
    ingestor = DocumentIngestor()
    for pdf in private_pdfs():
        pages = ingestor.load(pdf)
        for page in itertools.islice(pages, limit_pages):
            if page.digital_text is None:
                continue
            yield Case(
                f"{pdf.stem} p{page.page_number}", page.image, page.digital_text, False
            )


def find_pdf_for(ficha: str) -> Path | None:
    wanted = ficha.replace("_", " ").lower()
    return next((pdf for pdf in private_pdfs() if wanted in pdf.stem.lower()), None)


def pdf_page(pdf: Path, number: int) -> str | None:
    for page in DocumentIngestor().load(pdf):
        if page.page_number == number:
            return page.digital_text
    return None


def photo_cases() -> Iterator[Case]:
    if not PRIVATE_DIR.is_dir():
        return
    ingestor = DocumentIngestor()
    for photo in sorted(PRIVATE_DIR.iterdir()):
        if photo.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        expected = reference_for_photo(photo)
        if expected is not None:
            image = next(iter(ingestor.load(photo))).image
            yield Case(photo.name, image, expected, True)


def reference_for_photo(photo: Path) -> str | None:
    legacy = photo.with_suffix(".txt")
    if legacy.is_file():
        return legacy.read_text(encoding="utf-8")
    named = PHOTO_NAME.match(photo.stem)
    pdf = find_pdf_for(named["ficha"]) if named else None
    return pdf_page(pdf, int(named["page"])) if named and pdf else None


def load_private_cases() -> list[Case]:
    """Photos with a known reference (used by tests/test_private_photos.py)."""
    return list(photo_cases())


def synthetic_cases() -> Iterator[Case]:
    """Degraded copies of the scanned sample page (not real photos)."""
    page = next(
        iter(DocumentIngestor().load(SAMPLES_DIR / "sample_page_scanned.pdf"))
    ).image
    height, width = page.shape[:2]
    rng = np.random.default_rng(0)
    gradient = np.linspace(0.4, 1.0, width, dtype=np.float32)[None, :, None]

    def rotated(source: np.ndarray, degrees: float) -> np.ndarray:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -degrees, 1.0)
        return cv2.warpAffine(
            source, matrix, (width, height), borderValue=(255, 255, 255)
        )

    shadowed = (page * gradient).astype(np.uint8)
    noisy = np.clip(page + rng.normal(0, 25, page.shape), 0, 255).astype(np.uint8)
    combined = rotated(shadowed, 4.0)
    combined = np.clip(combined + rng.normal(0, 15, combined.shape), 0, 255).astype(
        np.uint8
    )
    variants = {
        "synthetic_clean": page,
        "synthetic_rot3": rotated(page, 3.0),
        "synthetic_rot10": rotated(page, 10.0),
        "synthetic_shadow": shadowed,
        "synthetic_noise": noisy,
        "synthetic_rot4_shadow_noise": combined,
    }
    for name, image in variants.items():
        yield Case(name, image, EXPECTED_TEXT, True)


def preprocess_configs(
    ablation: bool, shadows: bool
) -> dict[str, PreprocessSettings | None]:
    configs: dict[str, PreprocessSettings | None] = {
        "original": None,
        "preprocessed": PreprocessSettings(),
    }
    if ablation:
        stages = [s for s in STAGES if shadows or s != "remove_shadows"]
        none = PreprocessSettings(False, False, False, False)
        for stage in stages:
            configs[f"without_{stage}"] = replace(
                PreprocessSettings(), **{stage: False}
            )
        for stage in stages:
            configs[f"only_{stage}"] = replace(none, **{stage: True})
        configs["all_stages"] = PreprocessSettings(shadows, True, True, True)
    return configs


def summarise(items: list[Measurement]) -> str:
    specials = sum(m.specials for m in items)
    total = sum(m.specials_total for m in items)
    return (
        f"CER {statistics.fmean(m.cer for m in items):6.1%}  "
        f"F1 {statistics.fmean(m.f1 for m in items):6.1%}  "
        f"especiales {specials:4}/{total:<4} "
        f"pre {statistics.fmean(m.pre_ms for m in items):6.0f} ms  "
        f"ocr {statistics.fmean(m.ocr_ms for m in items):6.0f} ms"
    )


def run_comparison(source: CaseSource, engine: ClearReadOCR, ablation: bool) -> int:
    rows: dict[str, list[Measurement]] = {}
    default_stages: dict[str, list[float]] = {}
    count = 0
    for case in source():
        count += 1
        for name, settings in preprocess_configs(
            ablation, case.is_camera_photo
        ).items():
            measurement, stage_ms = measure(engine, case, settings)
            rows.setdefault(name, []).append(measurement)
            print(f"{case.name:48} {name:26} {summarise([measurement])}", flush=True)
            if name == "preprocessed":
                for stage, ms in stage_ms.items():
                    default_stages.setdefault(stage, []).append(ms)
    print(f"\n== MEDIA sobre {count} imágenes ==")
    for name, items in rows.items():
        print(f"{'media':48} {name:26} {summarise(items)}")
    print("\n== Tiempo medio por etapa (preprocesado por defecto) ==")
    for stage, values in default_stages.items():
        print(f"{stage:20} {statistics.fmean(values):7.0f} ms (máx {max(values):.0f})")
    return count


def run_sweep(source: CaseSource, settings: PreprocessSettings | None) -> None:
    label = "preprocessed" if settings else "original"
    print(f"\n== Barrido de parámetros OCR sobre imagen '{label}' ==")
    for box_thresh, unclip, confidence in itertools.product(
        SWEEP_BOX_THRESH, SWEEP_UNCLIP, SWEEP_CONFIDENCE
    ):
        engine = ClearReadOCR(OCRSettings(confidence, box_thresh, unclip))
        items = [measure(engine, case, settings)[0] for case in source()]
        print(
            f"box_thresh {box_thresh:.1f}  unclip {unclip:.1f}  confianza {confidence:.2f}  "
            f"{summarise(items)}",
            flush=True,
        )


def build_source(args: argparse.Namespace) -> tuple[CaseSource, str]:
    if args.synthetic:
        return synthetic_cases, "sintéticas"
    if args.pdf_render:
        return lambda: pdf_page_cases(args.limit_pages), "páginas de PDF renderizadas"
    return photo_cases, "fotos"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--pdf-render", action="store_true", help="render PDF pages")
    modes.add_argument("--photos", action="store_true", help="phone photos (default)")
    modes.add_argument("--synthetic", action="store_true", help="degraded sample pages")
    parser.add_argument(
        "--ablation", action="store_true", help="each stage alone / removed"
    )
    parser.add_argument("--sweep", action="store_true", help="grid over OCR parameters")
    parser.add_argument("--sweep-preprocessed", action="store_true")
    parser.add_argument("--limit-pages", type=int, default=None, help="pages per PDF")
    args = parser.parse_args()

    source, label = build_source(args)
    first = next(source(), None)
    if first is None:
        print(
            f"Sin {label} que calibrar en {PRIVATE_DIR}. Para fotos: <Ficha>_p<N>_<condición>.jpg "
            "(junto al PDF de la ficha) o <foto>.jpg + <foto>.txt; para --pdf-render, los PDF."
        )
        return 0

    engine = ClearReadOCR()
    engine.process_image(
        first.image
    )  # warm-up: the first inference includes model setup
    print(f"Modo: {label}. 1 pasada tras calentar.\n", flush=True)
    run_comparison(source, engine, args.ablation)
    if args.sweep:
        run_sweep(source, PreprocessSettings() if args.sweep_preprocessed else None)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
