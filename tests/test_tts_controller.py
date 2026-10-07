"""TTSController with a fake engine: threading, event alignment, cancellation.

The real SAPI5 voice is exercised by tests/manual/check_tts_real.py (CLAUDE.md
section m: mocks alone are not enough for a COM/SAPI failure).
"""

from collections.abc import Iterator

import pytest
from fakes import EngineSource, FakeEngine
from pytestqt.qtbot import QtBot

from clearread.services.tts_controller import (
    MAX_RATE_WPM,
    TTSController,
    TTSErrorKind,
)

TIMEOUT_MS = 5000


@pytest.fixture
def engines() -> EngineSource:
    return EngineSource()


@pytest.fixture
def controller(engines: EngineSource, qtbot: QtBot) -> Iterator[TTSController]:
    tts = TTSController(engine_factory=engines)
    yield tts
    tts.shutdown()


@pytest.fixture
def slow_controller(qtbot: QtBot) -> Iterator[tuple[TTSController, EngineSource]]:
    source = EngineSource(word_delay_s=0.05)
    tts = TTSController(engine_factory=source)
    yield tts, source
    tts.shutdown()


def collect_words(tts: TTSController) -> list[int]:
    words: list[int] = []
    tts.word_spoken.connect(words.append)
    return words


def test_events_are_aligned_by_char_offset_and_the_stream_event_is_ignored(
    controller: TTSController, qtbot: QtBot
) -> None:
    words = collect_words(controller)
    with qtbot.waitSignal(controller.playback_ended, timeout=TIMEOUT_MS):
        controller.speak_text("uno dos tres", start_offset=5)
    assert words == [5, 6, 7]


def test_start_offset_zero_starts_at_the_first_word(
    controller: TTSController, qtbot: QtBot
) -> None:
    words = collect_words(controller)
    with qtbot.waitSignal(controller.playback_ended, timeout=TIMEOUT_MS):
        controller.speak_text("uno dos")
    assert words == [0, 1]


def test_spanish_voice_is_selected_and_volume_set(
    controller: TTSController, engines: EngineSource, qtbot: QtBot
) -> None:
    with qtbot.waitSignal(controller.playback_ended, timeout=TIMEOUT_MS):
        controller.speak_text("hola")
    assert engines.latest.properties["voice"] == "es-1"
    assert engines.latest.properties["volume"] == 1.0


def test_speed_is_clamped_and_applied_to_the_next_utterance(
    controller: TTSController, engines: EngineSource, qtbot: QtBot
) -> None:
    controller.set_speed(1000)
    with qtbot.waitSignal(controller.playback_ended, timeout=TIMEOUT_MS):
        controller.speak_text("hola")
    assert engines.latest.properties["rate"] == MAX_RATE_WPM


def test_stop_cancels_a_running_utterance_without_a_late_end_signal(
    slow_controller: tuple[TTSController, EngineSource], qtbot: QtBot
) -> None:
    tts, _ = slow_controller
    words = collect_words(tts)
    ended: list[bool] = []
    tts.playback_ended.connect(lambda: ended.append(True))
    tts.speak_text(" ".join(["palabra"] * 40))
    qtbot.waitUntil(lambda: len(words) >= 2, timeout=TIMEOUT_MS)
    tts.stop()
    spoken_at_stop = len(words)
    qtbot.wait(400)  # the worker returns from runAndWait and emits its stale signals
    assert len(words) <= spoken_at_stop + 1
    assert ended == []


def test_stop_reaches_the_engine_while_run_and_wait_blocks_the_worker_thread(
    qtbot: QtBot,
) -> None:
    source = EngineSource(word_delay_s=0.2)
    tts = TTSController(engine_factory=source)
    words = collect_words(tts)
    try:
        tts.speak_text(" ".join(["palabra"] * 50))  # about 10 s if left alone
        qtbot.waitUntil(lambda: len(words) >= 1, timeout=TIMEOUT_MS)
        tts.stop()
        tts.speak_text("fin", start_offset=100)  # runs once the worker is free again
        qtbot.waitUntil(lambda: 100 in words, timeout=3000)
    finally:
        tts.shutdown()


