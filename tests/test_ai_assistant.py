"""Assistant panel: its states, the privacy notice, size limits and the spoken answer."""

from collections.abc import Iterator

import pytest
from fakes import EngineSource, FakeAIClient
from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from clearread.services.ai_client import AIErrorKind
from clearread.services.ai_text import (
    CONTEXT_MAX_CHARS,
    PARAGRAPH_MAX_CHARS,
    WORD_MAX_CHARS,
    sentence_around,
    word_query,
)
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.ai_assistant import AIAssistant
from clearread.ui.fonts import load_reading_font
from clearread.ui.strings import Language, tr
from clearread.ui.theme import THEMES, ThemeId, syllable_palette
from clearread.ui.views.ai_panel import AIMode, PanelState
from clearread.ui.views.reading_view import PlaybackState, ReadingView

TEXT = (
    "Los cloroplastos hacen la comida de la planta. Son muy pequeños.\n\n"
    "Segundo párrafo con cinco palabras."
)
TIMEOUT_MS = 5000


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource(word_delay_s=0.02)


@pytest.fixture
def tts(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    controller = TTSController(engine_factory=engines)
    yield controller
    controller.shutdown()


def build(
    qtbot: QtBot,
    tts: TTSController,
    client: FakeAIClient,
    accepted: bool = True,
    language: Language = Language.ES,
) -> tuple[ReadingView, AIAssistant]:
    load_reading_font()
    view = ReadingView(tts, language=language)
    qtbot.addWidget(view)
    formatter = TextFormatter(
        SpanishSyllabifier(), syllable_palette(THEMES[ThemeId.LIGHT])
    )
    view.load_document(formatter.format_document(TEXT))
    view.resize(1200, 700)
    view.show()
    assistant = AIAssistant(client, view, accepted)
    return view, assistant


def wait_state(qtbot: QtBot, view: ReadingView, state: PanelState) -> None:
    qtbot.waitUntil(lambda: view.ai_panel.state is state, timeout=TIMEOUT_MS)


def test_panel_starts_hidden_and_empty_with_instructions(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, _ = build(qtbot, tts, FakeAIClient())
    assert not view.assistant_open
    view.set_assistant_open(True)
    assert view.ai_panel.state is PanelState.EMPTY
    assert view.ai_panel.empty_body.text() == tr("ai.empty.body", Language.ES)


def test_loading_then_answer(qtbot: QtBot, tts: TTSController) -> None:
    client = FakeAIClient(text="Es una parte de la célula.")
    client.hold.clear()
    view, assistant = build(qtbot, tts, client)
    assistant.request_explain("cloroplastos", "Los cloroplastos hacen la comida.")
    assert view.assistant_open
    assert view.ai_panel.state is PanelState.LOADING
    assert view.ai_panel.status_title.text() == tr("ai.loading", Language.ES)
    assert view.ai_panel.chip.text() == "cloroplastos"
    client.hold.set()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert view.ai_panel.answer_body.text() == "Es una parte de la célula."
    assert view.ai_panel.answer_title.text() == tr("ai.answer_title_word", Language.ES)
    assert view.ai_panel.counter_label.text() == tr(
        "ai.session_counter", Language.ES, used=1, limit=30
    )
    assert client.calls == [
        ("explain", ("cloroplastos", "Los cloroplastos hacen la comida."))
    ]


def test_waking_notice_then_answer(qtbot: QtBot, tts: TTSController) -> None:
    client = FakeAIClient(waking=True)
    client.hold.clear()
    view, assistant = build(qtbot, tts, client)
    assistant.request_simplify("Un párrafo difícil.")
    wait_state(qtbot, view, PanelState.WAKING)
    assert view.ai_panel.status_title.text() == tr("ai.waking.title", Language.ES)
    assert view.ai_panel.status_detail.text() == tr("ai.waking.detail", Language.ES)
    client.hold.set()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert view.ai_panel.answer_title.text() == tr(
        "ai.answer_title_paragraph", Language.ES
    )


@pytest.mark.parametrize("language", list(Language))
@pytest.mark.parametrize("kind", list(AIErrorKind))
def test_error_shows_its_text_inside_the_panel(
    qtbot: QtBot, tts: TTSController, kind: AIErrorKind, language: Language
) -> None:
    view, assistant = build(qtbot, tts, FakeAIClient(error=kind), language=language)
    assistant.request_explain("casa", "Mi casa.")
    wait_state(qtbot, view, PanelState.ERROR)
    panel = view.ai_panel
    assert panel.error_message.text() == tr(f"ai.error.{kind.name.lower()}", language)
    retry = kind not in (
        AIErrorKind.SESSION_LIMIT,
        AIErrorKind.DAILY_LIMIT,
        AIErrorKind.INPUT_TOO_LONG,
    )
    assert panel.retry_button.isHidden() is not retry


def test_retry_asks_again(qtbot: QtBot, tts: TTSController) -> None:
    client = FakeAIClient(error=AIErrorKind.TIMEOUT)
    view, assistant = build(qtbot, tts, client)
    assistant.request_explain("casa", "Mi casa.")
    wait_state(qtbot, view, PanelState.ERROR)
    client.error = None
    view.ai_panel.retry_button.click()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert len(client.calls) == 2


def test_privacy_notice_blocks_sending_until_accepted(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, assistant = build(qtbot, tts, client, accepted=False)
    assistant.request_explain("casa", "Mi casa.")
    assert view.ai_panel.state is PanelState.PRIVACY
    assert client.calls == []
    with qtbot.waitSignal(assistant.privacy_accepted, timeout=TIMEOUT_MS):
        view.ai_panel.accept_button.click()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert client.calls == [("explain", ("casa", "Mi casa."))]


def test_declining_the_privacy_notice_sends_nothing(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, assistant = build(qtbot, tts, client, accepted=False)
    assistant.request_simplify("Un párrafo.")
    view.ai_panel.decline_button.click()
    assert view.ai_panel.state is PanelState.EMPTY
    assistant.request_explain("casa", "Mi casa.")
    assert view.ai_panel.state is PanelState.PRIVACY  # still asked: it was not accepted
    assert client.calls == []


def test_paragraph_too_long_does_not_call_the_client(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, assistant = build(qtbot, tts, client)
    assistant.request_simplify("palabra " * (PARAGRAPH_MAX_CHARS // 8 + 1))
    assert view.ai_panel.state is PanelState.ERROR
    assert view.ai_panel.error_message.text() == tr(
        "ai.error.input_too_long", Language.ES
    )
    assert client.calls == []


def test_word_too_long_does_not_call_the_client(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, assistant = build(qtbot, tts, client)
    assistant.request_explain("a" * (WORD_MAX_CHARS + 1), "Una frase.")
    assert view.ai_panel.state is PanelState.ERROR
    assert client.calls == []


def test_a_request_in_progress_ignores_new_ones(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    client.hold.clear()
    view, assistant = build(qtbot, tts, client)
    assistant.request_explain("uno", "Uno.")
    assistant.request_explain("dos", "Dos.")
    assistant.request_simplify("Tres.")
    client.hold.set()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert client.calls == [("explain", ("uno", "Uno."))]


def test_cancel_drops_the_late_answer(qtbot: QtBot, tts: TTSController) -> None:
    client = FakeAIClient()
    client.hold.clear()
    view, assistant = build(qtbot, tts, client)
    assistant.request_explain("uno", "Uno.")
    view.ai_panel.cancel_button.click()
    assert view.ai_panel.state is PanelState.EMPTY
    client.hold.set()
    qtbot.wait(300)
    assert view.ai_panel.state is PanelState.EMPTY
    assert not assistant.busy


def test_offline_disables_the_panel_and_sends_nothing(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, assistant = build(qtbot, tts, client)
    view.set_assistant_open(True)
    assistant.set_online(False)
    panel = view.ai_panel
    assert panel.state is PanelState.OFFLINE
    assert panel.offline_body.text() == tr("ai.offline_tooltip", Language.ES)
    assert not panel.explain_button.isEnabled()
    assert not panel.simplify_button.isEnabled()
    assistant.request_explain("casa", "Mi casa.")
    assert client.calls == []
    assistant.set_online(True)
    assert panel.state is PanelState.EMPTY
    assert panel.explain_button.isEnabled()


def test_listening_pauses_the_document_and_leaves_its_place_alone(
    qtbot: QtBot, tts: TTSController, engines: EngineSource
) -> None:
    view, assistant = build(qtbot, tts, FakeAIClient(text="Una respuesta corta."))
    view.toggle_play()
    qtbot.waitUntil(lambda: view.current_word_idx > 1, timeout=TIMEOUT_MS)
    assistant.request_explain("casa", "Mi casa.")
    assert view.state is PlaybackState.PAUSED
    wait_state(qtbot, view, PanelState.ANSWER)
    place = view.current_word_idx
    view.ai_panel.listen_button.click()
    assert view.ai_panel.listen_button.text() == tr("ai.listen_stop", Language.ES)
    qtbot.waitUntil(
        lambda: "Una respuesta corta." in engines.latest.said, timeout=TIMEOUT_MS
    )
    qtbot.waitUntil(
        lambda: view.ai_panel.listen_button.text() == tr("ai.listen", Language.ES),
        timeout=TIMEOUT_MS,
    )
    assert view.current_word_idx == place
    assert view.state is PlaybackState.PAUSED


def test_closing_the_panel_stops_the_spoken_answer(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, assistant = build(qtbot, tts, FakeAIClient(text="palabra " * 60))
    assistant.request_simplify("Un párrafo.")
    wait_state(qtbot, view, PanelState.ANSWER)
    view.ai_panel.listen_button.click()
    view.set_assistant_open(False)
    assert view.ai_panel.listen_button.text() == tr("ai.listen", Language.ES)


def test_escape_closes_the_panel_before_stopping_the_reading(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, _ = build(qtbot, tts, FakeAIClient())
    view.set_assistant_open(True)
    view._on_escape()
    assert not view.assistant_open


def test_explain_at_sends_the_word_with_its_sentence(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, _ = build(qtbot, tts, FakeAIClient())
    position = view.editor.toPlainText().index("comida")
    with qtbot.waitSignal(view.explain_requested, timeout=TIMEOUT_MS) as blocker:
        view.explain_at(position)
    assert blocker.args == ["comida", "Los cloroplastos hacen la comida de la planta."]


def test_simplify_at_sends_the_paragraph_or_the_selection(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, _ = build(qtbot, tts, FakeAIClient())
    with qtbot.waitSignal(view.simplify_requested, timeout=TIMEOUT_MS) as blocker:
        view.simplify_at(view.editor.toPlainText().index("Segundo"))
    assert blocker.args == ["Segundo párrafo con cinco palabras."]
    cursor = view.editor.textCursor()
    start = view.editor.toPlainText().index("Son")
    cursor.setPosition(start)
    cursor.setPosition(start + 3, cursor.MoveMode.KeepAnchor)
    view.editor.setTextCursor(cursor)
    with qtbot.waitSignal(view.simplify_requested, timeout=TIMEOUT_MS) as blocker:
        view.simplify_at(start + 1)
    assert blocker.args == ["Son"]


def test_right_click_asks_for_the_menu_only_when_the_assistant_is_on(
    qtbot: QtBot, tts: TTSController
) -> None:
    view, _ = build(qtbot, tts, FakeAIClient())
    # The real slot opens a blocking menu; only the request itself is checked here.
    view.editor.context_menu_requested.disconnect(view._show_context_menu)
    point = QPoint(80, 40)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, point, view.editor.viewport().mapToGlobal(point)
    )
    with qtbot.waitSignal(view.editor.context_menu_requested, timeout=TIMEOUT_MS):
        QApplication.sendEvent(view.editor.viewport(), event)
    view.set_assistant_available(False)
    with qtbot.assertNotEmitted(view.editor.context_menu_requested):
        QApplication.sendEvent(
            view.editor.viewport(),
            QContextMenuEvent(
                QContextMenuEvent.Reason.Keyboard,
                point,
                view.editor.viewport().mapToGlobal(point),
            ),
        )


def test_panel_buttons_work_on_the_current_word(
    qtbot: QtBot, tts: TTSController
) -> None:
    client = FakeAIClient()
    view, _ = build(qtbot, tts, client)
    view.set_assistant_open(True)
    view.ai_panel.explain_button.click()
    assert client.calls == []  # nothing chosen yet: the instructions stay
    assert view.ai_panel.state is PanelState.EMPTY
    view.explain_at(view.editor.toPlainText().index("planta"))
    wait_state(qtbot, view, PanelState.ANSWER)
    view.ai_panel.simplify_button.click()
    wait_state(qtbot, view, PanelState.ANSWER)
    assert [name for name, _ in client.calls] == ["explain", "simplify"]


def test_chosen_chip_marks_the_active_mode(qtbot: QtBot, tts: TTSController) -> None:
    view, assistant = build(qtbot, tts, FakeAIClient())
    assistant.request_simplify("Un párrafo muy largo " * 5)
    assert view.ai_panel.chip.text().endswith("…")
    assert view.ai_panel._mode is AIMode.SIMPLIFY


def test_sentence_around_cuts_to_the_backend_limit() -> None:
    sentence = "palabra " * 80
    text = f"Antes. {sentence}fin. Después."
    start = text.index("fin")
    result = sentence_around(text, start, start + 3)
    assert len(result) <= CONTEXT_MAX_CHARS
    assert "fin" in result


def test_word_query_strips_punctuation_and_keeps_the_sentence() -> None:
    text = "Hola mundo. ¿Qué es “casa”, dime? Adiós."
    start = text.index("casa") - 1
    query = word_query(text, start, start + 6)
    assert query.word == "casa"
    assert query.context_sentence.endswith("dime?")
    assert query.fits
