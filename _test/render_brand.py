"""Render the drawn logo so it can be eyeballed against the guidelines."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

sheet = Image.new("RGBA", (760, 300), brand.SHELL)
d = ImageDraw.Draw(sheet)

# app tiles at the sizes the guidelines call out
x = 24
for size in (128, 64, 48, 32, 16):
    tile = brand.tile_image(size)
    sheet.alpha_composite(tile, (x, 24 + (128 - size) // 2))
    d.text((x, 170), str(size), fill=brand.CREAM)
    x += size + 20

# tray template at tray sizes, cream on shell
x = 380
for size in (22, 18, 16):
    ring = brand.ring_image(size, brand.CREAM, stroke_scale=15 / 14)
    sheet.alpha_composite(ring, (x, 70))
    x += size + 18

# a large ring to inspect the gap position and terminals
sheet.alpha_composite(brand.ring_image(180, brand.CREAM), (500, 60))
d.text((380, 170), "tray template 22/18/16", fill=brand.CREAM)
d.text((500, 250), "gap should sit at 1 o'clock", fill=brand.CREAM)

# purple field lockup check: cream ring on Nabd Purple
field = Image.new("RGBA", (340, 90), brand.PURPLE)
field.alpha_composite(brand.ring_image(60, brand.CREAM), (16, 15))
sheet.alpha_composite(field, (24, 195))

path = OUT / "brand_check.png"
sheet.convert("RGB").save(path)
print(f"wrote {path}")
