"""
Render the Inno Setup wizard artwork from the brand assets.

    python make_wizard_art.py

Two sets of BMPs land in installer/:

  wizard-WxH.bmp        the tall panel down the left of the welcome and
                        finished pages - a purple field carrying the cream
                        stacked lockup, which is the approved pairing (the
                        mark is never purple-on-purple).
  wizardsmall-WxH.bmp   the tile in the corner of every other page, on the
                        white the modern wizard header uses.

Inno picks whichever size best fits the user's DPI, so every size in its
published ladder is emitted and the .iss globs them.
"""
import sys
from pathlib import Path

from PIL import Image

import brand

OUT = Path(__file__).resolve().parent / "installer"

# Inno Setup 6's documented size ladders for the two wizard images.
BIG = [(164, 314), (192, 386), (246, 471), (273, 525), (328, 628),
       (355, 680), (410, 785), (464, 889), (519, 993), (573, 1098)]
SMALL = [(55, 55), (64, 68), (83, 80), (92, 97), (110, 106), (119, 123),
         (138, 140), (146, 148), (155, 159), (164, 161), (192, 192)]


def _field(width, height):
    """Purple, deepening toward the bottom so the panel has some weight."""
    top = _rgb(brand.PURPLE)
    bottom = _rgb(brand.PURPLE_DEEP)
    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        t = y / max(1, height - 1)
        row = tuple(int(round(a + (b - a) * t)) for a, b in zip(top, bottom))
        for x in range(width):
            px[x, y] = row
    return img


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def panel(width, height):
    """The tall welcome-page panel."""
    img = _field(width, height)

    # One oversized mark rising out of the bottom edge, a shade deeper than
    # the field it sits on. Centred so the bite at 4 o'clock stays visible and
    # it reads as the mark rather than as stray shapes - texture, not a second
    # logo, which is why the contrast against the field is this low.
    wm_size = int(width * 1.04)
    wm = brand.mark_image(wm_size, brand.PURPLE_DEEP)
    img.paste(wm, ((width - wm_size) // 2, int(height - wm_size * 0.58)), wm)

    # The stacked lockup as supplied, sitting in the upper third. Composing it
    # here from a mark and a wordmark would be a third arrangement of the two
    # to keep in step - and it would be the place the horn rule got broken,
    # since the supplied artwork already carries the plain n.
    stack = brand.stacked_image(int(width * 0.74), brand.CREAM)
    img.paste(stack, ((width - stack.width) // 2,
                      int(height * 0.30) - stack.height // 2), stack)
    return img


def corner(width, height):
    """The small header image on the interior pages."""
    img = Image.new("RGB", (width, height), "#FFFFFF")
    size = int(min(width, height) * 0.86)
    tile = brand.tile_image(size)
    img.paste(tile, ((width - size) // 2, (height - size) // 2), tile)
    return img


def main():
    OUT.mkdir(exist_ok=True)
    for w, h in BIG:
        panel(w, h).save(OUT / f"wizard-{w}x{h}.bmp")
    for w, h in SMALL:
        corner(w, h).save(OUT / f"wizardsmall-{w}x{h}.bmp")
    print(f"{len(BIG)} panels + {len(SMALL)} corners -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
