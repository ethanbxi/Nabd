"""Render the tile lockup at several sizes, to pick one the letters survive."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

SIZES = [brand.MIN_TILE_LOCKUP, 52, 60, 68, 80]
pad, gap = 20, 18
images = [(s, brand.tile_lockup_image(s)) for s in SIZES]

width = max(i.width for _, i in images) + pad * 2 + 90
height = sum(i.height + gap for _, i in images) + pad * 2
sheet = Image.new("RGB", (width, height), brand.SHELL)
draw = ImageDraw.Draw(sheet)

y = pad
for size, img in images:
    sheet.paste(img, (pad, y), img)
    stroke = brand.WORD_STROKE * (size * brand.TILE_WORD_RATIO) / brand.WORD_HEIGHT
    draw.text((pad + img.width + 16, y + img.height // 2 - 6),
              f"tile {size}  ->  {img.width}px wide, stroke {stroke:.1f}px",
              fill=brand.MUTED if hasattr(brand, "MUTED") else brand.CREAM)
    y += img.height + gap

sheet.save(OUT / "lockup_sizes.png")
print(f"wrote {OUT / 'lockup_sizes.png'}")
print(f"minimum tile for a 120px lockup: {brand.MIN_TILE_LOCKUP}")
