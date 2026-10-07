"""Picks the text sent to the assistant and keeps it inside the backend's limits (§4.11)."""

from dataclasses import dataclass

WORD_MAX_CHARS = 40
CONTEXT_MAX_CHARS = 300
PARAGRAPH_MAX_CHARS = 1500

# Written as escapes: strings.py is the only module that holds Spanish characters.
_SENTENCE_ENDS = ".!?\u2026\n"
_EDGE_PUNCTUATION = (
    " \t\n.,;:!?\u00bf\u00a1()[]{}\"'\u00ab\u00bb\u201c\u201d\u2018\u2019"
    "\u2026\u2014\u2013-"
)


@dataclass(frozen=True)
class WordQuery:
    word: str
    context_sentence: str

    @property
    def fits(self) -> bool:
        return 0 < len(self.word) <= WORD_MAX_CHARS


def clean_word(raw: str) -> str:
    """The word without the punctuation that surrounds it in the text."""
    return raw.strip(_EDGE_PUNCTUATION)


def sentence_around(text: str, start: int, end: int) -> str:
    """Sentence that holds ``text[start:end]``: from the previous full stop to the next.

    A sentence longer than the backend accepts is cut to a window around the word.
    """
    left = max((text.rfind(mark, 0, start) for mark in _SENTENCE_ENDS), default=-1) + 1
    right_marks = [text.find(mark, end) for mark in _SENTENCE_ENDS]
    right = min((i for i in right_marks if i != -1), default=len(text) - 1) + 1
    if right - left > CONTEXT_MAX_CHARS:
        budget = CONTEXT_MAX_CHARS - (end - start)
        left = max(left, start - budget // 2)
        right = min(right, left + CONTEXT_MAX_CHARS)
        left = max(left, right - CONTEXT_MAX_CHARS)
    return text[left:right].strip()


def word_query(text: str, start: int, end: int) -> WordQuery:
    return WordQuery(clean_word(text[start:end]), sentence_around(text, start, end))
