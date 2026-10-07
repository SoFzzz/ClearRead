"""Build resources/icons/app.ico from app_logo.png and the size sheet for review.

Run from the repository root: .venv/Scripts/python tests/manual/make_app_icon.py
The logo's colors are never changed: it is only cropped, padded to a square and
resampled.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "resources" / "icons" / "app_logo.png"
ICO = ROOT / "resources" / "icons" / "app.ico"
SHEET = (
    ROOT / "docs" / "design-system" / "mockups" / "real" / "v2" / "icono_tamanos.png"
)
SIZES = (16, 24, 32, 48, 64, 128, 256)
ALPHA_THRESHOLD = 24  # ignores the faint halo pixels at the edge of the artwork
LIGHT_BG = (255, 255, 255, 255)
DARK_BG = (24, 24, 28, 255)
CELL = 300


def square_crop(logo: Image.Image) -> Image.Image:
    """Crop the empty margin, then pad the shorter side so the logo stays centered."""
    mask = logo.getchannel("A").point(lambda a: 255 if a > ALPHA_THRESHOLD else 0)
    cropped = logo.crop(mask.getbbox())
    side = max(cropped.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2))
    return square


def draw_sheet(master: Image.Image) -> Image.Image:
    width = CELL * len(SIZES)
    sheet = Image.new("RGBA", (width, CELL * 2), LIGHT_BG)
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((0, CELL, width, CELL * 2), fill=DARK_BG)
    for column, size in enumerate(SIZES):
        icon = master.resize((size, size), Image.Resampling.LANCZOS)
        for row, background in enumerate((LIGHT_BG, DARK_BG)):
            left = column * CELL + (CELL - size) // 2
            top = row * CELL + (CELL - size) // 2
            sheet.alpha_composite(icon, (left, top))
            label_color = (
                (0, 0, 0, 255) if background == LIGHT_BG else (235, 235, 235, 255)
            )
            draw.text(
                (column * CELL + 8, row * CELL + 8), f"{size} px", fill=label_color
            )
    return sheet


def main() -> None:
    master = square_crop(Image.open(LOGO).convert("RGBA"))
    master.save(ICO, format="ICO", sizes=[(size, size) for size in SIZES])
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    draw_sheet(master).convert("RGB").save(SHEET)
    print(f"master {master.size}, ico sizes {SIZES}")


if __name__ == "__main__":
    main()
