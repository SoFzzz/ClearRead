"""Real cards in tests/samples/private/*.pdf: digital-text bypass and token positions.

Skipped when the folder has no PDFs. Never prints document text (CLAUDE.md §n);
failures name the file, page and token index only.
"""

from pathlib import Path

import pytest
from PySide6.QtGui import QTextDocument
from samples.make_samples import SAMPLES_DIR

from clearread.services.ingestor import DocumentIngestor, PageResult
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import SyllablePalette, TextFormatter

PRIVATE_PDFS = sorted((SAMPLES_DIR / "private").glob("*.pdf"))
PALETTE = SyllablePalette("#111111", "#222222")

pytestmark = pytest.mark.skipif(
    not PRIVATE_PDFS, reason="no PDFs in tests/samples/private"
)


@pytest.fixture(scope="module")
def cards() -> dict[Path, list[PageResult]]:
    ingestor = DocumentIngestor(dpi=72)  # the text layer does not depend on the DPI
    return {pdf: list(ingestor.load(pdf)) for pdf in PRIVATE_PDFS}


def test_every_page_of_every_card_takes_the_digital_bypass(
    cards: dict[Path, list[PageResult]],
) -> None:
    without_text = [
        f"{pdf.name} p{page.page_number}"
        for pdf, pages in cards.items()
        for page in pages
        if page.digital_text is None
    ]
    assert not without_text, f"pages that would need OCR: {without_text}"
    assert all(
        pages and pages[-1].total_pages == len(pages) for pages in cards.values()
    )


def test_token_positions_are_exact_on_every_real_card(
    qapp: object, cards: dict[Path, list[PageResult]]
) -> None:
    formatter = TextFormatter(SpanishSyllabifier(), PALETTE)
    for pdf, pages in cards.items():
        text = "\n\n".join(page.digital_text or "" for page in pages)
        formatted = formatter.format_document(text)
        document = QTextDocument()
        document.setHtml(formatted.html_content)
        plain = document.toPlainText()
        wrong = [
            token.word_index
            for token in formatted.token_map
            if plain[token.doc_start_pos : token.doc_end_pos] != token.spoken_text
        ]
        assert formatted.token_map, pdf.name
        assert not wrong, (
            f"{pdf.name}: {len(wrong)} of {len(formatted.token_map)} tokens off"
        )
