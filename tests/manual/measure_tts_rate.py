r"""Real SAPI5 speed measurement (CLAUDE.md sections l and m): it speaks aloud.

    .\.venv\Scripts\python tests\manual\measure_tts_rate.py steps       # one point per SAPI5 step
    .\.venv\Scripts\python tests\manual\measure_tts_rate.py raw         # rate = shown speed (before)
    .\.venv\Scripts\python tests\manual\measure_tts_rate.py calibrated  # sapi_rate_for (after)

Speaks the synthetic sample text for at least 12 s per point and reports the words per
minute actually heard, from the word events and ``time.perf_counter()``. Each point runs
in a fresh process (pyttsx3 caches its engine).
"""

import math
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from samples.make_samples import EXPECTED_TEXT

from clearread.services import tts_controller
from clearread.services.tts_controller import TTSController

POINTS = (80, 120, 150, 200, 280)
SAPI_STEPS = range(-8, 8)
LISTEN_S = 12.0
TIMEOUT_S = 40.0
TEXT = " ".join(EXPECTED_TEXT.split() * 4)
# pyttsx3 2.98 sets SAPI's integer Rate to int(log(rate / A, B)) for voices it does not know.
PYTTSX3_A, PYTTSX3_B = 156.63, 1.11


def rate_inside_step(step: int) -> float:
    """A pyttsx3 rate value that lands in the middle of the SAPI5 integer step."""
    offset = 0.0 if step == 0 else math.copysign(0.5, step)
    return PYTTSX3_A * PYTTSX3_B ** (step + offset)


def speak_and_time(app: QCoreApplication, shown_wpm: int) -> tuple[int, float]:
    controller = TTSController()
    events: list[float] = []
    controller.word_spoken.connect(lambda _i: events.append(time.perf_counter()))
    deadline = time.perf_counter() + TIMEOUT_S
    while not controller.voices and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    controller.set_speed(shown_wpm)
    controller.speak_text(TEXT)
    while time.perf_counter() < deadline:
        app.processEvents()
        if len(events) > 1 and events[-1] - events[0] >= LISTEN_S:
            break
        time.sleep(0.005)
    controller.shutdown()
    return len(events) - 1, events[-1] - events[0]


def run_point(app: QCoreApplication, mode: str, value: int) -> None:
    if mode == "steps":
        # The worker converts the shown speed; here the shown speed is the raw rate.
        tts_controller.sapi_rate_for = lambda _wpm: rate_inside_step(value)  # type: ignore[assignment]
        shown = 0
    elif mode == "raw":
        tts_controller.sapi_rate_for = lambda wpm: wpm  # type: ignore[assignment]
        shown = value
    else:
        shown = value
    words, span = speak_and_time(app, shown)
    heard = words / span * 60
    if mode == "steps":
        print(
            f"{value}\t{rate_inside_step(value):.1f}\t{words}\t{span:.2f}\t{heard:.1f}"
        )
        return
    sent = tts_controller.sapi_rate_for(shown)
    error = (heard - value) / value * 100
    print(f"{value}\t{sent}\t{words}\t{span:.2f}\t{heard:.1f}\t{error:+.1f}%")


def main() -> int:
    if len(sys.argv) > 3:
        run_point(QCoreApplication(sys.argv), sys.argv[1], int(sys.argv[2]))
        return 0
    mode = sys.argv[1] if len(sys.argv) > 1 else "calibrated"
    points = SAPI_STEPS if mode == "steps" else POINTS
    header = (
        "step\trate_sent\twords\tseconds\theard_wpm"
        if mode == "steps"
        else ("shown\trate_sent\twords\tseconds\theard_wpm\terror")
    )
    print(
        f"mode={mode}  text={len(TEXT.split())} synthetic words, listen>={LISTEN_S}s each"
    )
    print(header)
    for point in points:
        subprocess.run(
            [sys.executable, "-u", __file__, mode, str(point), "x"], check=True
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
