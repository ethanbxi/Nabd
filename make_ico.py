"""Render the app tile to icon.ico for the shortcuts.

The tile, not bare linework: the guidelines note the field treatment is what
survives a 16px tab, which is exactly the size Windows hands a shortcut icon.
"""
from pathlib import Path

import brand

SIZES = (16, 24, 32, 48, 64, 128, 256)

out = Path(__file__).resolve().parent / "icon.ico"
# Rendered per size rather than downscaled from one master, so the 22.5%
# corner radius and the 58% ring stay true at every size.
images = [brand.tile_image(s) for s in SIZES]
images[-1].save(out, sizes=[(s, s) for s in SIZES],
                append_images=images[:-1])
print(f"wrote {out}")
