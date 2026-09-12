"""Render the draw-on at fixed progress values, to check the stroke order.

Faster than trying to photograph a 520ms animation: the same geometry the
banner uses, stepped by hand.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

STEPS = [0.12, 0.3, 0.5, 0.7, 0.88, 1.0]
CELL, RING = 96, 72
sheet = Image.new("RGB", (CELL * len(STEPS), CELL + 22), brand.SHELL)
draw = ImageDraw.Draw(sheet)

for i, progress in enumerate(STEPS):
    img = Image.new("RGBA", (RING * 8, RING * 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = RING * 8 / brand.BOX
    c = RING * 8 / 2
    r = brand.RADIUS * s
    box = (c - r, c - r, c + r, c + r)
    extent = brand.STROKE_EXTENT * progress
    if extent > 0.5:
        # Tk counts counter-clockwise, PIL clockwise.
        d.arc(box, start=-(brand.STROKE_START + extent),
              end=-brand.STROKE_START, fill=brand.PURPLE_LIGHT,
              width=max(1, round(brand.STROKE * s)))
    img = img.resize((RING, RING), Image.LANCZOS)
    sheet.paste(img, (i * CELL + (CELL - RING) // 2, 8), img)
    draw.text((i * CELL + 30, CELL + 4), f"{progress:.2f}", fill=brand.CREAM)

path = OUT / "trace_steps.png"
sheet.save(path)
print(f"wrote {path}")
print(f"stroke starts at {brand.STROKE_START}deg and sweeps "
      f"{brand.STROKE_EXTENT}deg counter-clockwise, leaving a "
      f"{brand.GAP_EXTENT}deg gap centred on "
      f"{(brand.GAP_START + brand.GAP_EXTENT / 2):.1f}deg (1 o'clock)")
