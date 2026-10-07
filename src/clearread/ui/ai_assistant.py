"""Connects the reading view and the assistant panel to the AI workers (AI-F01..F04).

The UI never calls the network: requests go to workers on a dedicated pool and the
answers come back as queued signals.
"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from clearread.services.ai_client import AIClient, AIErrorKind
from clearread.services.ai_text import (
    CONTEXT_MAX_CHARS,
    PARAGRAPH_MAX_CHARS,
    WORD_MAX_CHARS,
)
from clearread.ui.views.ai_panel import AIMode
from clearread.ui.views.reading_view import ReadingView
from clearread.workers.ai_worker import (
    ExplainWordWorker,
    SimplifyParagraphWorker,
    create_ai_thread_pool,
)

CHIP_MAX_CHARS = 28
_ELLIPSIS = "…"


@dataclass(frozen=True)
class AIRequest:
    mode: AIMode
    text: str  # the word, or the paragraph
    sentence: str = ""  # context of the word

    @property
    def chip(self) -> str:
        if len(self.text) <= CHIP_MAX_CHARS:
            return self.text
        return self.text[:CHIP_MAX_CHARS].rstrip() + _ELLIPSIS

    @property
    def fits(self) -> bool:
        if self.mode is AIMode.EXPLAIN:
            return (
                0 < len(self.text) <= WORD_MAX_CHARS
                and len(self.sentence) <= CONTEXT_MAX_CHARS
            )
        return len(self.text) <= PARAGRAPH_MAX_CHARS


class AIAssistant(QObject):
    privacy_accepted = (
        Signal()
    )  # the first-use notice was accepted: keep it in the config

    def __init__(
        self,
        client: AIClient,
        view: ReadingView,
        privacy_accepted: bool,
        pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._view = view
        self._panel = view.ai_panel
        self._pool = pool or create_ai_thread_pool()
        self._privacy_ok = privacy_accepted
        self._online = True
        self._pending: AIRequest | None = None  # waits for the privacy notice
        self._last: AIRequest | None = None
        self._answer = ""
        self._listening = False
        self._active: QObject | None = None  # signals of the request being waited for
        self._in_flight: set[QObject] = set()  # kept alive until their worker ends
        self._connect()
        self._refresh_counter()
        view.set_assistant_available(True)

    def _connect(self) -> None:
        self._view.explain_requested.connect(self.request_explain)
        self._view.simplify_requested.connect(self.request_simplify)
        self._view.aside_finished.connect(self._on_aside_finished)
        panel = self._panel
        panel.explain_clicked.connect(self._explain_current)
        panel.simplify_clicked.connect(self._simplify_current)
        panel.cancel_clicked.connect(self.cancel)
        panel.retry_clicked.connect(self._retry)
        panel.privacy_accepted.connect(self._accept_privacy)
        panel.privacy_declined.connect(self._decline_privacy)
        panel.listen_clicked.connect(self._toggle_listen)

    @property
    def busy(self) -> bool:
        return self._active is not None

    def set_online(self, online: bool) -> None:
        self._online = online
        self._panel.set_online(online)

    def toggle_panel(self) -> None:
        self._view.set_assistant_open(not self._view.assistant_open)

    def request_explain(self, word: str, sentence: str) -> None:
        self._submit(AIRequest(AIMode.EXPLAIN, word, sentence))

    def request_simplify(self, text: str) -> None:
        self._submit(AIRequest(AIMode.SIMPLIFY, text))

    def cancel(self) -> None:
        """Stop waiting; the worker ends by itself and its answer is dropped."""
        self._active = None
        self._panel.show_empty()

    def _submit(self, request: AIRequest) -> None:
        if self.busy:
            return
        self._view.set_assistant_open(True)
        self._view.stop_aside()
        self._panel.set_chosen(request.chip, request.mode)
        if not self._online:
            self._panel.show_offline()
        elif not request.fits:
            self._panel.show_error(AIErrorKind.INPUT_TOO_LONG)
        elif not self._privacy_ok:
            self._pending = request
            self._panel.show_privacy()
        else:
            self._start(request)

    def _start(self, request: AIRequest) -> None:
        self._last = request
        worker = self._make_worker(request)
        signals = worker.signals
        signals.waking.connect(self._on_waking)
        signals.finished.connect(self._on_finished)
        signals.failed.connect(self._on_failed)
        self._active = signals
        self._in_flight.add(signals)
        self._panel.show_loading()
        self._pool.start(worker)

    def _make_worker(
        self, request: AIRequest
    ) -> ExplainWordWorker | SimplifyParagraphWorker:
        if request.mode is AIMode.EXPLAIN:
            return ExplainWordWorker(self._client, request.text, request.sentence)
        return SimplifyParagraphWorker(self._client, request.text)

    def _settle(self) -> bool:
        """Forget the sender's request; true when it was the one being waited for."""
        sender = self.sender()
        self._in_flight.discard(sender)
        if sender is self._active:
            self._active = None
            return True
        return False

    @Slot()
    def _on_waking(self) -> None:
        if self.sender() is self._active:
            self._panel.show_waking()

    @Slot(str)
    def _on_finished(self, text: str) -> None:
        if self._settle() and self._last is not None:
            self._answer = text
            self._panel.show_answer(text, self._last.mode)
            self._refresh_counter()

    @Slot(object)
    def _on_failed(self, kind: AIErrorKind) -> None:
        if self._settle():
            self._panel.show_error(kind)
            self._refresh_counter()

    def _refresh_counter(self) -> None:
        self._panel.set_counter(
            self._client.session_calls_used, self._client.session_calls_limit
        )

    def _retry(self) -> None:
        if self._last is not None and not self.busy and self._online:
            self._start(self._last)

    def _explain_current(self) -> None:
        self._act_on_anchor(self._view.explain_at)

    def _simplify_current(self) -> None:
        self._act_on_anchor(self._view.simplify_at)

    def _act_on_anchor(self, action: Callable[[int], None]) -> None:
        anchor = self._view.assistant_anchor()
        if anchor is None:
            self._panel.show_empty()
        else:
            action(anchor)

    def _accept_privacy(self) -> None:
        self._privacy_ok = True
        self.privacy_accepted.emit()
        request, self._pending = self._pending, None
        if request is not None:
            self._start(request)
        else:
            self._panel.show_empty()

    def _decline_privacy(self) -> None:
        self._pending = None
        self._panel.show_empty()

    def _toggle_listen(self) -> None:
        if self._listening:
            self._view.stop_aside()
        elif self._answer:
            self._listening = True
            self._panel.set_listening(True)
            self._view.speak_aside(self._answer)

    def _on_aside_finished(self) -> None:
        self._listening = False
        self._panel.set_listening(False)
