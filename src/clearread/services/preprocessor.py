"""Image preprocessing pipeline for OCR (OpenCV, vectorised primitives only)."""

from dataclasses import dataclass

import cv2
import numpy as np

MAX_DESKEW_ANGLE = 45.0
MIN_DESKEW_ANGLE = 0.5
_ANALYSIS_SIDE = 1000
_MIN_LINE_ASPECT = 3.0
_MIN_LINE_AREA = 40.0


@dataclass(frozen=True)
class PreprocessSettings:
    """Which stages run.

    Day 3 calibration (§4.2): only deskew showed a measured benefit, so the
    others are off until real photos prove otherwise.
    """

    remove_shadows: bool = False
    denoise: bool = False
    deskew: bool = True
    enhance_contrast: bool = False


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def _shrink(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    scale = min(1.0, max_side / max(image.shape[:2]))
    if scale == 1.0:
        return image, 1.0
    return cv2.resize(
        image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
    ), scale


class OCRPreprocessor:
    """Prepares raw images for OCR. Every stage is a method so it can be timed alone."""

    def __init__(self, settings: PreprocessSettings | None = None) -> None:
        self._settings = settings or PreprocessSettings()

    def process(
        self, image_rgb: np.ndarray, is_camera_photo: bool = True
    ) -> np.ndarray:
        """Return a grayscale image; shadow removal only runs for camera photos."""
        settings = self._settings
        gray = _to_gray(image_rgb)
        if settings.remove_shadows and is_camera_photo:
            gray = self.remove_shadows(gray)
        if settings.denoise:
            gray = self.denoise(gray)
        if settings.deskew:
            gray = self.deskew(gray)
        if settings.enhance_contrast:
            gray = self.enhance_contrast(gray)
        return gray

    @staticmethod
    def remove_shadows(gray: np.ndarray) -> np.ndarray:
        """Divide by a morphological background estimate (PRE-F01).

        The estimate runs on a shrunken copy: shadows are low-frequency, so the
        result is the same and the cost is a fraction of full resolution.
        """
        small, _ = _shrink(gray, _ANALYSIS_SIDE)
        side = max(9, (min(small.shape[:2]) // 25) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (side, side))
        background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, kernel)
        background = cv2.medianBlur(background, side)
        background = cv2.resize(
            background, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR
        )
        return cv2.divide(gray, np.maximum(background, 1), scale=255)

    @staticmethod
    def denoise(gray: np.ndarray) -> np.ndarray:
        return cv2.medianBlur(gray, 3)

    @staticmethod
    def enhance_contrast(gray: np.ndarray) -> np.ndarray:
        return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

    @staticmethod
    def estimate_skew(gray: np.ndarray) -> float:
        """Median angle (degrees) of the text lines; positive = clockwise tilt."""
        small, _ = _shrink(gray, _ANALYSIS_SIDE)
        binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[
            1
        ]
        width = max(5, int(small.shape[1] * 0.02))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (width, 1))
        lines = cv2.dilate(binary, kernel)
        contours, _ = cv2.findContours(
            lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        angles = [
            angle for contour in contours if (angle := _line_angle(contour)) is not None
        ]
        return float(np.median(angles)) if angles else 0.0

    @classmethod
    def deskew(cls, gray: np.ndarray) -> np.ndarray:
        """Straighten tilted text within ±45° when the tilt is at least 0.5° (PRE-F02)."""
        angle = cls.estimate_skew(gray)
        if abs(angle) < MIN_DESKEW_ANGLE:
            return gray
        height, width = gray.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        return cv2.warpAffine(
            gray,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=255,
        )


def _line_angle(contour: np.ndarray) -> float | None:
    """Angle of the long side of a contour's min-area rectangle, or None if not line-like."""
    if cv2.contourArea(contour) < _MIN_LINE_AREA:
        return None
    (_, _), (width, height), angle = cv2.minAreaRect(contour)
    if (
        min(width, height) == 0
        or max(width, height) / min(width, height) < _MIN_LINE_ASPECT
    ):
        return None
    if width < height:
        angle += 90.0
    angle = (angle + 90.0) % 180.0 - 90.0  # long-side direction in [-90, 90)
    return angle if abs(angle) <= MAX_DESKEW_ANGLE else None
