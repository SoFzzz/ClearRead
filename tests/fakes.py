"""A speech engine double that behaves like pyttsx3's SAPI5 engine, minus the sound.

It reproduces what the controller depends on (Day 1 spike and Day 5 real check):
an extra "started-word" event with name=None at the start of every utterance,
``runAndWait()`` blocking its thread (while still processing its Qt events) until the
text is spoken or ``stop()`` is called from another thread, and an engine that stays silent after a ``stop()`` in
the middle of speech (only a new engine speaks again).
"""

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QCoreApplication

WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class FakeVoice:
    id: str
    name: str


class VoiceCounter:
    """How many engines speak at once: two voices overlapping would make the peak 2."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    def leave(self) -> None:
        with self._lock:
            self.active -= 1


class FakeEngine:
    def __init__(
        self, word_delay_s: float = 0.0, voices: VoiceCounter | None = None
    ) -> None:
        self.word_delay_s = word_delay_s
        self._voices_speaking = voices
        self.properties: dict[str, Any] = {}
        self.said: list[str] = []
        self.runs = 0
        self._text = ""
        self._callback: Callable[..., None] | None = None
        self._stop = threading.Event()
        self._speaking = False
        self._poisoned = False
        self._voices = [
            FakeVoice("en-1", "Microsoft David Desktop - English (United States)"),
            FakeVoice("es-1", "Microsoft Helena Desktop - Spanish (Spain)"),
        ]

    def say(self, text: str, name: str | None = None) -> None:
        self._text = text
        self.said.append(text)

    def connect(self, topic: str, cb: Callable[..., None]) -> None:
        assert topic == "started-word"
        self._callback = cb

    def getProperty(self, name: str) -> Any:
        return self._voices if name == "voices" else self.properties.get(name)

    def setProperty(self, name: str, value: Any) -> None:
        self.properties[name] = value

    def stop(self) -> None:
        if self._speaking:
            self._poisoned = True
        self._stop.set()

    def runAndWait(self) -> None:
        self.runs += 1
        self._stop.clear()
        assert self._callback is not None
        # pyttsx3 calls its callbacks with keyword arguments.
        self._callback(name=None, location=self.runs, length=0)  # stream start
        if self._poisoned:
            return
        self._speaking = True
        if self._voices_speaking:
            self._voices_speaking.enter()
        try:
            self._speak_words(self._callback)
        finally:
            self._speaking = False
            if self._voices_speaking:
                self._voices_speaking.leave()

    def _speak_words(self, callback: Callable[..., None]) -> None:
        for match in WORD.finditer(self._text):
            if self._stop.is_set():
                self._wind_down()
                return
            callback(
                name=match.group(), location=match.start(), length=len(match.group())
            )
            # Like pyttsx3's loop, which pumps the Windows messages (and with them the
            # Qt events) of the thread that is speaking (Day 5 and Day 8 real checks).
            QCoreApplication.processEvents()
            if self.word_delay_s:
                time.sleep(self.word_delay_s)

    def _wind_down(self) -> None:
        # SAPI takes a moment to report a purged utterance as done (0.76 s measured on
        # Day 5) and pyttsx3 keeps pumping the thread's Qt events meanwhile.
        time.sleep(0.02)
        QCoreApplication.processEvents()


class EngineSource:
    """Engine factory for the controller; like pyttsx3.init(), each call can give a new engine."""

    def __init__(self, word_delay_s: float = 0.0) -> None:
        self.word_delay_s = word_delay_s
        self.created: list[FakeEngine] = []
        self.voices = VoiceCounter()

    def __call__(self) -> FakeEngine:
        engine = FakeEngine(self.word_delay_s, self.voices)
        self.created.append(engine)
        return engine

    @property
    def latest(self) -> FakeEngine:
        return self.created[-1]
