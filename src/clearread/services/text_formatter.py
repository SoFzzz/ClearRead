"""Linguistic text formatter and Token Position Map for bimodal reading."""

import html
import re
import unicodedata
from dataclasses import dataclass

from clearread.services.syllabifier import SpanishSyllabifier

# Bump when the html or the token map change shape: cached documents key on it.
FORMATTER_VERSION = "1"

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A number such as 3,5 or 12.345,67 is one token; otherwise a word with optional
# inner apostrophes/hyphens. Anything else (punctuation, symbols) is not spoken.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+|\w+(?:['’-]\w+)*")
# No line-height in the div style: Qt applies block properties of a <div> to its first
# paragraph only, and its proportional line-height is relative to the font's own line
# pitch, not to the font size. ReaderWidget sets the line spacing on every block instead.


@dataclass(frozen=True)
class ReadingStyle:
    """Typography baked into the html; the values come from AppConfig (§4.6)."""

    font_family: str = "OpenDyslexic"
    font_size_pt: int = 16
    letter_spacing_px: float = 1.5
    word_spacing_px: int = 4

    def css(self) -> str:
        return (
            f"font-family: '{self.font_family}'; font-size: {self.font_size_pt}pt; "
            f"letter-spacing: {self.letter_spacing_px:g}px; "
            f"word-spacing: {self.word_spacing_px}px;"
        )


@dataclass(frozen=True)
class WordToken:
    word_index: int
    spoken_text: str  # clean text handed to the speech engine
    doc_start_pos: int  # first character in QTextDocument.toPlainText()
    doc_end_pos: int  # one past the last character


@dataclass(frozen=True)
class SyllablePalette:
    """Injected by the active theme; colors and contrast ratios are owned by
    the design system, not hardcoded here."""

    color_even: str
    color_odd: str


@dataclass(frozen=True)
class FormattedDocument:
    html_content: str
    token_map: list[WordToken]
    tts_script: str


def normalise_paragraphs(raw_text: str) -> list[str]:
    """Split on blank lines and collapse every whitespace run to one space.

    Qt's HTML import collapses whitespace, so positions must be computed on the
    already-collapsed text (§8 risk: double spaces and stray line breaks). The text
    is composed to NFC first: a PDF may hand over "o" + U+0301, and Qt keeps those as
    two characters, which would shift every position after the accent.
    """
    composed = unicodedata.normalize("NFC", raw_text)
    paragraphs = (" ".join(chunk.split()) for chunk in _PARAGRAPH_BREAK.split(composed))
    return [paragraph for paragraph in paragraphs if paragraph]


class TextFormatter:
    """Segments Spanish text into colored syllables and creates the TTS alignment index.

    Positions refer to ``QTextDocument.toPlainText()`` after ``setHtml``: one
    character per letter and a single ``\\n`` between paragraphs.
    """

    def __init__(
        self,
        syllabifier: SpanishSyllabifier,
        palette: SyllablePalette,
        style: ReadingStyle | None = None,
    ) -> None:
        self._syllabifier = syllabifier
        self._palette = palette
        self._style = style or ReadingStyle()

    def format_document(
        self, raw_text: str, enable_syllables: bool = True
    ) -> FormattedDocument:
        token_map: list[WordToken] = []
        html_paragraphs: list[str] = []
        paragraph_start = 0
        for paragraph in normalise_paragraphs(raw_text):
            html_paragraphs.append(
                self._format_paragraph(
                    paragraph, paragraph_start, enable_syllables, token_map
                )
            )
            paragraph_start += len(paragraph) + 1  # block separator
        body = "".join(html_paragraphs)
        return FormattedDocument(
            html_content=f'<div style="{self._style.css()}">{body}</div>',
            token_map=token_map,
            tts_script=" ".join(token.spoken_text for token in token_map),
        )

    def _format_paragraph(
        self,
        paragraph: str,
        paragraph_start: int,
        enable_syllables: bool,
        token_map: list[WordToken],
    ) -> str:
        parts: list[str] = []
        cursor = 0
        for match in _TOKEN.finditer(paragraph):
            parts.append(html.escape(paragraph[cursor : match.start()]))
            word = match.group()
            token_map.append(
                WordToken(
                    word_index=len(token_map),
                    spoken_text=word,
                    doc_start_pos=paragraph_start + match.start(),
                    doc_end_pos=paragraph_start + match.end(),
                )
            )
            parts.append(self._colour_word(word, enable_syllables))
            cursor = match.end()
        parts.append(html.escape(paragraph[cursor:]))
        return f'<p style="margin-bottom: 14px;">{"".join(parts)}</p>'

    def _colour_word(self, word: str, enable_syllables: bool) -> str:
        syllables = (
            self._syllabifier.syllabify_word(word).syllables if enable_syllables else ()
        )
        if "".join(syllables) != word:
            syllables = (word,)
        colours = (self._palette.color_even, self._palette.color_odd)
        return "".join(
            f'<span style="color: {colours[index % 2]};">{html.escape(syllable)}</span>'
            for index, syllable in enumerate(syllables)
        )
