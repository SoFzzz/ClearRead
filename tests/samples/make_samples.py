"""Generate the synthetic sample PDFs used by the Day 1 spike and the tests.

Run from the repo root:  .\\.venv\\Scripts\\python tests\\samples\\make_samples.py

Outputs (no personal data, Spanish text with ñ, tildes and ü):
- sample_page_digital.pdf   text layer (pdfium can extract it)
- sample_page_scanned.pdf   image only (forces OCR)
- sample_page_password.pdf  text layer, RC4-40 encrypted, user password SAMPLE_PASSWORD
- sample_photo_exif6.jpg    stored landscape with EXIF Orientation=6 (displays portrait)

PDFs are written by hand so no PDF-writing dependency is needed.
"""

import hashlib
import io
import struct
import time
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

SAMPLES_DIR = Path(__file__).parent
SAMPLE_PASSWORD = "clearread"
EXPECTED_LINES = (
    "El niño leyó una canción en el jardín.",
    "Mañana estudiará matemáticas y física",
    "con su compañera de clase.",
    "¿Dónde está el cuaderno de química?",
    "¡Qué difícil es la pronunciación!",
    "El pingüino comió piña en la montaña.",
)
EXPECTED_TEXT = "\n".join(EXPECTED_LINES)

PAGE_WIDTH_PT = 595
PAGE_HEIGHT_PT = 842
FONT_SIZE_PT = 18
LINE_GAP_PT = 30
SCAN_DPI = 300
# Fixed so regenerating the samples yields byte-identical files.
FIXED_PDF_DATE = time.strptime("2026-10-01", "%Y-%m-%d")

# PDF 1.7 spec, Algorithm 2: fixed padding string for passwords.
PASSWORD_PAD = bytes.fromhex(
    "28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A"
)
PERMISSIONS = -4
EXIF_ORIENTATION_TAG = 0x0112
EXIF_ROTATE_90_CW = 6
# Stored pixels: 200 wide x 100 tall, red block at the top-left corner.
PHOTO_STORED_SIZE = (200, 100)
PHOTO_MARKER_BOX = (0, 0, 39, 39)
PHOTO_MARKER_RGB = (255, 0, 0)
PHOTO_BACKGROUND_RGB = (255, 255, 255)
FILE_ID = hashlib.md5(b"clearread-synthetic-sample").digest()


def rc4(key: bytes, data: bytes) -> bytes:
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) % 256
        state[i], state[j] = state[j], state[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + state[i]) % 256
        state[i], state[j] = state[j], state[i]
        out.append(byte ^ state[(state[i] + state[j]) % 256])
    return bytes(out)


def pad_password(password: str) -> bytes:
    return (password.encode("latin-1") + PASSWORD_PAD)[:32]


def escape_pdf_text(line: str) -> bytes:
    raw = line.encode("cp1252")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def text_content_stream() -> bytes:
    commands = [f"BT /F1 {FONT_SIZE_PT} Tf 60 760 Td {LINE_GAP_PT} TL".encode()]
    for line in EXPECTED_LINES:
        commands.append(b"(" + escape_pdf_text(line) + b") Tj T*")
    commands.append(b"ET")
    return b"\n".join(commands)


def build_pdf(objects: list[bytes], trailer_extra: bytes = b"") -> bytes:
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    file_id = f"<{FILE_ID.hex()}>".encode()
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R ".encode()
        + b"/ID ["
        + file_id
        + b" "
        + file_id
        + b"] "
        + trailer_extra
        + f">>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    )
    return out.getvalue()


def stream_object(data: bytes, extra_dict: bytes = b"") -> bytes:
    return (
        f"<< /Length {len(data)} ".encode()
        + extra_dict
        + b">>\nstream\n"
        + data
        + b"\nendstream"
    )


def text_page_objects(content: bytes) -> list[bytes]:
    return [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH_PT} {PAGE_HEIGHT_PT}] ".encode()
        + b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        stream_object(content),
    ]


def build_digital_pdf() -> bytes:
    return build_pdf(text_page_objects(text_content_stream()))


def build_password_pdf(user_password: str) -> bytes:
    # Standard security handler, revision 2 (40-bit RC4), PDF 1.7 Algorithms 1-4.
    owner_key = hashlib.md5(pad_password(user_password + "-owner")).digest()[:5]
    owner_entry = rc4(owner_key, pad_password(user_password))
    file_key = hashlib.md5(
        pad_password(user_password)
        + owner_entry
        + struct.pack("<i", PERMISSIONS)
        + FILE_ID
    ).digest()[:5]
    user_entry = rc4(file_key, PASSWORD_PAD)

    content_obj_number = 5
    object_key = hashlib.md5(
        file_key + struct.pack("<I", content_obj_number)[:3] + b"\x00\x00"
    ).digest()[:10]
    objects = text_page_objects(rc4(object_key, text_content_stream()))
    objects.append(
        b"<< /Filter /Standard /V 1 /R 2 "
        + b"/O <"
        + owner_entry.hex().encode()
        + b"> "
        + b"/U <"
        + user_entry.hex().encode()
        + b"> "
        + f"/P {PERMISSIONS} >>".encode()
    )
    return build_pdf(objects, trailer_extra=f"/Encrypt {len(objects)} 0 R ".encode())


def build_scanned_pdf(digital_pdf: Path) -> bytes:
    doc = pdfium.PdfDocument(str(digital_pdf))
    try:
        image = doc[0].render(scale=SCAN_DPI / 72).to_pil().convert("L")
    finally:
        doc.close()
    out = io.BytesIO()
    image.save(
        out,
        format="PDF",
        resolution=SCAN_DPI,
        creationDate=FIXED_PDF_DATE,
        modDate=FIXED_PDF_DATE,
    )
    return out.getvalue()


def build_exif_photo() -> bytes:
    image = Image.new("RGB", PHOTO_STORED_SIZE, PHOTO_BACKGROUND_RGB)
    ImageDraw.Draw(image).rectangle(PHOTO_MARKER_BOX, fill=PHOTO_MARKER_RGB)
    exif = Image.Exif()
    exif[EXIF_ORIENTATION_TAG] = EXIF_ROTATE_90_CW
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=95, subsampling=0, exif=exif)
    return out.getvalue()


def main() -> None:
    digital = SAMPLES_DIR / "sample_page_digital.pdf"
    digital.write_bytes(build_digital_pdf())
    (SAMPLES_DIR / "sample_page_scanned.pdf").write_bytes(build_scanned_pdf(digital))
    (SAMPLES_DIR / "sample_page_password.pdf").write_bytes(
        build_password_pdf(SAMPLE_PASSWORD)
    )
    (SAMPLES_DIR / "sample_photo_exif6.jpg").write_bytes(build_exif_photo())


if __name__ == "__main__":
    main()
