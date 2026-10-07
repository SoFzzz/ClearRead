"""Thread-safe SAPI5 TTS controller with an isolated STA COM lifecycle."""

import bisect
import gc
import re
from collections.abc import Callable
from enum import Enum
from typing import Any, Protocol

import pythoncom
import pyttsx3
from PySide6.QtCore import QObject, QThread, Signal, Slot

SPANISH_VOICE = re.compile(r"spanish|espa.ol|helena|sabina|es-es|es-mx", re.IGNORECASE)
DEFAULT_RATE_WPM = 150
MIN_RATE_WPM = 80
MAX_RATE_WPM = 320
_WORD = re.compile(r"\S+")
_SHUTDOWN_WAIT_MS = 2000


class TTSErrorKind(Enum):
    """Failure categories; the UI translates them through ``strings.py``."""

    INIT_FAILED = "init_failed"
    PLAYBACK_FAILED = "playback_failed"


class SpeechEngine(Protocol):
    """The subset of ``pyttsx3.Engine`` this module relies on."""

    def say(self, text: str, name: str | None = None) -> None: ...

    def runAndWait(self) -> None: ...

    def stop(self) -> None: ...

    def connect(self, topic: str, cb: Callable[..., None]) -> Any: ...

    def getProperty(self, name: str) -> Any: ...

    def setProperty(self, name: str, value: Any) -> None: ...


EngineFactory = Callable[[], SpeechEngine]


def create_sapi_engine() -> SpeechEngine:
    return pyttsx3.init("sapi5")


class SAPI5Worker(QObject):
    """Lives inside a dedicated QThread; owns the engine and its COM apartment.

    Every signal carries the generation of the utterance it belongs to, so the
    controller can drop events of an utterance that was already cancelled.
    """

    word_started = Signal(int, int)  # generation, global word index
    speech_finished = Signal(int)  # generation
    error_occurred = Signal(str)  # TTSErrorKind name

    def __init__(self, engine_factory: EngineFactory) -> None:
        super().__init__()
        self._engine_factory = engine_factory
        self._engine: SpeechEngine | None = None
        self._com_initialised = False
        self._is_speaking = False
        self._rate = DEFAULT_RATE_WPM
        self._valid_generation = 0
        self._active_generation = 0
        self._base_word_index = 0
        self._word_starts: list[int] = []  # char offset of each word in the sent text

    @Slot()
    def initialize(self) -> None:
        """Runs inside the target QThread."""
        try:
            pythoncom.CoInitialize()
            self._com_initialised = True
            self._engine = self._create_engine()
        except Exception:  # noqa: BLE001 - any SAPI/COM failure is reported by kind
            self._engine = None
            self.error_occurred.emit(TTSErrorKind.INIT_FAILED.name)

    def _create_engine(self) -> SpeechEngine:
        engine = self._engine_factory()
        self._select_spanish_voice(engine)
        engine.setProperty("volume", 1.0)
        engine.connect("started-word", self._on_word_boundary)
        return engine

    def _replace_engine(self) -> None:
        """Build a fresh engine after an interrupted utterance.

        Day 5 real check: after ``engine.stop()`` pyttsx3 2.98 swallows the next
        utterance (SAPI delivers the end-of-stream of the purge request during it, so
        ``runAndWait()`` returns at once and nothing is spoken). A new engine takes
        about 0.1 s and speaks normally.
        """
        self._engine = None
        gc.collect()  # pyttsx3 caches engines weakly: the old one must really be gone
        try:
            self._engine = self._create_engine()
        except Exception:  # noqa: BLE001 - any SAPI/COM failure is reported by kind
            self.error_occurred.emit(TTSErrorKind.INIT_FAILED.name)

    @staticmethod
    def _select_spanish_voice(engine: SpeechEngine) -> None:
        for voice in engine.getProperty("voices"):
            if SPANISH_VOICE.search(voice.name):
                engine.setProperty("voice", voice.id)
                return

    @Slot(str, int, int)
    def speak(self, text: str, start_offset: int, generation: int) -> None:
        if generation != self._valid_generation:
            return  # cancelled while still queued behind another utterance
        if self._engine is None:
            self.error_occurred.emit(TTSErrorKind.INIT_FAILED.name)
            self.speech_finished.emit(generation)
            return
        self._active_generation = generation
        self._base_word_index = start_offset
        self._word_starts = [match.start() for match in _WORD.finditer(text)]
        self._is_speaking = True
        try:
            self._engine.setProperty("rate", self._rate)
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception:  # noqa: BLE001 - any engine failure is reported by kind
            self.error_occurred.emit(TTSErrorKind.PLAYBACK_FAILED.name)
        finally:
            self._is_speaking = False
            if generation != self._valid_generation:
                self._replace_engine()
            self.speech_finished.emit(generation)

    def cancel(self, current_generation: int) -> None:
        """Stop the voice now. Called directly from the GUI thread.

        A queued ``sig_stop`` is not delivered while ``runAndWait()`` blocks this
        thread, but ``engine.stop()`` is safe across threads (Day 1 spike, and the
        Day 5 real check), so the controller bypasses the queue.
        """
        self._valid_generation = current_generation
        engine = self._engine
        if engine is not None and self._is_speaking:
            engine.stop()

    @Slot(int)
    def set_rate(self, wpm: int) -> None:
        self._rate = max(MIN_RATE_WPM, min(MAX_RATE_WPM, wpm))

    def _on_word_boundary(self, name: str | None, location: int, length: int) -> None:
        # pyttsx3 calls this with keyword arguments (name=, location=, length=), so the
        # parameter names must match. It also reports the stream start as a "started-word"
        # with name=None and location=stream number; only real word events carry a char
        # offset (Day 1 spike). say() is called without a name: with one, the stream-start
        # event would carry it instead of None.
        if name is None:
            return
        local_index = bisect.bisect_right(self._word_starts, location) - 1
        if local_index >= 0:
            self.word_started.emit(
                self._active_generation, self._base_word_index + local_index
            )

    @Slot()
    def cleanup(self) -> None:
        if self._engine is not None and self._is_speaking:
            self._engine.stop()
        if self._com_initialised:
            pythoncom.CoUninitialize()
            self._com_initialised = False


