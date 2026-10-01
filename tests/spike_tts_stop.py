"""Day 1 spike (§8 risk): can engine.stop() from another thread interrupt runAndWait()?

Each scenario runs in a fresh process with a fresh engine, because a previous
utterance or stop() leaves pyttsx3 state behind that skews the next measurement.

Scenarios:
- full:         one utterance, no stop (baseline duration)
- repeat:       two utterances on the same engine (does the second one speak?)
- stop-nocom:   stop() from a second thread without COM initialisation
- stop-com:     stop() from a second thread after pythoncom.CoInitialize()

Usage: python tests/spike_tts_stop.py            (runs all scenarios)
       python tests/spike_tts_stop.py <scenario>
"""

import subprocess
import sys
import threading
import time
from importlib.metadata import version

import pythoncom
import pyttsx3

LONG_TEXT = (
    "Esta es una prueba larga de lectura en voz alta para comprobar si la síntesis "
    "se detiene cuando otro hilo llama a la función de parada mientras el motor "
    "sigue hablando sin interrupción durante varios segundos seguidos."
)
STOP_AFTER_S = 1.5
SCENARIOS = ("full", "repeat", "stop-nocom", "stop-com")
SAPI_RUNNING_STATES = {1: "done", 2: "speaking"}


def make_engine(words: list[int]) -> pyttsx3.Engine:
    engine = pyttsx3.init("sapi5")
    spanish = [v for v in engine.getProperty("voices") if "spanish" in v.name.lower()]
    if spanish:
        engine.setProperty("voice", spanish[0].id)
    engine.connect(
        "started-word", lambda name, location, length: words.append(location)
    )
    return engine


def speak_and_time(engine: pyttsx3.Engine) -> float:
    t_start = time.perf_counter()
    engine.say(LONG_TEXT)
    engine.runAndWait()
    return time.perf_counter() - t_start


def stopper(engine: pyttsx3.Engine, init_com: bool, outcome: dict[str, str]) -> None:
    time.sleep(STOP_AFTER_S)
    if init_com:
        pythoncom.CoInitialize()
    try:
        engine.stop()
        outcome["stop"] = "stop() returned without exception"
    except Exception as exc:  # noqa: BLE001 - the spike reports whatever happens
        outcome["stop"] = f"stop() raised {type(exc).__name__}: {exc}"
    finally:
        if init_com:
            pythoncom.CoUninitialize()


def run_scenario(name: str) -> str:
    words: list[int] = []
    engine = make_engine(words)
    if name == "full":
        return f"{speak_and_time(engine):.2f} s, {len(words)} word events"
    if name == "repeat":
        first = speak_and_time(engine)
        first_words = len(words)
        words.clear()
        second = speak_and_time(engine)
        return (
            f"1st {first:.2f} s / {first_words} events, "
            f"2nd {second:.2f} s / {len(words)} events"
        )
    outcome: dict[str, str] = {}
    thread = threading.Thread(
        target=stopper, args=(engine, name == "stop-com", outcome)
    )
    thread.start()
    elapsed = speak_and_time(engine)
    thread.join()
    # Private attribute: the spike needs SAPI's own state to prove audio stopped.
    state = engine.proxy._driver._tts.Status.RunningState
    return (
        f"runAndWait returned after {elapsed:.2f} s (stop requested at "
        f"{STOP_AFTER_S:.1f} s), {len(words)} word events, SAPI state "
        f"{SAPI_RUNNING_STATES.get(state, state)} | {outcome.get('stop')}"
    )


def main(args: list[str]) -> None:
    if args:
        pythoncom.CoInitialize()
        try:
            print(f"{args[0]:<11} {run_scenario(args[0])}")
        finally:
            pythoncom.CoUninitialize()
        return
    print(f"pyttsx3 {version('pyttsx3')}", flush=True)
    for scenario in SCENARIOS:
        subprocess.run([sys.executable, __file__, scenario], check=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
