"""I18N-F01: the visible-text catalog is complete and no Spanish leaks into src/."""

import re
from pathlib import Path
from string import Formatter

import pytest

from clearread.services.account_client import AccountErrorKind
from clearread.services.ai_client import AIErrorKind
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
        tr("home.dashboard_title", "fr")


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


def test_every_account_error_kind_has_a_message() -> None:
    missing = [
        kind.name
        for kind in AccountErrorKind
        if f"auth.error.{kind.name.lower()}" not in CATALOG
    ]
    assert missing == []


def test_every_ai_error_kind_has_a_message() -> None:
    missing = [
        kind.name
        for kind in AIErrorKind
        if f"ai.error.{kind.name.lower()}" not in CATALOG
    ]
    assert missing == []


GOOGLE_TEXTS = {
    "auth.google_sign_in": ("Entrar con Google", "Sign in with Google"),
    "auth.or_with_email": ("o con tu correo", "or with your email"),
    "account.google_link": ("Vincular con Google", "Link with Google"),
    "account.google_linked": ("Google vinculado", "Google linked"),
    "google.waiting_title": ("Esperando a Google…", "Waiting for Google…"),
    "google.waiting_cancel": ("Cancelar", "Cancel"),
    "auth.error.google_attempt_not_found": (
        "Se perdió el intento con Google. Inténtalo otra vez.",
        "The Google attempt was lost. Try again.",
    ),
    "auth.error.google_attempt_expired": (
        "Pasó demasiado tiempo esperando a Google. Inténtalo otra vez.",
        "It took too long to hear from Google. Try again.",
    ),
    "auth.error.browser_unavailable": (
        "No pudimos abrir tu navegador. Ábrelo tú y vuelve a intentarlo.",
        "We couldn't open your browser. Open it yourself and try again.",
    ),
}
GOOGLE_KEYS = [
    *GOOGLE_TEXTS,
    "google.waiting_body",
    "auth.error.google_cancelled",
    "auth.error.google_already_linked",
    "auth.error.google_not_linked",
    "auth.error.google_not_configured",
]


@pytest.mark.parametrize("key", GOOGLE_KEYS)
def test_google_keys_have_both_languages_and_the_same_parameters(key: str) -> None:
    es, en = tr(key, Language.ES), tr(key, Language.EN)
    assert es and en and es != en
    assert "{" not in CATALOG[key]["es"] and "{" not in CATALOG[key]["en"]


@pytest.mark.parametrize(("key", "texts"), list(GOOGLE_TEXTS.items()))
def test_google_texts_match_the_design_document(
    key: str, texts: tuple[str, str]
) -> None:
    assert (tr(key, Language.ES), tr(key, Language.EN)) == texts
