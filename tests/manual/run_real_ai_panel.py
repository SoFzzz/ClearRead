"""Real run of the assistant panel (Day 11) against the deployed backend.

Run from the repo root:

    .\\.venv\\Scripts\\python tests\\manual\\run_real_ai_panel.py DIR

Explains a word and simplifies a paragraph of a synthetic text through the real
BackendAIClient and the real URL in core/config.py, prints each latency measured with
``time.perf_counter()`` and whether "waking" appeared (cold start, BE-NF01), and saves
captures of the panel (answer, error and no network, light and dark) in DIR.

The client token comes from CLEARREAD_CLIENT_TOKEN or, if unset, from the CLIENT_TOKEN
line of backend/.env (git-ignored). It is never printed. Only synthetic text is sent.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clearread.core.config import DEFAULT_BACKEND_URL
from clearread.services.ai_client import BackendAIClient, DiskResponseCache
from clearread.services.syllabifier import SpanishSyllabifier
from clearread.services.text_formatter import TextFormatter
from clearread.services.tts_controller import TTSController
from clearread.ui.ai_assistant import AIAssistant
from clearread.ui.fonts import load_reading_font
from clearread.ui.strings import Language
from clearread.ui.theme import THEMES, ThemeId, build_stylesheet, syllable_palette
from clearread.ui.views.ai_panel import PanelState
from clearread.ui.views.reading_view import ReadingView

ROOT = Path(__file__).resolve().parents[2]
WINDOW_SIZE = (1280, 760)
TIMEOUT_S = 120.0
WORD = "cloroplastos"
UNREACHABLE_URL = "http://127.0.0.1:9"
TEXT = (
    "La fotosíntesis es el proceso que usan las plantas para fabricar su propio "
    "alimento. Con la luz del sol, el agua y el aire, las hojas producen azúcar y "
    "liberan oxígeno.\n\n"
    "Este proceso ocurre dentro de los cloroplastos, unas estructuras pequeñas que "
    "contienen clorofila, el pigmento que da el color verde a las hojas."
)
_TERMINAL = (PanelState.ANSWER, PanelState.ERROR)


def read_client_token() -> str:
    from_env = os.environ.get("CLEARREAD_CLIENT_TOKEN", "").strip()
    if from_env:
        return from_env
    for line in (ROOT / "backend" / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("CLIENT_TOKEN="):
            return line.partition("=")[2].strip().strip("\"'")
    raise SystemExit("No hay CLIENT_TOKEN en el entorno ni en backend/.env")


def build(
    app: QApplication, theme: ThemeId, client: BackendAIClient
) -> tuple[ReadingView, AIAssistant, list[tuple[float, PanelState]]]:
    app.setStyleSheet(build_stylesheet(THEMES[theme]))
    view = ReadingView(TTSController(), theme, Language.ES)
    formatter = TextFormatter(SpanishSyllabifier(), syllable_palette(THEMES[theme]))
    view.load_document(formatter.format_document(TEXT))
    view.resize(*WINDOW_SIZE)
    view.show()
    assistant = AIAssistant(client, view, privacy_accepted=True, parent=view)

    timeline: list[tuple[float, PanelState]] = []
    original = view.ai_panel._set_state

    def logged(state: PanelState) -> None:
        timeline.append((time.perf_counter(), state))
        original(state)

    view.ai_panel._set_state = logged  # type: ignore[method-assign]
    return view, assistant, timeline


def wait_terminal(app: QApplication, view: ReadingView) -> None:
    deadline = time.perf_counter() + TIMEOUT_S
    while view.ai_panel.state not in _TERMINAL and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def measure(app: QApplication, view: ReadingView, label: str, request) -> None:
    panel = view.ai_panel
    started = time.perf_counter()
    request()
    wait_terminal(app, view)
    elapsed = time.perf_counter() - started
    outcome = panel.state.value
    detail = (
        panel.answer_body.text()
        if panel.state is PanelState.ANSWER
        else (panel.error_message.text())
    )
    print(f"{label}: {outcome} in {elapsed:.2f} s | {detail}")


def waking_seen(timeline: list[tuple[float, PanelState]]) -> float | None:
    first = next((t for t, s in timeline if s is PanelState.WAKING), None)
    return None if first is None else first - timeline[0][0]


def save(view: ReadingView, out_dir: Path, name: str) -> None:
    view.ai_panel.repaint()
    QApplication.processEvents()
    path = out_dir / name
    view.grab().save(str(path))
    print(f"saved {path}")


def main() -> int:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    load_reading_font()
    token = read_client_token()
    cache = DiskResponseCache(Path(tempfile.mkdtemp()) / "ai_cache.json")
    client = BackendAIClient(DEFAULT_BACKEND_URL, token, cache, "es")
    print(f"backend: {DEFAULT_BACKEND_URL}")

    view, _, timeline = build(app, ThemeId.LIGHT, client)
    plain = view.editor.toPlainText()
    measure(
        app,
        view,
        "explain word (first request, may be a cold start)",
        lambda: view.explain_at(plain.index(WORD)),
    )
    wake = waking_seen(timeline)
    print(
        "waking notice: "
        + (
            "not shown (service was awake: cold start NOT measured)"
            if wake is None
            else f"shown {wake:.2f} s after the request"
        )
    )
    save(view, out_dir, "panel_ia_respuesta_real_light.png")
    measure(
        app,
        view,
        "simplify paragraph",
        lambda: view.simplify_at(plain.index("La fotos")),
    )
    print(f"session calls: {client.session_calls_used} of {client.session_calls_limit}")

    dark, _, _ = build(app, ThemeId.DARK, client)
    dark.explain_at(dark.editor.toPlainText().index(WORD))
    wait_terminal(app, dark)
    save(dark, out_dir, "panel_ia_respuesta_real_dark.png")

    bad = BackendAIClient(UNREACHABLE_URL, token, cache, "es")
    for theme in (ThemeId.LIGHT, ThemeId.DARK):
        broken, _, _ = build(app, theme, bad)
        measure(
            app,
            broken,
            f"unreachable backend ({theme.value})",
            lambda b=broken: b.explain_at(b.editor.toPlainText().index("proceso")),
        )
        save(broken, out_dir, f"panel_ia_error_real_{theme.value}.png")

        offline, offline_assistant, _ = build(app, theme, client)
        offline.set_assistant_open(True)
        offline_assistant.set_online(False)
        save(offline, out_dir, f"panel_ia_sin_red_real_{theme.value}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