class TTSController(QObject):
    """Public interface for thread-safe speech: GUI thread only."""

    sig_speak = Signal(str, int, int)
    sig_set_rate = Signal(int)

    word_spoken = Signal(int)  # global word index, only for the current utterance
    playback_ended = Signal()  # the current utterance ran to its end
    error_occurred = Signal(str)  # TTSErrorKind name

    def __init__(self, engine_factory: EngineFactory = create_sapi_engine) -> None:
        super().__init__()
        self._generation = 0
        self._thread = QThread()
        self._worker = SAPI5Worker(engine_factory)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.initialize)
        self._thread.finished.connect(self._worker.cleanup)
        self.sig_speak.connect(self._worker.speak)
        self.sig_set_rate.connect(self._worker.set_rate)
        self._worker.word_started.connect(self._on_word_started)
        self._worker.speech_finished.connect(self._on_speech_finished)
        self._worker.error_occurred.connect(self.error_occurred)

        self._thread.start()

    def speak_text(self, text: str, start_offset: int = 0) -> None:
        """Speak ``text``; its first word is word ``start_offset`` of the document."""
        self.stop()
        self.sig_speak.emit(text, start_offset, self._generation)

    def stop(self) -> None:
        self._generation += 1
        self._worker.cancel(self._generation)

    def set_speed(self, wpm: int) -> None:
        self.sig_set_rate.emit(wpm)

    def shutdown(self) -> None:
        self.stop()
        self._thread.quit()
        self._thread.wait(_SHUTDOWN_WAIT_MS)

    @Slot(int, int)
    def _on_word_started(self, generation: int, word_index: int) -> None:
        if generation == self._generation:
            self.word_spoken.emit(word_index)

    @Slot(int)
    def _on_speech_finished(self, generation: int) -> None:
        if generation == self._generation:
            self.playback_ended.emit()
