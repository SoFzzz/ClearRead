"""Case- and accent-insensitive text matching shared by the library and the glossary."""

import unicodedata


def search_key(text: str) -> str:
    """Lower case, accents removed, single spaces: the key two spellings share."""
    decomposed = unicodedata.normalize("NFD", " ".join(text.lower().split()))
    return "".join(c for c in decomposed if not unicodedata.combining(c))