def test_a_queued_utterance_is_dropped_when_stopped_before_it_starts(
    qtbot: QtBot,
) -> None:
    source = EngineSource(word_delay_s=0.1)
    tts = TTSController(engine_factory=source)
    words = collect_words(tts)
    try:
        tts.speak_text(" ".join(["primera"] * 30))
        qtbot.waitUntil(lambda: len(words) >= 1, timeout=TIMEOUT_MS)
        tts.speak_text("segunda", start_offset=200)  # queued behind the first
        tts.stop()  # cancels the first and invalidates the second
        qtbot.wait(500)
        assert 200 not in words
    finally:
        tts.shutdown()


def test_resuming_speaks_only_the_new_utterance_events(
    slow_controller: tuple[TTSController, EngineSource], qtbot: QtBot
) -> None:
    tts, _ = slow_controller
    words = collect_words(tts)
    tts.speak_text("a b c d e f g h", start_offset=0)
    qtbot.waitUntil(lambda: len(words) >= 3, timeout=TIMEOUT_MS)
    tts.stop()
    resume_from = words[-1]
    words.clear()
    with qtbot.waitSignal(tts.playback_ended, timeout=TIMEOUT_MS):
        tts.speak_text("d e f g h", start_offset=3)
    assert words[0] >= 3 and words[-1] == 7
    assert resume_from in (2, 3)


def test_a_new_engine_is_built_after_an_interrupted_utterance(
    slow_controller: tuple[TTSController, EngineSource], qtbot: QtBot
) -> None:
    """Real pyttsx3 2.98 is silent after stop() mid-speech; the fake reproduces that."""
    tts, source = slow_controller
    words = collect_words(tts)
    tts.speak_text("a b c d e f g h", start_offset=0)
    qtbot.waitUntil(lambda: len(words) >= 2, timeout=TIMEOUT_MS)
    tts.stop()
    qtbot.waitUntil(lambda: len(source.created) == 2, timeout=TIMEOUT_MS)
    words.clear()
    with qtbot.waitSignal(tts.playback_ended, timeout=TIMEOUT_MS):
        tts.speak_text("c d e", start_offset=2)
    assert words == [2, 3, 4]
    assert source.latest.said == ["c d e"]


def test_the_fake_engine_really_is_silent_after_stop_without_a_new_engine(
    qtbot: QtBot,
) -> None:
    """Guards the guard: if the fake stopped modelling the quirk, the test above is moot."""
    engine = FakeEngine(word_delay_s=0.05)
    tts = TTSController(engine_factory=lambda: engine)  # always the same engine
    words = collect_words(tts)
    try:
        tts.speak_text("a b c d e f g h")
        qtbot.waitUntil(lambda: len(words) >= 2, timeout=TIMEOUT_MS)
        tts.stop()
        qtbot.wait(300)
        words.clear()
        with qtbot.waitSignal(tts.playback_ended, timeout=TIMEOUT_MS):
            tts.speak_text("c d e", start_offset=2)
        assert words == []
    finally:
        tts.shutdown()


def test_no_engine_is_rebuilt_when_speech_ends_normally(
    controller: TTSController, engines: EngineSource, qtbot: QtBot
) -> None:
    with qtbot.waitSignal(controller.playback_ended, timeout=TIMEOUT_MS):
        controller.speak_text("uno dos")
    assert len(engines.created) == 1


def test_engine_init_failure_is_reported_by_kind(qtbot: QtBot) -> None:
    def broken_factory() -> FakeEngine:
        raise OSError("no SAPI")

    tts = TTSController(engine_factory=broken_factory)
    try:
        with qtbot.waitSignal(tts.error_occurred, timeout=TIMEOUT_MS) as blocker:
            pass
        assert blocker.args == [TTSErrorKind.INIT_FAILED.name]
        with qtbot.waitSignal(tts.error_occurred, timeout=TIMEOUT_MS) as blocker:
            tts.speak_text("hola")
        assert blocker.args == [TTSErrorKind.INIT_FAILED.name]
    finally:
        tts.shutdown()
