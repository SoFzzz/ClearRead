"""AI workers: signals, serialization and the guarantee that nothing escapes (§4.10)."""

from collections.abc import Callable

import pytest
from pytestqt.qtbot import QtBot

from clearread.services.ai_client import (
    AIClient,
    AIErrorKind,
    AIResponse,
    AIUnavailableError,
)
from clearread.workers.ai_worker import (
    ExplainWordWorker,
    SimplifyParagraphWorker,
    create_ai_thread_pool,
)


class ScriptedClient(AIClient):
    def __init__(
        self,
        awake: Callable[[Callable[[], None]], None] = lambda on_waking: None,
        answer: Callable[[], AIResponse] = lambda: AIResponse("listo"),
    ) -> None:
        self._awake = awake
        self._answer = answer
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def ensure_awake(self, on_waking: Callable[[], None]) -> None:
        self._awake(on_waking)

    def explain_word(self, word: str, context_sentence: str) -> AIResponse:
        self.calls.append(("explain", (word, context_sentence)))
        return self._answer()

    def simplify_paragraph(self, text: str) -> AIResponse:
        self.calls.append(("simplify", (text,)))
        return self._answer()


def run(worker: ExplainWordWorker | SimplifyParagraphWorker) -> None:
    pool = create_ai_thread_pool()
    pool.start(worker)
    assert pool.waitForDone(5000)


def test_pool_is_serialized() -> None:
    assert create_ai_thread_pool().maxThreadCount() == 1


def test_explain_emits_finished(qtbot: QtBot) -> None:
    client = ScriptedClient()
    worker = ExplainWordWorker(client, "casa", "Mi casa.")
    with qtbot.waitSignal(worker.signals.finished, timeout=5000) as blocker:
        run(worker)
    assert blocker.args == ["listo"]
    assert client.calls == [("explain", ("casa", "Mi casa."))]


def test_simplify_emits_finished(qtbot: QtBot) -> None:
    client = ScriptedClient()
    worker = SimplifyParagraphWorker(client, "texto")
    with qtbot.waitSignal(worker.signals.finished, timeout=5000):
        run(worker)
    assert client.calls == [("simplify", ("texto",))]


def test_waking_is_emitted_before_finished(qtbot: QtBot) -> None:
    client = ScriptedClient(awake=lambda on_waking: on_waking())
    worker = SimplifyParagraphWorker(client, "texto")
    events: list[str] = []
    worker.signals.waking.connect(lambda: events.append("waking"))
    worker.signals.finished.connect(lambda text: events.append("finished"))
    run(worker)
    qtbot.waitUntil(lambda: events == ["waking", "finished"], timeout=2000)


def test_known_failure_emits_its_kind(qtbot: QtBot) -> None:
    def refuse() -> AIResponse:
        raise AIUnavailableError(AIErrorKind.DAILY_LIMIT)

    worker = ExplainWordWorker(ScriptedClient(answer=refuse), "a", "b")
    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)
    assert blocker.args == [AIErrorKind.DAILY_LIMIT]


def test_failure_while_waking_emits_server_waking(qtbot: QtBot) -> None:
    def never(on_waking: Callable[[], None]) -> None:
        raise AIUnavailableError(AIErrorKind.SERVER_WAKING)

    worker = ExplainWordWorker(ScriptedClient(awake=never), "a", "b")
    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)
    assert blocker.args == [AIErrorKind.SERVER_WAKING]


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyError("x"), OSError()])
def test_unexpected_exception_never_escapes(qtbot: QtBot, error: Exception) -> None:
    def explode() -> AIResponse:
        raise error

    worker = SimplifyParagraphWorker(ScriptedClient(answer=explode), "t")
    with qtbot.waitSignal(worker.signals.failed, timeout=5000) as blocker:
        run(worker)
    assert blocker.args == [AIErrorKind.BAD_RESPONSE]
