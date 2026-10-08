"""Linguistic text formatter and Token Position Map for bimodal reading."""

import bisect
import html
import re
import unicodedata
from dataclasses import dataclass

from clearread.services.syllabifier import SpanishSyllabifier

# Bump when the html or the token map change shape: cached documents key on it.
FORMATTER_VERSION = "3"

CSS_PX_PER_PT = 96 / 72
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A number such as 3,5 or 12.345,67 is one token; otherwise a word with optional
# inner apostrophes/hyphens. Matches without a letter or digit (a lone "_") are skipped.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+|\w+(?:['’-]\w+)*")
# Characters kept in the speech; any other symbol becomes a space so the voice does
# not name it ("asterisco"). Stops are kept because they are what makes it pause.
# The inverted marks are built from code points: strings.py is the only file in src/
# allowed to contain them literally (tests/test_strings.py).
_SPEECH_KEPT = frozenset(".,;:!?…-–—()\"'“”«»‘’%/$€+" + chr(0xBF) + chr(0xA1))
_SENTENCE_END = (".", "!", "?", "…", ":", ";")
_CLOSERS = " \"”»)’'"
# No line-height in the div style: Qt applies block properties of a <div> to its first
# paragraph only, and its proportional line-height is relative to the font's own line
# pitch, not to the font size. ReaderWidget sets the line spacing on every block instead.


@dataclass(frozen=True)
class ReadingStyle:
    """Typography baked into the html; the values come from AppConfig (§4.6)."""

    font_family: str = "Lexend"
    font_size_pt: int = 18
    letter_spacing_em: float = 0.12
    word_spacing_em: float = 0.16

    @property
    def font_size_px(self) -> float:
        return self.font_size_pt * CSS_PX_PER_PT

    def css(self) -> str:
        # Qt's rich text takes spacing in px, so the em values are scaled by the font size.
        return (
            f"font-family: '{self.font_family}'; font-size: {self.font_size_pt}pt; "
            f"letter-spacing: {self.letter_spacing_em * self.font_size_px:.2f}px; "
            f"word-spacing: {self.word_spacing_em * self.font_size_px:.2f}px;"
        )


@dataclass(frozen=True)
class WordToken:
    word_index: int
    spoken_text: str  # the word as it appears in the document
    doc_start_pos: int  # first character in QTextDocument.toPlainText()
    doc_end_pos: int  # one past the last character


@dataclass(frozen=True)
class SyllablePalette:
    """Injected by the active theme; colors and contrast ratios are owned by
    the design system, not hardcoded here."""

    color_even: str
    color_odd: str
    background_odd: str | None = None  # soft fill behind every odd syllable


@dataclass(frozen=True)
class FormattedDocument:
    html_content: str
    token_map: list[WordToken]
    tts_script: str  # the document's plain text: token positions index into it


@dataclass(frozen=True)
class SpeechText:
    """What SAPI5 receives, with the character span of each token inside it."""

    text: str
    word_spans: list[tuple[int, int]]


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


def token_index_at(token_map: list[WordToken], char_index: int) -> int:
    """Index of the word that contains ``char_index``, or of the next one.

    A space or punctuation mark between two words belongs to the word that follows;
    past the last word the last one is returned. ``token_map`` must not be empty.
    """
    candidate = bisect.bisect_right(
        token_map, char_index, key=lambda token: token.doc_start_pos
    )
    if candidate > 0 and char_index < token_map[candidate - 1].doc_end_pos:
        return candidate - 1
    return min(candidate, len(token_map) - 1)


def _speakable(gap: str) -> str:
    """Blank the symbols a voice would name; one character in, one out."""
    return "".join(
        char if char.isalnum() or char.isspace() or char in _SPEECH_KEPT else " "
        for char in gap
    )


def _with_paragraph_stop(gap: str) -> str:
    """Make a paragraph break pause: SAPI5 runs a heading into the next paragraph."""
    before, newline, after = gap.partition("\n")
    if not newline or before.rstrip(_CLOSERS).endswith(_SENTENCE_END):
        return gap
    return f"{before.rstrip()}.{newline}{after}"


def speech_from(
    tts_script: str, token_map: list[WordToken], first_index: int
) -> SpeechText:
    """Text for SAPI5 from token ``first_index`` on, keeping punctuation and paragraphs.

    Offsets are recomputed on the text actually sent, so the voice's character events
    map back to tokens even where a stop was inserted.
    """
    pieces: list[str] = []
    spans: list[tuple[int, int]] = []
    length = 0
    cursor = token_map[first_index].doc_start_pos
    for token in token_map[first_index:]:
        gap = _with_paragraph_stop(_speakable(tts_script[cursor : token.doc_start_pos]))
        word = tts_script[token.doc_start_pos : token.doc_end_pos]
        length += len(gap)
        spans.append((length, length + len(word)))
        pieces += [gap, word]
        length += len(word)
        cursor = token.doc_end_pos
    pieces.append(_speakable(tts_script[cursor:]))
    return SpeechText("".join(pieces), spans)


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
        paragraphs = normalise_paragraphs(raw_text)
        for paragraph in paragraphs:
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
            tts_script="\n".join(paragraphs),
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
            word = match.group()
            if not any(char.isalnum() for char in word):
                continue
            parts.append(html.escape(paragraph[cursor : match.start()]))
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
        return "".join(
            f'<span style="{self._syllable_style(index)}">{html.escape(syllable)}</span>'
            for index, syllable in enumerate(syllables)
        )

    def _syllable_style(self, index: int) -> str:
        if index % 2 == 0:
            return f"color: {self._palette.color_even};"
        style = f"color: {self._palette.color_odd};"
        if self._palette.background_odd:
            style += f" background-color: {self._palette.background_odd};"
        return style
