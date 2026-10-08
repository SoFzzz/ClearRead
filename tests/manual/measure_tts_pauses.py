r"""Real SAPI5 pause measurement (CLAUDE.md sections l and m): it speaks aloud.

    .\.venv\Scripts\python tests\manual\measure_tts_pauses.py

Speaks the same words twice with the real voice: without punctuation (the old script)
and as ``speech_from`` builds it. For each word the time to the next word event is taken
with ``time.perf_counter()``; the difference between the two runs on the same word is
the pause the punctuation added.
"""

import statistics
import sys
import time
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import (
    SyllablePalette,
    TextFormatter,
    speech_from,
)
from clearread.services.tts_controller import TTSController

TEXT = (
    "El niño salió temprano, cogió su mochila, y se fue. Después volvió a casa; "
    "su madre, muy contenta, lo abrazó. ¿Qué hiciste hoy? ¡Aprendí mucho!\n\n"
    "Título de prueba\n\n"
    "El segundo párrafo habla del sol, de la luna, y de las estrellas. Fin del texto."
)
TIMEOUT_S = 90.0


def listen(
    app: QCoreApplication, controller: TTSController, text: str, spans: list | None
) -> list[float]:
    events: dict[int, float] = {}
    controller.word_spoken.connect(lambda i: events.setdefault(i, time.perf_counter()))
    done: list[bool] = []
    controller.playback_ended.connect(lambda: done.append(True))
    controller.speak_text(text, start_offset=0, word_spans=spans)
    deadline = time.perf_counter() + TIMEOUT_S
    while not done and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.002)
    stamps = [events[i] for i in sorted(events)]
    return [b - a for a, b in pairwise(stamps)]


def main() -> None:
    app = QCoreApplication([])
    document = TextFormatter(
        SpanishSyllabifier(), SyllablePalette("#000", "#000")
    ).format_document(TEXT)
    tokens, script = document.token_map, document.tts_script
    controller = TTSController()
    deadline = time.perf_counter() + 30
    while not controller.voices and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    controller.set_speed(150)
    plain = " ".join(t.spoken_text for t in tokens)
    before = listen(app, controller, plain, None)
    speech = speech_from(script, tokens, 0)
    after = listen(app, controller, speech.text, speech.word_spans)
    controller.shutdown()

    groups: dict[str, list[float]] = {
        "between plain words": [],
        "after comma": [],
        "after period": [],
        "after paragraph break": [],
    }
    for index, (gap_before, gap_after) in enumerate(zip(before, after, strict=False)):
        following = script[tokens[index].doc_end_pos : tokens[index + 1].doc_start_pos]
        if "\n" in following:
            key = "after paragraph break"
        elif any(c in following for c in ".!?"):
            key = "after period"
        elif "," in following or ";" in following:
            key = "after comma"
        else:
            key = "between plain words"
        groups[key].append(gap_after)
        print(f"word {index:3d}: {gap_before:5.2f} s -> {gap_after:5.2f} s  [{key}]")
    print()
    for key, values in groups.items():
        if values:
            print(
                f"{key:24s} n={len(values):2d} mean {statistics.mean(values):.2f} s (event-to-event, after)"
            )
    print(
        f"total words {len(tokens)}; events plain {len(before) + 1}, punctuated {len(after) + 1}"
    )


if __name__ == "__main__":
    main()
