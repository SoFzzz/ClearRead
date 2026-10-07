"""Linguistic text formatter and Token Position Map for bimodal reading."""

import html
import re
from dataclasses import dataclass

from clearread.services.syllabifier import SpanishSyllabifier

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A number such as 3,5 or 12.345,67 is one token; otherwise a word with optional
# inner apostrophes/hyphens. Anything else (punctuation, symbols) is not spoken.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+|\w+(?:['’-]\w+)*")
_DIV_STYLE = (
    "font-family: 'OpenDyslexic'; font-size: 16pt; line-height: 1.8; "
    "letter-spacing: 1.5px; word-spacing: 4px;"
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
    already-collapsed text (§8 risk: double spaces and stray line breaks).
    """
    paragraphs = (" ".join(chunk.split()) for chunk in _PARAGRAPH_BREAK.split(raw_text))
    return [paragraph for paragraph in paragraphs if paragraph]


class TextFormatter:
    """Segments Spanish text into colored syllables and creates the TTS alignment index.

    Positions refer to ``QTextDocument.toPlainText()`` after ``setHtml``: one
    character per letter and a single ``\\n`` between paragraphs.
    """

    def __init__(
        self, syllabifier: SpanishSyllabifier, palette: SyllablePalette
    ) -> None:
        self._syllabifier = syllabifier
        self._palette = palette

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
            html_content=f'<div style="{_DIV_STYLE}">{body}</div>',
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
