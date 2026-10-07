"""Streaming ingestion and OCR on a background thread (§4.7)."""

import threading
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum

import numpy as np
from PySide6.QtCore import QThread, Signal

from clearread.services.ingestor import (
    DocumentIngestor,
    DocumentType,
    PasswordProtectedError,
    UnsupportedFormatError,
)
from clearread.services.ocr_engine import OCREngine
from clearread.services.preprocessor import OCRPreprocessor
from clearread.services.text_formatter import FormattedDocument, TextFormatter


class NoTextRecognizedError(ValueError):
    """No page produced any text."""


class ProcessingErrorKind(Enum):
    """The value is the middle part of the ``error.<value>.*`` catalog keys."""

    PASSWORD = "password"
    UNSUPPORTED_FORMAT = "unsupported_format"
    FILE_NOT_FOUND = "file_not_found"
    NO_TEXT = "no_text"
    UNREADABLE = "unreadable"


def classify_error(error: Exception) -> ProcessingErrorKind:
    if isinstance(error, PasswordProtectedError):
        return ProcessingErrorKind.PASSWORD
    if isinstance(error, UnsupportedFormatError):
        return ProcessingErrorKind.UNSUPPORTED_FORMAT
    if isinstance(error, FileNotFoundError):
        return ProcessingErrorKind.FILE_NOT_FOUND
    if isinstance(error, NoTextRecognizedError):
        return ProcessingErrorKind.NO_TEXT
    return ProcessingErrorKind.UNREADABLE


@dataclass(frozen=True)
class ProcessedDocument:
    raw_text: str
    formatted: FormattedDocument
    page_count: int
    is_photo: bool


class DocumentProcessWorker(QThread):
    progress_changed = Signal(int, int)  # page being read, total pages
    formatting_started = Signal()
    document_ready = Signal(object)  # ProcessedDocument
    error_occurred = Signal(str)  # ProcessingErrorKind.value

    def __init__(
        self,
        file_path: str,
        ingestor: DocumentIngestor,
        preprocessor: OCRPreprocessor,
        ocr_engine: OCREngine,
        formatter: TextFormatter,
    ) -> None:
        super().__init__()
        self._file_path = file_path
        self._ingestor = ingestor
        self._preprocessor = preprocessor
        self._ocr_engine = ocr_engine
        self._formatter = formatter
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            processed = self._process()
        except Exception as error:  # noqa: BLE001 - any failure must reach the UI as a kind
            if not self._cancelled.is_set():
                self.error_occurred.emit(classify_error(error).value)
            return
        if processed is not None:
            self.document_ready.emit(processed)

    def _process(self) -> ProcessedDocument | None:
        total_pages = self._ingestor.get_page_count(self._file_path)
        pages = self._ingestor.load(self._file_path)
        texts: list[str] = []
        is_photo = False
        try:
            for page in pages:
                if self._cancelled.is_set():
                    return None
                self.progress_changed.emit(page.page_number, total_pages)
                is_photo = page.source_type is DocumentType.IMAGE
                text = page.digital_text or self._recognise(page.image, is_photo)
                if text.strip():
                    texts.append(text.strip())
        finally:
            if isinstance(pages, Generator):
                pages.close()
        if self._cancelled.is_set():
            return None
        if not texts:
            raise NoTextRecognizedError(self._file_path)
        self.formatting_started.emit()
        raw_text = "\n\n".join(texts)
        return ProcessedDocument(
            raw_text, self._formatter.format_document(raw_text), total_pages, is_photo
        )

    def _recognise(self, image: np.ndarray, is_photo: bool) -> str:
        clean = self._preprocessor.process(image, is_camera_photo=is_photo)
        return self._ocr_engine.process_image(clean).raw_text
