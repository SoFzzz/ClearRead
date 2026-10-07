"""OCR and layout analysis engine using RapidOCR (ONNX Runtime, offline)."""

import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from clearread.core.paths import get_resource_path

REC_MODEL_RELATIVE = "resources/models/latin_PP-OCRv5_rec_mobile.onnx"
_LINE_HEIGHT_MIN_PX = 10.0
_LINE_MERGE_RATIO = 0.5
_PARAGRAPH_GAP_RATIO = 1.0
_HAS_ALNUM = re.compile(r"\w")


@dataclass(frozen=True)
class OCRSettings:
    """Detector and filter parameters. Defaults come from the Day 3 calibration (§4.3)."""

    min_confidence: float = 0.45
    box_thresh: float = 0.5
    unclip_ratio: float = 1.6


@dataclass(frozen=True)
class OCRResult:
    page_number: int
    raw_text: str = ""
    processing_time_ms: float = 0.0


@dataclass(frozen=True)
class TextBox:
    """Axis-aligned bounds of one recognised fragment, in pixels."""

    text: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def height(self) -> float:
        return max(self.bottom - self.top, _LINE_HEIGHT_MIN_PX)

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


def merge_lines(lines: list[str]) -> str:
    """Join consecutive lines, removing end-of-line hyphenation (OCR-F02).

    Only a hyphen that ends a line is touched: "inter-" + "nacional" becomes
    "internacional", while "hispano-americano" inside a line is left alone. When
    the next line starts in uppercase the hyphen is kept ("Madrid-" + "Barcelona").
    """
    merged = ""
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not merged:
            merged = text
        elif merged[-1] == "-" and len(merged) > 1 and merged[-2].isalpha():
            keeps_hyphen = not text[0].islower()
            merged = merged + text if keeps_hyphen else merged[:-1] + text
        else:
            merged = f"{merged} {text}"
    return merged


def build_paragraphs(boxes: list[TextBox]) -> list[str]:
    """Order boxes into reading order and group them into paragraphs (OCR-F03)."""
    if not boxes:
        return []
    median_height = statistics.median(box.height for box in boxes)
    paragraphs: list[list[str]] = [[]]
    previous_bottom: float | None = None
    for line in _group_into_lines(boxes, median_height):
        top = min(box.top for box in line)
        gap = None if previous_bottom is None else top - previous_bottom
        if gap is not None and gap > median_height * _PARAGRAPH_GAP_RATIO:
            paragraphs.append([])
        paragraphs[-1].append(" ".join(box.text for box in line))
        previous_bottom = max(box.bottom for box in line)
    return [merge_lines(lines) for lines in paragraphs]


def _group_into_lines(
    boxes: list[TextBox], median_height: float
) -> list[list[TextBox]]:
    tolerance = median_height * _LINE_MERGE_RATIO
    lines: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda b: (b.center_y, b.left)):
        for line in lines:
            line_center = sum(item.center_y for item in line) / len(line)
            if abs(box.center_y - line_center) <= tolerance:
                line.append(box)
                break
        else:
            lines.append([box])
    for line in lines:
        line.sort(key=lambda b: b.left)
    lines.sort(key=lambda line: sum(item.center_y for item in line) / len(line))
    return lines


class ClearReadOCR:
    """Offline OCR: ch_PP-OCRv4 detection, latin_PP-OCRv5 recognition, angle classifier.

    Detection and classifier models ship inside the ``rapidocr_onnxruntime``
    package; the Latin recognizer (accented vowels, the tilde-n and Spanish punctuation) lives in
    ``resources/models``. The engine is built once and reused for every page.
    """

    def __init__(
        self,
        settings: OCRSettings | None = None,
        rec_model_path: Path | None = None,
    ) -> None:
        self._settings = settings or OCRSettings()
        rec_path = rec_model_path or get_resource_path(REC_MODEL_RELATIVE)
        if not rec_path.is_file():
            raise FileNotFoundError(rec_path)
        self._engine = RapidOCR(rec_model_path=str(rec_path))

    def process_image(self, image: np.ndarray, page_number: int = 1) -> OCRResult:
        """Recognise an RGB (H, W, 3) or grayscale (H, W) image."""
        started = time.perf_counter()
        paragraphs = build_paragraphs(self._filter(self._recognise(image)))
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return OCRResult(page_number, "\n\n".join(paragraphs), elapsed_ms)

    def _recognise(self, image: np.ndarray) -> list[tuple[TextBox, float]]:
        settings = self._settings
        result, _ = self._engine(
            _to_bgr(image),
            box_thresh=settings.box_thresh,
            unclip_ratio=settings.unclip_ratio,
            text_score=settings.min_confidence,
        )
        return [
            (_to_text_box(points, text), float(score))
            for points, text, score in result or []
        ]

    def _filter(self, detections: list[tuple[TextBox, float]]) -> list[TextBox]:
        minimum = self._settings.min_confidence
        return [
            box
            for box, score in detections
            if score >= minimum and _HAS_ALNUM.search(box.text)
        ]


def _to_bgr(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)


def _to_text_box(points: list[list[float]], text: str) -> TextBox:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return TextBox(text.strip(), min(xs), min(ys), max(xs), max(ys))
