"""Contract of the synthetic sample PDFs (tests/samples/make_samples.py).

Also pins the pypdfium2 behaviour Day 3 relies on: there is no
PdfPasswordError; a locked PDF raises PdfiumError with FPDF_ERR_PASSWORD.
"""

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
import pytest
from samples.make_samples import EXPECTED_TEXT, SAMPLE_PASSWORD, SAMPLES_DIR


def first_page_text(document: pdfium.PdfDocument) -> str:
    return document[0].get_textpage().get_text_range().replace("\r\n", "\n").strip()


def test_digital_sample_has_spanish_text_layer() -> None:
    document = pdfium.PdfDocument(str(SAMPLES_DIR / "sample_page_digital.pdf"))
    try:
        assert first_page_text(document) == EXPECTED_TEXT
    finally:
        document.close()


def test_scanned_sample_is_image_only() -> None:
    document = pdfium.PdfDocument(str(SAMPLES_DIR / "sample_page_scanned.pdf"))
    try:
        assert first_page_text(document) == ""
        assert document[0].render(scale=1).to_pil().width > 0
    finally:
        document.close()


def test_password_sample_raises_pdfium_error_without_password() -> None:
    assert not hasattr(pdfium, "PdfPasswordError")
    with pytest.raises(pdfium.PdfiumError) as error:
        pdfium.PdfDocument(str(SAMPLES_DIR / "sample_page_password.pdf"))
    assert error.value.err_code == pdfium_raw.FPDF_ERR_PASSWORD


def test_password_sample_opens_with_password() -> None:
    document = pdfium.PdfDocument(
        str(SAMPLES_DIR / "sample_page_password.pdf"), password=SAMPLE_PASSWORD
    )
    try:
        assert first_page_text(document) == EXPECTED_TEXT
    finally:
        document.close()
