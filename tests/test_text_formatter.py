import pytest
from PySide6.QtGui import QTextDocument

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    FormattedDocument,
    SyllablePalette,
    TextFormatter,
    normalise_paragraphs,
)

PALETTE = SyllablePalette(color_even="#111111", color_odd="#222222")


@pytest.fixture
def formatter() -> TextFormatter:
    return TextFormatter(SpanishSyllabifier(), PALETTE)


def plain_text_of(formatted: FormattedDocument) -> str:
    document = QTextDocument()
    document.setHtml(formatted.html_content)
    return document.toPlainText()


def assert_tokens_match_qt(formatted: FormattedDocument) -> None:
    plain = plain_text_of(formatted)
    wrong = [
        token.word_index
        for token in formatted.token_map
        if plain[token.doc_start_pos : token.doc_end_pos] != token.spoken_text
    ]
    assert not wrong, f"tokens fuera de posición: {wrong[:10]}"


def spoken(formatted: FormattedDocument) -> list[str]:
    return [token.spoken_text for token in formatted.token_map]


@pytest.mark.parametrize(
    "text",
    [
        "Hola mundo.",
        "Primer párrafo con cinco palabras.\n\nSegundo párrafo.\n\n\n\nTercero.",
        "¿Qué quieres? ¡Vamos! «comillas» (paréntesis), [corchetes]; “dobles” —raya—.",
        "Cuesta 3,5 euros y 12.345,67 dólares; el 2026 fue año 1.",
        "Una <etiqueta> & un \"entrecomillado\" y 'simple' con a < b > c.",
        "Dos  espacios   y\ttabulador\r\ny un salto\nsuelto dentro del párrafo.",
        "  Espacios al inicio y al final.  \n\n   \n\nOtro.",
        "d'Artagnan hispano-americano co-operar x2 hola123 niño pingüino.",
        "Palabras ÁRBOL Ñandú ÜBER con MAYÚSCULAS.",
        "Símbolos → ∑ ≠ sin letras y 100% seguro @usuario #etiqueta.",
        "Unicode combinado: café y emoji 🙂 junto a texto.",
    ],
)
def test_token_positions_match_a_real_qtextdocument(
    qapp: object, formatter: TextFormatter, text: str
) -> None:
    for syllables in (True, False):
        assert_tokens_match_qt(
            formatter.format_document(text, enable_syllables=syllables)
        )


def test_multiple_paragraphs_become_blocks(
    qapp: object, formatter: TextFormatter
) -> None:
    formatted = formatter.format_document("Uno dos.\n\nTres cuatro.")
    assert plain_text_of(formatted) == "Uno dos.\nTres cuatro."
    assert spoken(formatted) == ["Uno", "dos", "Tres", "cuatro"]


def test_punctuation_is_not_part_of_the_spoken_word(formatter: TextFormatter) -> None:
    formatted = formatter.format_document("¿Qué? «comillas» (paréntesis), fin.")
    assert spoken(formatted) == ["Qué", "comillas", "paréntesis", "fin"]


def test_numbers_are_single_tokens(formatter: TextFormatter) -> None:
    formatted = formatter.format_document("Son 3,5 y 12.345,67 y 2026.")
    assert spoken(formatted) == ["Son", "3,5", "y", "12.345,67", "y", "2026"]


def test_whitespace_is_normalised_before_positions(formatter: TextFormatter) -> None:
    formatted = formatter.format_document("uno   dos\ntres\n\ncuatro")
    assert formatted.tts_script == "uno dos tres cuatro"
    assert [t.doc_start_pos for t in formatted.token_map] == [0, 4, 8, 13]


def test_script_and_angle_brackets_are_escaped(
    qapp: object, formatter: TextFormatter
) -> None:
    formatted = formatter.format_document("<script>alert(1)</script> y a & b")
    assert "<script" not in formatted.html_content
    assert "&lt;" in formatted.html_content
    assert "&amp;" in formatted.html_content
    assert plain_text_of(formatted) == "<script>alert(1)</script> y a & b"
    assert_tokens_match_qt(formatted)


def test_html_has_balanced_tags(formatter: TextFormatter) -> None:
    html_content = formatter.format_document("a & b <i>x</i>\n\nsegundo").html_content
    for tag in ("div", "p", "span"):
        assert html_content.count(f"<{tag}") == html_content.count(f"</{tag}>")


def test_syllables_alternate_palette_colours(formatter: TextFormatter) -> None:
    html_content = formatter.format_document("cuaderno").html_content
    assert 'color: #111111;">cua<' in html_content
    assert 'color: #222222;">der<' in html_content
    assert 'color: #111111;">no<' in html_content


def test_syllables_can_be_disabled(formatter: TextFormatter) -> None:
    html_content = formatter.format_document(
        "cuaderno", enable_syllables=False
    ).html_content
    assert html_content.count("<span") == 1


def test_palette_is_injected_not_hardcoded() -> None:
    other = TextFormatter(SpanishSyllabifier(), SyllablePalette("#abcdef", "#fedcba"))
    assert "#abcdef" in other.format_document("hola").html_content


def test_empty_text_gives_empty_document(
    qapp: object, formatter: TextFormatter
) -> None:
    formatted = formatter.format_document("  \n\n  ")
    assert formatted.token_map == []
    assert formatted.tts_script == ""
    assert plain_text_of(formatted) == ""


def test_normalise_paragraphs() -> None:
    assert normalise_paragraphs(" a  b\nc \n \n d ") == ["a b c", "d"]


def test_decomposed_accents_are_composed_before_positions(
    formatter: TextFormatter,
) -> None:
    decomposed = "El niño leyó una canción.\n\nComió piña."
    formatted = formatter.format_document(decomposed)
    assert spoken(formatted) == [
        "El",
        "niño",
        "leyó",
        "una",
        "canción",
        "Comió",
        "piña",
    ]
    assert_tokens_match_qt(formatted)
    assert "́" not in plain_text_of(formatted)
