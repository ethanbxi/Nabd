"""Render the mark at fixed instants, to check the assembly order.

Faster than trying to photograph a 460ms animation: the same artwork the
banner blits, stepped by hand.

Was a trace of an arc drawn from brand.py's transcribed geometry. The mark is
a posed path now - it grows horns and opens eyes as well as drawing its ring -
so this renders the real thing through nabd_mark_frames, which is the one
definition of that raster path. Build-time deps (svglib, reportlab) required,
as for any other frame render.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw  # noqa: E402

import brand  # noqa: E402
import nabd_banner as M  # noqa: E402
import nabd_mark_frames as F  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

# The assembly, then the gesture. 440 is the ring starting, 660 the horns,
# 760 the eyes, 900 the close; 1800 is the wink at its deepest.
STEPS = [480, 600, 700, 800, 900, 1200, 1800]
CELL, MARK = 96, 72

sheet = Image.new("RGB", (CELL * len(STEPS), CELL + 22), brand.SHELL)
draw = ImageDraw.Draw(sheet)

for i, t in enumerate(STEPS):
    img = F.render_one(t, px=MARK, art=brand.CREAM, bg=brand.SHELL)
    sheet.paste(img, (i * CELL + (CELL - MARK) // 2, 8))
    draw.text((i * CELL + 26, CELL + 4), f"{t}ms", fill=brand.CREAM)

path = OUT / "trace_steps.png"
sheet.save(path)
print(f"wrote {path}")

f = M.sample(900)
print(f"at 900ms: ring {f.ring:.2f}, horns {f.horns:.2f}, eyes {f.eyes:.2f}"
      f"  - the ring closes and the eyes finish together, on the sound's"
      f" resolve")
print(f"{F.FRAME_COUNT} poses baked per scale, "
      f"windows {', '.join('%d-%d' % w for w in F.MOTION)}")
