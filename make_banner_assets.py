"""Generate the save banner's frames, in both field colours.

    python make_banner_assets.py

Build-time only. The banner is drawn entirely from these PNGs, and rendering
them at launch gives back exactly what onedir was chosen to buy.

Two sets land in each assets/banner/<scale>x[-fail] directory:

  card_h??.png    the card at every height the rise and collapse pass through
  mark_????.png   the mark's flipbook

The mark is a flipbook now because it poses: it tilts, turns, squashes and
winks, so it can no longer be one cached PNG with a partial ring drawn over it
(docs/overhaul/OVERHAUL.md section 6). nabd_mark_frames owns that render and
the index_for() contract the banner reads it back through.

card() moved here from nabd_banner_frames.py, which the overhaul retired. That
file held the card generator as well as the ring frames and only the ring half
was superseded, so the geometry below is unchanged - same supersample, same
radius ramp, same 2px height step the banner's asset cache expects.

The "fail" field is not in the motion spec, which only describes the save
banner. It reuses the very same card() and the very same flipbook at a
different field, so there is one definition of the geometry and the two can
never drift apart.
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

import nabd_banner as B
import nabd_banner_error as E
import nabd_mark_frames as F
import nabd_mark_frames_error as FE
import nabd_tokens as T

SCALES = (1.0, 1.25, 1.5, 2.0)
PURPLE, PURPLE_LIGHT = "#6C3BAA", "#9B6BD8"
# The failure ground comes from the error timeline, not from --danger. Cream on
# #B4483E is 4.21:1, which would make the failure copy harder to read than the
# success copy; #8E3229 puts it at 6.28:1, better than purple's own 5.82:1.
# See docs/error-banner/ERROR.md section 5.
FAIL_FIELD = E.FIELD         # #8E3229
FAIL_LINE = E.FIELD_EDGE     # #D2695C, as purple-light is to purple

# The card's cream, a touch warmer than the brand's #E8E4DC. It is the TITLE's
# colour, and it was the retired ring's - but not the mark's. The reference
# renders the mark in brand cream (docs/banner/make_reference_gif.py), and
# BANNER.md is explicit that where the reference and the app disagree the app
# is wrong, so the flipbook takes nabd_mark.CREAM by leaving `art` unset.
CARD_CREAM = "#F3EFE9"
# The mark's posed box on the card, CSS px. Shared with banner.py through
# nabd_tokens, because a Tk canvas image is drawn at its native size: bake it
# at one size and blit it at another and the mark is silently wrong.
MARK_PX = T.BANNER_MARK


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


SS = 4                       # supersample -- PIL has no AA


def card(w: int, h: int, radius: int, line_px: int, line_opacity: float,
         bg=PURPLE, line=PURPLE_LIGHT) -> Image.Image:
    """The card at an arbitrary size, with the bottom line blended over it."""
    s = SS
    img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=radius * s,
                        fill=_rgb(bg) + (255,))
    if line_opacity > 0:
        lh = max(1, line_px * s)
        overlay = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle(
            [0, h * s - lh, w * s - 1, h * s - 1], radius=min(radius, line_px) * s,
            fill=_rgb(line) + (int(255 * line_opacity),))
        img = Image.alpha_composite(img, overlay)
    return img.resize((w, h), Image.LANCZOS)


def build_cards(out_dir, scale, field, line, suffix=""):
    """The card at every height the rise and collapse pass through, 2px apart."""
    d = os.path.join(out_dir, f"{scale:g}x{suffix}")
    os.makedirs(d, exist_ok=True)
    px = lambda v: int(round(v * scale))
    n = 0
    for h in range(4, 77, 2):
        r = 2 + (12 - 2) * (h - 4) / 72                   # radius tracks height
        card(px(B.CARD_W), px(h), px(r), px(4), 1.0 if h <= 6 else 0.0,
             bg=field, line=line).save(os.path.join(d, f"card_h{h:02d}.png"))
        n += 1
    return n


def main(out="assets/banner"):
    # All three checks, before a single PNG is written. They encode the things
    # that have already gone wrong once: a retimed beat that leaves the mark
    # changing outside a motion window, and - the one no data assertion can
    # see - a rasteriser that silently drops the channel the timeline is
    # moving. assert_raster() counts ink at 0.0 and 1.0 for the ring, the
    # horns and the eyes, because a flipbook can be static with every other
    # test green. See docs/banner/BANNER.md section 5a.
    held = B.assert_invariants()
    frames = F.assert_invariants()
    F.assert_raster()
    print(f"  motion      {B.TOTAL_MS}ms, eye held shut {held:.0f}ms, "
          f"sound cues all land")
    print(f"  flipbook    {frames} frames per scale, "
          f"windows {', '.join('%d-%d' % w for w in F.MOTION)}")
    print("  raster      ring, horns and eyes all actually render")

    # The error banner's three, including the one that proves the two banners
    # are still the same product: every pose in the shared entry and exit
    # windows must render to the identical picture. The tracks are shared by
    # reference, but sample() is not, so nothing else would catch a drift.
    shut, traverses = E.assert_invariants()
    e_frames = FE.assert_invariants()
    shared = FE.assert_shared_with_save()
    FE.assert_raster()
    print(f"  error       {E.TOTAL_MS}ms, eyes shut {shut:.0f}ms, "
          f"{traverses} traverses, field {E.FIELD}")
    print(f"  error book  {e_frames} frames per scale, "
          f"windows {', '.join('%d-%d' % w for w in FE.MOTION)}")
    print(f"  shared      {shared} entry/exit poses identical to the save banner")

    total = 0
    for scale in SCALES:
        total += build_cards(out, scale, PURPLE, PURPLE_LIGHT)
        total += build_cards(out, scale, FAIL_FIELD, FAIL_LINE, "-fail")
    print(f"  cards       {total} files across {len(SCALES)} scales x 2 fields")

    # The two fields get different FLIPBOOKS now, not just different grounds:
    # the save banner winks, the error banner shuts both eyes and shakes.
    marks = F.render(out, SCALES, px=MARK_PX, bg=PURPLE)
    print(f"  marks       {marks} save poses across {len(SCALES)} scales")
    e_marks = FE.render(out, SCALES, px=MARK_PX, bg=FAIL_FIELD, suffix="-fail")
    print(f"  error marks {e_marks} error poses across {len(SCALES)} scales")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "assets/banner"))
