"""I18N-F01: the visible-text catalog is complete and no Spanish leaks into src/."""

import re
from pathlib import Path
from string import Formatter

import pytest

from clearread.ui.strings import CATALOG, Language, MissingStringError, tr

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
SPANISH_CHARS = re.compile("[áéíóúñÁÉÍÓÚÑ¿¡]")
# Language names are shown in their own language in both catalogs.
AUTONYMS = {"settings.language.es", "settings.language.en"}


def _params(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def test_catalog_not_empty() -> None:
    assert CATALOG


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_every_key_has_both_languages_non_empty(key: str) -> None:
    entry = CATALOG[key]
    assert set(entry) == {lang.value for lang in Language}
    assert all(text.strip() for text in entry.values())


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_same_params_in_both_languages(key: str) -> None:
    entry = CATALOG[key]
    assert _params(entry["es"]) == _params(entry["en"])


@pytest.mark.parametrize("key", sorted(set(CATALOG) - AUTONYMS))
def test_english_text_has_no_spanish_characters(key: str) -> None:
    assert not SPANISH_CHARS.search(CATALOG[key]["en"])


def test_tr_fills_params_in_both_languages() -> None:
    assert tr("processing.reading_page", Language.ES, current=5, total=12) == (
        "Leyendo la página 5 de 12"
    )
    assert (
        tr("processing.reading_page", "en", current=5, total=12)
        == "Reading page 5 of 12"
    )


def test_tr_unknown_key_fails_clearly() -> None:
    with pytest.raises(MissingStringError, match="no.such.key"):
        tr("no.such.key", Language.ES)


def test_tr_unknown_language_fails() -> None:
    with pytest.raises(ValueError):
        tr("home.title", "fr")


def test_tr_missing_param_fails() -> None:
    with pytest.raises(KeyError):
        tr("processing.reading_page", Language.EN, current=1)


def test_no_spanish_outside_strings_py() -> None:
    offenders = [
        f"{path.relative_to(SRC_DIR)}:{number}"
        for path in SRC_DIR.rglob("*.py")
        if path.name != "strings.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if SPANISH_CHARS.search(line)
    ]
    assert offenders == []
