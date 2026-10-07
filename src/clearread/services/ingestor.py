"""Document ingestion service using pypdfium2 and Pillow."""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image, ImageOps


class DocumentType(Enum):
    PDF = "pdf"
    IMAGE = "image"


class PasswordProtectedError(PermissionError):
    """The PDF needs a password to be opened (ING-F04)."""


class UnsupportedFormatError(ValueError):
    """The file extension is neither a supported PDF nor image format."""


@dataclass(frozen=True)
class PageResult:
    page_number: int
    total_pages: int
    image: np.ndarray  # RGB (H, W, 3)
    digital_text: str | None  # native text layer when it is long enough, else None
    source_type: DocumentType


class DocumentIngestor:
    SUPPORTED_IMAGE_EXT = frozenset(
        {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".tiff", ".tif"}
    )
    SUPPORTED_PDF_EXT = frozenset({".pdf"})
    DEFAULT_DPI = 300
    DIGITAL_TEXT_THRESHOLD = 50

    def __init__(self, dpi: int = DEFAULT_DPI) -> None:
        self._dpi = dpi

    def get_page_count(self, file_path: str | Path) -> int:
        path = Path(file_path)
        kind = self._classify(path)
        if kind is DocumentType.IMAGE:
            return 1
        document = self._open_pdf(path)
        try:
            return len(document)
        finally:
            document.close()

    def load(self, file_path: str | Path) -> Iterator[PageResult]:
        """Validate the file now and return a page-by-page iterator.

        Validation is eager so a missing or unsupported file fails at the call,
        not on the first ``next()``.
        """
        path = Path(file_path)
        if self._classify(path) is DocumentType.IMAGE:
            return iter((self._load_single_image(path),))
        return self._load_pdf_streaming(path)

    def _classify(self, path: Path) -> DocumentType:
        if not path.is_file():
            raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if suffix in self.SUPPORTED_PDF_EXT:
            return DocumentType.PDF
        if suffix in self.SUPPORTED_IMAGE_EXT:
            return DocumentType.IMAGE
        raise UnsupportedFormatError(suffix)

    @staticmethod
    def _open_pdf(path: Path) -> pdfium.PdfDocument:
        try:
            return pdfium.PdfDocument(str(path))
        except pdfium.PdfiumError as err:
            if err.err_code == pdfium_raw.FPDF_ERR_PASSWORD:
                raise PasswordProtectedError(path) from err
            raise

    def _load_pdf_streaming(self, path: Path) -> Iterator[PageResult]:
        document = self._open_pdf(path)
        try:
            total_pages = len(document)
            scale = self._dpi / 72.0
            for index in range(total_pages):
                yield self._render_page(document, index, total_pages, scale)
        finally:
            document.close()

    def _render_page(
        self, document: pdfium.PdfDocument, index: int, total_pages: int, scale: float
    ) -> PageResult:
        page = document[index]
        try:
            text = self._extract_text(page)
            image = np.array(page.render(scale=scale).to_pil().convert("RGB"))
        finally:
            page.close()
        return PageResult(
            page_number=index + 1,
            total_pages=total_pages,
            image=image,
            digital_text=text if len(text) >= self.DIGITAL_TEXT_THRESHOLD else None,
            source_type=DocumentType.PDF,
        )

    @staticmethod
    def _extract_text(page: pdfium.PdfPage) -> str:
        textpage = page.get_textpage()
        try:
            return textpage.get_text_range().replace("\r\n", "\n").strip()
        finally:
            textpage.close()

    @staticmethod
    def _load_single_image(path: Path) -> PageResult:
        with Image.open(path) as opened:
            upright = ImageOps.exif_transpose(opened)
            if upright.mode in ("RGBA", "LA", "P"):
                rgba = upright.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = upright.convert("RGB")
            image = np.array(rgb)
        return PageResult(
            page_number=1,
            total_pages=1,
            image=image,
            digital_text=None,
            source_type=DocumentType.IMAGE,
        )
