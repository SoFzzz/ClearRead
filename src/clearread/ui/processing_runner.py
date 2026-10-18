"""Owns the background worker that turns a file into a formatted document."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clearread.services.ingestor import DocumentIngestor
from clearread.services.ocr_engine import OCREngine
from clearread.services.preprocessor import OCRPreprocessor
from clearread.services.text_formatter import TextFormatter
from clearread.ui.views.home_view import ProcessingView
from clearread.workers.ocr_worker import (
    DocumentProcessWorker,
    ProcessedDocument,
    ProcessingErrorKind,
)


@dataclass(frozen=True)
class PendingDocument:
    source: Path
    key: str
    folder_id: str  # folder selected on Home when the document was chosen


class ProcessingRunner:
    def __init__(
        self,
        processing_view: ProcessingView,
        ingestor: DocumentIngestor,
        preprocessor: OCRPreprocessor,
        ocr_engine: OCREngine,
        on_ready: Callable[[ProcessedDocument, PendingDocument], None],
        on_error: Callable[[ProcessingErrorKind], None],
    ) -> None:
        self._view = processing_view
        self._ingestor = ingestor
        self._preprocessor = preprocessor
        self._ocr_engine = ocr_engine
        self._on_ready = on_ready
        self._on_error = on_error
        self.worker: DocumentProcessWorker | None = None
        self.retired_workers: set[DocumentProcessWorker] = set()
        self._pending: PendingDocument | None = None

    def start(
        self,
        pending: PendingDocument,
        formatter: TextFormatter,
        syllables_enabled: bool,
        show_processing: Callable[[], None],
    ) -> None:
        """``show_processing`` runs before the thread starts, so no signal beats the screen."""
        worker = DocumentProcessWorker(
            str(pending.source),
            self._ingestor,
            self._preprocessor,
            self._ocr_engine,
            formatter,
            syllables_enabled,
        )
        worker.progress_changed.connect(self._view.set_progress)
        worker.formatting_started.connect(self._view.set_preparing)
        worker.document_ready.connect(self._on_document_ready)
        worker.error_occurred.connect(self._on_worker_error)
        worker.finished.connect(lambda: self._on_worker_finished(worker))
        self._pending = pending
        self.worker = worker
        self._view.start(pending.source.name)
        show_processing()
        worker.start()

    def cancel(self) -> bool:
        """Stop the current worker; False when there was none."""
        worker = self.worker
        if worker is None:
            return False
        worker.cancel()
        self._detach(worker)
        return True

    def shutdown(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self._detach(self.worker)
        for worker in list(self.retired_workers):
            worker.wait()

    def _detach(self, worker: DocumentProcessWorker) -> None:
        for signal in (
            worker.progress_changed,
            worker.formatting_started,
            worker.document_ready,
            worker.error_occurred,
        ):
            signal.disconnect()
        self.retired_workers.add(worker)
        self.worker = None
        self._pending = None

    def _release_worker(self) -> PendingDocument | None:
        """Stop tracking the finished worker as current but keep it joinable on close."""
        if self.worker is not None:
            self.retired_workers.add(self.worker)
            self.worker = None
        pending, self._pending = self._pending, None
        return pending

    def _on_worker_finished(self, worker: DocumentProcessWorker) -> None:
        self.retired_workers.discard(worker)
        if self.worker is worker:
            self.worker = None
        worker.deleteLater()

    def _on_document_ready(self, processed: ProcessedDocument) -> None:
        pending = self._release_worker()
        if pending is not None:
            self._on_ready(processed, pending)

    def _on_worker_error(self, kind_value: str) -> None:
        if self._release_worker() is not None:
            self._on_error(ProcessingErrorKind(kind_value))
