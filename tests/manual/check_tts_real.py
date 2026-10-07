"""Real SAPI5 check (CLAUDE.md section m): it speaks aloud, so run it on purpose.

    .\\.venv\\Scripts\\python tests\\manual\\check_tts_real.py

A. Hypothesis of document.md section 8: is a *queued* stop signal delivered while
   ``runAndWait()`` blocks the worker thread? Compared with the direct
   ``engine.stop()`` call the controller uses.
B. Pause in the middle of a paragraph and resume: prints the event stream, the word
   where it paused and the word where it resumed.

Only the synthetic sample text is spoken and printed.
"""

import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT

from clearread.services.tts_controller import (
    SAPI5Worker,
    TTSController,
    create_sapi_engine,
)

LONG_TEXT = " ".join(EXPECTED_TEXT.split())
STOP_AFTER_S = 1.5
PAUSE_AT_WORD = 9
TIMEOUT_S = 40.0


class ProbeWorker(SAPI5Worker):
    """The reference design: stop travels as a queued signal to the worker thread."""

    @Slot()
    def queued_stop(self) -> None:
        if self._engine is not None and self._is_speaking:
            self._engine.stop()


class Probe(QObject):
    sig_speak = Signal(str, int, int)
    sig_stop = Signal()


def pump_until(app: QCoreApplication, condition, timeout_s: float = TIMEOUT_S) -> bool:
    deadline = time.perf_counter() + timeout_s
    while not condition():
        app.processEvents()
        if time.perf_counter() > deadline:
            return False
        time.sleep(0.005)
    return True


def stop_experiment(app: QCoreApplication, mode: str) -> float:
    """Seconds between the stop request and the end of runAndWait()."""
    thread = QThread()
    worker = ProbeWorker(create_sapi_engine)
    worker.moveToThread(thread)
    probe = Probe()
    probe.sig_speak.connect(worker.speak)
    probe.sig_stop.connect(worker.queued_stop)
    state: dict[str, float] = {}
    worker.word_started.connect(
        lambda _g, _i: state.setdefault("first_word", time.perf_counter())
    )
    worker.speech_finished.connect(
        lambda _g: state.setdefault("finished", time.perf_counter())
    )
    thread.started.connect(worker.initialize)
    thread.start()
    worker.cancel(1)  # marks generation 1 as the valid one
    probe.sig_speak.emit(LONG_TEXT, 0, 1)
    pump_until(app, lambda: "first_word" in state)
    time.sleep(STOP_AFTER_S)
    requested = time.perf_counter()
    if mode == "queued":
        probe.sig_stop.emit()
    else:
        worker.cancel(1)
    pump_until(app, lambda: "finished" in state)
    thread.quit()
    thread.wait(3000)
    return state.get("finished", float("nan")) - requested


def pause_resume(app: QCoreApplication) -> None:
    words = LONG_TEXT.split()
    controller = TTSController()
    events: list[tuple[float, int]] = []
    ended: list[float] = []
    started = time.perf_counter()
    controller.word_spoken.connect(
        lambda i: events.append((time.perf_counter() - started, i))
    )
    controller.playback_ended.connect(
        lambda: ended.append(time.perf_counter() - started)
    )

    controller.speak_text(" ".join(words), start_offset=0)
    pump_until(app, lambda: bool(events) and events[-1][1] >= PAUSE_AT_WORD)
    controller.stop()  # pause
    paused_at = time.perf_counter() - started
    last_before_pause = events[-1][1]
    pump_until(app, lambda: False, timeout_s=1.2)  # a silent second: nothing may arrive
    events_during_pause = [e for e in events if e[0] > paused_at + 0.15]

    resume_index = last_before_pause
    resume_mark = len(events)
    controller.speak_text(" ".join(words[resume_index:]), start_offset=resume_index)
    pump_until(app, lambda: bool(ended))
    controller.shutdown()

    after = events[resume_mark:]
    print("\n== B. Pause / resume with the real voice ==")
    print(
        f"paused after the event of word {last_before_pause} ('{words[last_before_pause]}') "
        f"at t={paused_at:.2f}s"
    )
    print(f"events received while paused (must be 0): {len(events_during_pause)}")
    print(f"resumed from word {resume_index} ('{words[resume_index]}')")
    if after:
        print(f"first event after resume: word {after[0][1]} ('{words[after[0][1]]}')")
        print(
            f"last event: word {after[-1][1]} ('{words[after[-1][1]]}'), "
            f"total words {len(words)}"
        )
        consecutive = all(b[1] == a[1] + 1 for a, b in pairwise(after))
        print(f"events after resume are consecutive: {consecutive}")
    print(f"playback_ended signals: {len(ended)}")
    print("event stream (t seconds, word index):")
    print("  " + " ".join(f"{t:.1f}s:{i}" for t, i in events))


def run_scenario(app: QCoreApplication, scenario: str) -> None:
    if scenario == "pause":
        pause_resume(app)
        return
    seconds = stop_experiment(app, scenario)
    label = "queued signal" if scenario == "queued" else "direct engine.stop()"
    print(f"{label} -> speech ended {seconds:.2f} s after the request")


def main() -> int:
    """Each scenario runs in a fresh process: pyttsx3.init() caches the engine per process."""
    if len(sys.argv) > 1:
        run_scenario(QCoreApplication(sys.argv), sys.argv[1])
        return 0
    words = len(LONG_TEXT.split())
    print(
        f"Speaking {words} words with the SAPI5 voice (about {words / 150 * 60:.1f} s at 150 wpm)."
    )
    print("\n== A. Is a queued stop delivered during runAndWait()? ==")
    for scenario in ("queued", "direct", "pause"):
        subprocess.run([sys.executable, "-u", __file__, scenario], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
