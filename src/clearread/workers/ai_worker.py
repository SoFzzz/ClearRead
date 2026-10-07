"""Workers that run AIClient calls off the UI thread (AI-F04, §4.10).

Both are dispatched onto a dedicated QThreadPool with maxThreadCount=1, so calls are
serialized and never race on the client's session counter or the on-disk cache.
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from clearread.services.ai_client import (
    AIClient,
    AIErrorKind,
    AIResponse,
    AIUnavailableError,
)


def create_ai_thread_pool() -> QThreadPool:
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    return pool


class AIWorkerSignals(QObject):
    waking = Signal()  # the backend is starting up (AI-F03)
    finished = Signal(str)  # answer text
    # object, not AIErrorKind: PySide6 does not handle plain Enum members reliably.
    failed = Signal(object)


class _AIWorker(QRunnable):
    def __init__(self, client: AIClient, call: Callable[[], AIResponse]) -> None:
        super().__init__()
        self.signals = AIWorkerSignals()
        self._client = client
        self._call = call

    def run(self) -> None:
        try:
            self._client.ensure_awake(self.signals.waking.emit)
            self.signals.finished.emit(self._call().text)
        except AIUnavailableError as exc:
            self.signals.failed.emit(exc.kind)
        except Exception:  # noqa: BLE001 - the UI must never wait on an unexpected failure
            self.signals.failed.emit(AIErrorKind.BAD_RESPONSE)


class ExplainWordWorker(_AIWorker):
    def __init__(self, client: AIClient, word: str, context_sentence: str) -> None:
        super().__init__(client, lambda: client.explain_word(word, context_sentence))


class SimplifyParagraphWorker(_AIWorker):
    def __init__(self, client: AIClient, text: str) -> None:
        super().__init__(client, lambda: client.simplify_paragraph(text))
