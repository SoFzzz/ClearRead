"""Day 1 spike (§6.4): ingestion -> RapidOCR inference -> SAPI5 speech.

Validates the dependency chain both in the venv and as a PyInstaller .exe.
It deliberately calls RapidOCR directly: ClearReadOCR is a Day 3 deliverable.

Usage: python tests/spike_pipeline.py [samples_dir]   (default: tests/samples)
Exit code 0 only if every step passes.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pythoncom
import pyttsx3
from rapidocr_onnxruntime import RapidOCR

RENDER_DPI = 300
SPANISH_SPECIAL_CHARS = set("áéíóúüñ¿¡")
SPANISH_VOICE_HINTS = ("spanish", "español", "helena", "sabina", "es-es", "es-mx")
TTS_PHRASE = "Prueba de integración exitosa"


def render_first_page(pdf_path: Path) -> tuple[np.ndarray, str]:
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        page = doc[0]
        text = page.get_textpage().get_text_range().strip()
        image = np.array(page.render(scale=RENDER_DPI / 72).to_pil().convert("RGB"))
    finally:
        doc.close()
    return image, text


def step_ingest(samples_dir: Path) -> np.ndarray:
    print("[1/3] Ingesta con pypdfium2...")
    _, digital_text = render_first_page(samples_dir / "sample_page_digital.pdf")
    assert len(digital_text) > 50, "El PDF digital no tiene capa de texto"
    print(f" -> PDF digital: {len(digital_text)} caracteres de texto nativo")
    print(f" -> Texto nativo: {digital_text!r}")

    scanned_image, scanned_text = render_first_page(
        samples_dir / "sample_page_scanned.pdf"
    )
    assert scanned_image.shape[0] > 0, "Fallo al renderizar la página escaneada"
    assert not scanned_text, "El PDF escaneado no debería tener capa de texto"
    print(f" -> PDF escaneado: sin texto nativo, imagen {scanned_image.shape}")
    return scanned_image


def step_ocr(image: np.ndarray) -> None:
    print("[2/3] OCR con RapidOCR (ONNX Runtime)...")
    t_init = time.perf_counter()
    engine = RapidOCR()
    init_ms = (time.perf_counter() - t_init) * 1000
    t_ocr = time.perf_counter()
    result, _ = engine(image)
    ocr_ms = (time.perf_counter() - t_ocr) * 1000
    assert result, "OCR no produjo texto"
    lines = [text for _box, text, _score in result]
    text = "\n".join(lines)
    found = sorted(SPANISH_SPECIAL_CHARS & set(text))
    print(
        f" -> Inicialización: {init_ms:.0f} ms | Inferencia: {ocr_ms:.0f} ms (perf_counter)"
    )
    for _box, line, score in result:
        print(f"    {score:.2f}  {line}")
    print(f" -> Caracteres especiales reconocidos: {''.join(found) or 'ninguno'}")


def step_tts() -> None:
    print("[3/3] Síntesis SAPI5 con COM STA...")
    pythoncom.CoInitialize()
    try:
        engine = pyttsx3.init("sapi5")
        voices = engine.getProperty("voices")
        spanish = [
            v for v in voices if any(h in v.name.lower() for h in SPANISH_VOICE_HINTS)
        ]
        if spanish:
            engine.setProperty("voice", spanish[0].id)
        print(f" -> Voces instaladas: {[v.name for v in voices]}")
        print(
            f" -> Voz usada: {spanish[0].name if spanish else 'por defecto (sin voz española)'}"
        )
        word_events: list[int] = []
        engine.connect(
            "started-word", lambda name, location, length: word_events.append(location)
        )
        t_start = time.perf_counter()
        engine.say(TTS_PHRASE)
        engine.runAndWait()
        elapsed = time.perf_counter() - t_start
        assert word_events, "SAPI5 no emitió eventos started-word"
        print(f" -> TTS OK: {len(word_events)} eventos started-word en {elapsed:.2f} s")
    finally:
        pythoncom.CoUninitialize()


def run_spike(samples_dir: Path) -> None:
    scanned_image = step_ingest(samples_dir)
    step_ocr(scanned_image)
    step_tts()
    print("SPIKE OK")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_spike(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/samples"))
