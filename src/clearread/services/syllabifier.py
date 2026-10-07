"""Spanish syllabification built on the silabeador library."""

from dataclasses import dataclass
from functools import lru_cache

from silabeador import syllabify


@dataclass(frozen=True)
class SyllabificationResult:
    word: str
    syllables: tuple[str, ...]


class SpanishSyllabifier:
    """Splits a word into syllables, keeping its capitalisation, tildes and diaeresis."""

    def syllabify_word(self, word: str) -> SyllabificationResult:
        """Return the syllables of ``word``; words with digits or symbols come back whole."""
        if not word.isalpha():
            return SyllabificationResult(word, (word,) if word else ())
        return SyllabificationResult(word, self._split_preserving_case(word))

    @staticmethod
    def _split_preserving_case(word: str) -> tuple[str, ...]:
        pieces = _library_split(word)
        if "".join(pieces) != word.lower():
            return (word,)
        # silabeador lowercases its input, so its pieces are sliced back from the original.
        syllables: list[str] = []
        start = 0
        for piece in pieces:
            syllables.append(word[start : start + len(piece)])
            start += len(piece)
        return tuple(syllables)


@lru_cache(maxsize=8192)
def _library_split(word: str) -> tuple[str, ...]:
    """Divide with silabeador; cached because it re-reads its exceptions file on every call.

    Words ending in Latin-looking suffixes (-um, -em, -at, -it, -am...) make the
    library's Latin branch return a list where it expects a string (TypeError);
    retrying without its exception rules still yields a valid division.
    """
    for exceptions in (1, 0):
        try:
            return tuple(syllabify(word, exceptions=exceptions))
        except (IndexError, TypeError):
            continue
    return (word,)
