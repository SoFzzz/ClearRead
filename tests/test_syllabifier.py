"""Syllabification bank (NFR-FON01): 51 complex Spanish words (50 + the sub-r control).

Criterion: PHONETIC division (how the word is pronounced), because that is what helps
decoding. The bank only changes with the user's permission (CLAUDE.md §j); the four
prefix answers were corrected to the phonetic criterion with her explicit approval
(2026-10-07). Threshold: at most 1 mistake (>= 98 %).
"""

import pytest

from clearread.services.syllabifier import SpanishSyllabifier

MAX_MISTAKES = 1

BANK: tuple[tuple[str, str], ...] = (
    # (expected division, category)
    ("dí-a", "hiato acentual"),
    ("ba-úl", "hiato acentual"),
    ("re-ír", "hiato acentual"),
    ("ma-íz", "hiato acentual"),
    ("pa-ís", "hiato acentual"),
    ("rí-o", "hiato acentual"),
    ("ca-í-da", "hiato acentual"),
    ("le-er", "hiato simple"),
    ("ca-er", "hiato simple"),
    ("po-e-ta", "hiato simple"),
    ("te-a-tro", "hiato simple"),
    ("ca-os", "hiato simple"),
    ("bo-a", "hiato simple"),
    ("puer-ta", "diptongo"),
    ("cui-da-do", "diptongo"),
    ("a-gua", "diptongo"),
    ("vien-to", "diptongo"),
    ("cau-sa", "diptongo"),
    ("ciu-dad", "diptongo"),
    ("pei-ne", "diptongo"),
    ("buey", "triptongo"),
    ("a-ve-ri-guáis", "triptongo"),
    ("es-tu-diáis", "triptongo"),
    ("u-ru-guay", "triptongo"),
    ("miau", "triptongo"),
    ("de-sahu-cio", "prefijo"),
    ("sub-ra-yar", "prefijo"),
    ("sub-ro-gar", "prefijo"),
    ("i-nac-ti-vo", "prefijo"),
    ("de-ses-ti-mar", "prefijo"),
    ("su-bur-ba-no", "prefijo"),
    ("in-ha-bi-ta-ble", "prefijo"),
    ("pe-rro", "dígrafo"),
    ("ca-lle", "dígrafo"),
    ("co-che", "dígrafo"),
    ("ca-rro", "dígrafo"),
    ("llu-via", "dígrafo"),
    ("mu-cha-cho", "dígrafo"),
    ("a-bra-zo", "grupo consonántico"),
    ("at-las", "grupo consonántico"),
    ("ap-to", "grupo consonántico"),
    ("pers-pec-ti-va", "grupo consonántico"),
    ("cons-truc-ción", "grupo consonántico"),
    ("ins-tan-te", "grupo consonántico"),
    ("ex-tra-ño", "grupo consonántico"),
    ("ta-xi", "x / h intercalada"),
    ("ahu-ma-do", "x / h intercalada"),
    ("e-xa-men", "x / h intercalada"),
    ("a-ho-ra", "x / h intercalada"),
    ("prohi-bir", "x / h intercalada"),
    ("ex-ha-lar", "x / h intercalada"),
)

syllabifier = SpanishSyllabifier()


def divide(word: str) -> str:
    return "-".join(syllabifier.syllabify_word(word).syllables)


def test_bank_has_51_words() -> None:
    assert len(BANK) == 51


def test_bank_reaches_98_percent() -> None:
    mistakes = [
        f"{category}: esperado {expected}, obtenido {divide(expected.replace('-', ''))}"
        for expected, category in BANK
        if divide(expected.replace("-", "")) != expected
    ]
    assert len(mistakes) <= MAX_MISTAKES, (
        f"{len(mistakes)} fallos de 51:\n" + "\n".join(mistakes)
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("Día", "Dí-a"),
        ("ÁRBOL", "ÁR-BOL"),
        ("Pingüino", "Pin-güi-no"),
        ("ÑANDÚ", "ÑAN-DÚ"),
        ("Averiguáis", "A-ve-ri-guáis"),
    ],
)
def test_case_tildes_and_diaeresis_are_preserved(word: str, expected: str) -> None:
    assert divide(word) == expected


@pytest.mark.parametrize(
    "word", ["hola123", "3,5", "a+b", "co-operar", "d'Artagnan", "¿", "%", "x2"]
)
def test_words_with_digits_or_symbols_are_not_split(word: str) -> None:
    assert syllabifier.syllabify_word(word).syllables == (word,)


def test_empty_word_has_no_syllables() -> None:
    assert syllabifier.syllabify_word("").syllables == ()


def test_result_keeps_the_original_word() -> None:
    assert syllabifier.syllabify_word("Cuaderno").word == "Cuaderno"


@pytest.mark.parametrize(
    "word", ["álbum", "item", "combat", "ejem", "volumen", "Ántrax"]
)
def test_latin_looking_endings_do_not_crash_the_library(word: str) -> None:
    syllables = syllabifier.syllabify_word(word).syllables
    assert "".join(syllables) == word


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("Subrayado", "Sub-ra-ya-do"),
        ("SUBRUTINA", "SUB-RU-TI-NA"),
        ("submarino", "sub-ma-ri-no"),
    ],
)
def test_sub_followed_by_r_keeps_the_prefix_coda(word: str, expected: str) -> None:
    assert divide(word) == expected
