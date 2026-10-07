import random

import pytest
from calibrate_ocr import character_error_rate, levenshtein, special_hits, word_f1


def reference_levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            )
        previous = current
    return previous[-1]


def test_levenshtein_matches_textbook_dp_on_random_strings() -> None:
    rng = random.Random(7)
    for _ in range(300):
        a = "".join(rng.choice("abñ ") for _ in range(rng.randint(0, 25)))
        b = "".join(rng.choice("abñ ") for _ in range(rng.randint(0, 25)))
        assert levenshtein(a, b) == reference_levenshtein(a, b)


def test_cer_ignores_whitespace_differences() -> None:
    assert character_error_rate("hola  mundo\nfeliz", "hola mundo feliz") == 0.0


def test_cer_counts_character_errors() -> None:
    assert character_error_rate("niño", "nino") == pytest.approx(0.25)


def test_word_f1_ignores_order_case_and_punctuation() -> None:
    assert word_f1("El niño lee.", "lee, EL niño") == 1.0


def test_word_f1_of_disjoint_texts_is_zero() -> None:
    assert word_f1("uno dos", "tres cuatro") == 0.0


def test_special_hits_counts_each_character_once_per_occurrence() -> None:
    assert special_hits("niño ñandú ¿sí?", "nino ñandu ¿si?") == (2, 5)
