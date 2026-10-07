"""A speech engine double that behaves like pyttsx3's SAPI5 engine, minus the sound.

It reproduces what the controller depends on (Day 1 spike and Day 5 real check):
an extra "started-word" event with name=None at the start of every utterance,
``runAndWait()`` blocking its thread until the text is spoken or ``stop()`` is
called from another thread, and an engine that stays silent after a ``stop()`` in
the middle of speech (only a new engine speaks again).
"""

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class FakeVoice:
    id: str
    name: str


class FakeEngine:
    def __init__(self, word_delay_s: float = 0.0) -> None:
        self.word_delay_s = word_delay_s
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
        try:
            self._speak_words(self._callback)
        finally:
            self._speaking = False

    def _speak_words(self, callback: Callable[..., None]) -> None:
        for match in WORD.finditer(self._text):
            if self._stop.is_set():
                return
            callback(
                name=match.group(), location=match.start(), length=len(match.group())
            )
            if self.word_delay_s:
                time.sleep(self.word_delay_s)


class EngineSource:
    """Engine factory for the controller; like pyttsx3.init(), each call can give a new engine."""

    def __init__(self, word_delay_s: float = 0.0) -> None:
        self.word_delay_s = word_delay_s
        self.created: list[FakeEngine] = []

    def __call__(self) -> FakeEngine:
        engine = FakeEngine(self.word_delay_s)
        self.created.append(engine)
        return engine

    @property
    def latest(self) -> FakeEngine:
        return self.created[-1]
