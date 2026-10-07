"""Thread-safe SAPI5 TTS controller with an isolated STA COM lifecycle."""

import bisect
import gc
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import pythoncom
import pyttsx3
from PySide6.QtCore import QObject, QThread, Signal, Slot

SPANISH_VOICE = re.compile(r"spanish|espa.ol|helena|sabina|es-es|es-mx", re.IGNORECASE)
DEFAULT_RATE_WPM = 150
MIN_RATE_WPM = 80
MAX_RATE_WPM = 320
# (words per minute heard, rate handed to pyttsx3), one entry per integer SAPI5 step.
# Measured with tests/manual/measure_tts_rate.py on Microsoft Helena; see section 4.5.
# pyttsx3 2.98 turns the rate into SAPI's integer step with int(log(rate / 156.63, 1.11)),
# so each rate below sits inside its step. Another voice speaks at another pace.
_RATE_STEPS: tuple[tuple[float, int], ...] = (
    (68.6, 64),
    (76.5, 72),
    (77.5, 80),
    (86.8, 88),
    (104.7, 98),
    (107.9, 109),
    (122.0, 121),
    (127.3, 134),
    (142.1, 157),
    (164.4, 183),
    (179.3, 203),
    (205.3, 226),
    (227.9, 251),
    (258.6, 278),
    (288.3, 309),
    (306.5, 343),
)
_WORD = re.compile(r"\S+")
_SHUTDOWN_WAIT_MS = 2000


@dataclass(frozen=True)
class VoiceInfo:
    id: str
    name: str

    @property
    def is_spanish(self) -> bool:
        return SPANISH_VOICE.search(self.name) is not None


def sapi_rate_for(displayed_wpm: int) -> int:
    """Rate for pyttsx3 whose measured pace is closest to ``displayed_wpm``.

    The engine's rate is not in words per minute: at 200 it spoke 179 and at 280 only 259.
    """
    return min(_RATE_STEPS, key=lambda step: abs(step[0] - displayed_wpm))[1]


def sort_voices(voices: list[VoiceInfo]) -> list[VoiceInfo]:
    """Spanish voices first, each group in alphabetical order."""
    return sorted(voices, key=lambda voice: (not voice.is_spanish, voice.name.lower()))


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
    voices_listed = Signal(object)  # list[VoiceInfo], Spanish first

    def __init__(self, engine_factory: EngineFactory) -> None:
        super().__init__()
        self._engine_factory = engine_factory
        self._engine: SpeechEngine | None = None
        self._com_initialised = False
        self._is_speaking = False
        self._rate = DEFAULT_RATE_WPM
        self._voice_id = ""  # empty: the first Spanish voice, if any
        self._voices: list[VoiceInfo] = []
        self._valid_generation = 0
        self._active_generation = 0
        self._base_word_index = 0
        self._word_starts: list[int] = []  # char offset of each word in the sent text
        self._pending: tuple[str, int, int] | None = None

    @Slot()
    def initialize(self) -> None:
        """Runs inside the target QThread."""
        try:
            pythoncom.CoInitialize()
            self._com_initialised = True
            self._engine = self._create_engine()
            self.voices_listed.emit(self._voices)
        except Exception:  # noqa: BLE001 - any SAPI/COM failure is reported by kind
            self._engine = None
            self.error_occurred.emit(TTSErrorKind.INIT_FAILED.name)

    def _create_engine(self) -> SpeechEngine:
        engine = self._engine_factory()
        self._voices = self._installed_voices(engine)
        self._select_voice(engine)
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
    def _installed_voices(engine: SpeechEngine) -> list[VoiceInfo]:
        return sort_voices(
            [VoiceInfo(voice.id, voice.name) for voice in engine.getProperty("voices")]
        )

    def _select_voice(self, engine: SpeechEngine) -> None:
        chosen = next((v for v in self._voices if v.id == self._voice_id), None)
        if chosen is None:
            chosen = next((v for v in self._voices if v.is_spanish), None)
        if chosen is not None:
            engine.setProperty("voice", chosen.id)

    @Slot(str)
    def set_voice(self, voice_id: str) -> None:
        """Remember the voice; it is applied when the next utterance starts."""
        self._voice_id = voice_id

    @Slot(str, int, int)
    def speak(self, text: str, start_offset: int, generation: int) -> None:
        if self._is_speaking:
            # pyttsx3's loop pumps Qt events of this thread, so a request made while
            # an utterance is being cancelled arrives nested inside its runAndWait()
            # (Day 8 real check): on the engine being stopped it would end in silence.
            self._pending = (text, start_offset, generation)
            return
        request: tuple[str, int, int] | None = (text, start_offset, generation)
        while request is not None:
            self._speak_now(*request)
            request, self._pending = self._pending, None

    def _speak_now(self, text: str, start_offset: int, generation: int) -> None:
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
            self._select_voice(self._engine)
            self._engine.setProperty("rate", sapi_rate_for(self._rate))
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
    sig_set_voice = Signal(str)

    word_spoken = Signal(int)  # global word index, only for the current utterance
    playback_ended = Signal()  # the current utterance ran to its end
    error_occurred = Signal(str)  # TTSErrorKind name
    voices_listed = Signal(object)  # list[VoiceInfo], Spanish first

    def __init__(self, engine_factory: EngineFactory = create_sapi_engine) -> None:
        super().__init__()
        self._generation = 0
        self.voices: list[VoiceInfo] = []  # filled once the engine is up
        self._thread = QThread()
        self._worker = SAPI5Worker(engine_factory)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.initialize)
        self._thread.finished.connect(self._worker.cleanup)
        self.sig_speak.connect(self._worker.speak)
        self.sig_set_rate.connect(self._worker.set_rate)
        self.sig_set_voice.connect(self._worker.set_voice)
        self._worker.voices_listed.connect(self._on_voices_listed)
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

    def set_voice(self, voice_id: str) -> None:
        self.sig_set_voice.emit(voice_id)

    def shutdown(self) -> None:
        self.stop()
        self._thread.quit()
        self._thread.wait(_SHUTDOWN_WAIT_MS)

    @Slot(object)
    def _on_voices_listed(self, voices: list[VoiceInfo]) -> None:
        self.voices = voices
        self.voices_listed.emit(voices)

    @Slot(int, int)
    def _on_word_started(self, generation: int, word_index: int) -> None:
        if generation == self._generation:
            self.word_spoken.emit(word_index)

    @Slot(int)
    def _on_speech_finished(self, generation: int) -> None:
        if generation == self._generation:
            self.playback_ended.emit()
