from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pytest
from PIL import Image
from samples.make_samples import (
    EXPECTED_TEXT,
    PHOTO_BACKGROUND_RGB,
    PHOTO_MARKER_RGB,
    PHOTO_STORED_SIZE,
    SAMPLES_DIR,
)

from clearread.services.ingestor import (
    DocumentIngestor,
    DocumentType,
    PasswordProtectedError,
    UnsupportedFormatError,
)

LOW_DPI = 100


@pytest.fixture
def ingestor() -> DocumentIngestor:
    return DocumentIngestor(dpi=LOW_DPI)


def test_digital_pdf_bypasses_ocr_with_native_text(ingestor: DocumentIngestor) -> None:
    (page,) = list(ingestor.load(SAMPLES_DIR / "sample_page_digital.pdf"))
    assert page.digital_text == EXPECTED_TEXT
    assert page.source_type is DocumentType.PDF
    assert (page.page_number, page.total_pages) == (1, 1)
    assert page.image.ndim == 3 and page.image.shape[2] == 3


def test_scanned_pdf_has_no_digital_text(ingestor: DocumentIngestor) -> None:
    (page,) = list(ingestor.load(SAMPLES_DIR / "sample_page_scanned.pdf"))
    assert page.digital_text is None


def test_render_size_follows_dpi() -> None:
    path = SAMPLES_DIR / "sample_page_scanned.pdf"
    small = next(iter(DocumentIngestor(dpi=72).load(path))).image
    large = next(iter(DocumentIngestor(dpi=144).load(path))).image
    assert large.shape[0] == pytest.approx(small.shape[0] * 2, abs=2)


def test_short_text_layer_is_not_digital(
    ingestor: DocumentIngestor, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingestor, "DIGITAL_TEXT_THRESHOLD", len(EXPECTED_TEXT) + 1)
    (page,) = list(ingestor.load(SAMPLES_DIR / "sample_page_digital.pdf"))
    assert page.digital_text is None


def test_page_count(ingestor: DocumentIngestor) -> None:
    assert ingestor.get_page_count(SAMPLES_DIR / "sample_page_digital.pdf") == 1
    assert ingestor.get_page_count(SAMPLES_DIR / "sample_photo_exif6.jpg") == 1


def test_exif_orientation_6_rotates_to_portrait(ingestor: DocumentIngestor) -> None:
    (page,) = list(ingestor.load(SAMPLES_DIR / "sample_photo_exif6.jpg"))
    stored_w, stored_h = PHOTO_STORED_SIZE
    assert page.image.shape == (stored_w, stored_h, 3)
    assert page.source_type is DocumentType.IMAGE
    assert page.digital_text is None
    # A 90° clockwise turn moves the top-left marker to the top-right corner.
    assert np.abs(page.image[2, -3].astype(int) - PHOTO_MARKER_RGB).max() < 12
    assert np.abs(page.image[2, 2].astype(int) - PHOTO_BACKGROUND_RGB).max() < 12


def test_rgba_png_is_flattened_on_white(
    tmp_path: Path, ingestor: DocumentIngestor
) -> None:
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(path)
    (page,) = list(ingestor.load(path))
    assert page.image.shape == (4, 4, 3)
    assert (page.image == 255).all()


def test_password_pdf_raises_password_protected(ingestor: DocumentIngestor) -> None:
    path = SAMPLES_DIR / "sample_page_password.pdf"
    with pytest.raises(PasswordProtectedError):
        ingestor.get_page_count(path)
    with pytest.raises(PasswordProtectedError):
        list(ingestor.load(path))


def test_unsupported_format(tmp_path: Path, ingestor: DocumentIngestor) -> None:
    path = tmp_path / "notes.docx"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFormatError):
        ingestor.load(path)
    with pytest.raises(UnsupportedFormatError):
        ingestor.get_page_count(path)


def test_missing_file_fails_at_call_not_at_first_page(
    tmp_path: Path, ingestor: DocumentIngestor
) -> None:
    with pytest.raises(FileNotFoundError):
        ingestor.load(tmp_path / "missing.pdf")
    with pytest.raises(FileNotFoundError):
        ingestor.get_page_count(tmp_path / "missing.pdf")


def test_pdf_document_is_closed_when_generator_is_abandoned(
    ingestor: DocumentIngestor, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[bool] = []
    original_close = pdfium.PdfDocument.close

    def spy(self: pdfium.PdfDocument) -> None:
        closed.append(True)
        original_close(self)

    monkeypatch.setattr(pdfium.PdfDocument, "close", spy)
    pages = ingestor.load(SAMPLES_DIR / "sample_page_scanned.pdf")
    next(iter(pages))
    assert closed == []
    pages.close()  # type: ignore[attr-defined]
    assert closed == [True]


@pytest.mark.parametrize("suffix", [".jfif", ".jpe", ".JFIF"])
def test_jpeg_variants_are_loaded_like_jpg(
    tmp_path: Path, ingestor: DocumentIngestor, suffix: str
) -> None:
    path = tmp_path / f"photo{suffix}"
    path.write_bytes((SAMPLES_DIR / "sample_photo_exif6.jpg").read_bytes())
    (page,) = list(ingestor.load(path))
    assert page.source_type is DocumentType.IMAGE
    assert page.image.shape == (200, 100, 3)  # EXIF rotation still applied
    assert ingestor.get_page_count(path) == 1
