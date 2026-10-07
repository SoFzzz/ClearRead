"""DocumentLibrary: cache round trip, recents order and cap, removal, keys."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from clearread.services.document_library import (
    MAX_RECENTS,
    CachedDocument,
    DocumentLibrary,
    compute_cache_key,
)
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FORMATTER_VERSION,
    SyllablePalette,
    TextFormatter,
)

TEXT = "El niño leyó una canción.\n\nSegundo párrafo."


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(
        tmp_path / "cache", clock=lambda: datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    )


def cached() -> CachedDocument:
    formatter = TextFormatter(SpanishSyllabifier(), SyllablePalette("#111", "#222"))
    return CachedDocument(TEXT, formatter.format_document(TEXT), "light")


def test_key_depends_on_content_and_formatter_version(tmp_path: Path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_bytes(b"same")
    second.write_bytes(b"same")
    assert compute_cache_key(first) == compute_cache_key(second)
    assert compute_cache_key(first).endswith(f"-f{FORMATTER_VERSION}")
    second.write_bytes(b"other")
    assert compute_cache_key(first) != compute_cache_key(second)


def test_store_then_load_returns_the_same_document(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    original = cached()
    library.store("k1", tmp_path / "doc.pdf", original, pages=2, is_photo=False)
    loaded = library.load("k1")
    assert loaded == original


def test_load_of_unknown_or_corrupt_key_is_none(library: DocumentLibrary) -> None:
    assert library.load("missing") is None
    (library._root / "bad.json").write_text("{", encoding="utf-8")
    assert library.load("bad") is None


def test_recents_are_newest_first_and_capped(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    for index in range(MAX_RECENTS + 3):
        library.store(f"k{index}", tmp_path / f"d{index}.pdf", cached(), 1, False)
    recents = library.recents()
    assert len(recents) == MAX_RECENTS
    assert recents[0].key == f"k{MAX_RECENTS + 2}"
    assert not library.has("k0")


def test_storing_again_moves_the_entry_to_the_top_without_duplicates(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    for key in ("a", "b", "c"):
        library.store(key, tmp_path / f"{key}.pdf", cached(), 1, False)
    library.store("a", tmp_path / "a.pdf", cached(), 1, False)
    assert [r.key for r in library.recents()] == ["a", "c", "b"]


def test_remove_deletes_entry_and_cache_file(
    library: DocumentLibrary, tmp_path: Path
) -> None:
    library.store("a", tmp_path / "a.pdf", cached(), 1, True)
    library.remove("a")
    assert library.recents() == []
    assert not library.has("a")
