"""Generate the save banner's frames, in both field colours.

    python make_banner_assets.py

Build-time only. BANNER-MOTION.md is explicit about why: the banner is drawn
entirely from these PNGs, and rendering rounded rectangles in Pillow at launch
gives back exactly what onedir was chosen to buy.

The "ok" set is nabd_banner_frames.build() unchanged, including its assertion
that frame 16 is the logo. The "fail" set - which the motion spec does not
cover, because it only describes the save banner - reuses the very same
ring_frame() and card() with a different field, so there is one definition of
the geometry and the two can never drift apart.
"""
from __future__ import annotations

import os
import sys

import nabd_banner_frames as F
import nabd_tokens as T

SCALES = (1.0, 1.25, 1.5, 2.0)
FAIL_FIELD = T.DANGER        # #B4483E
FAIL_LINE = "#D2665C"        # the danger equivalent of purple-light


def build_variant(out_dir, scale, field, line, suffix=""):
    d = os.path.join(out_dir, f"{scale:g}x{suffix}")
    os.makedirs(d, exist_ok=True)
    px = lambda v: int(round(v * scale))
    n = 0
    for i in range(F.RING_FRAMES + 1):
        F.ring_frame(px(30), i / F.RING_FRAMES, bg=field).save(
            os.path.join(d, f"ring_{i:02d}.png"))
        n += 1
    for h in range(4, 77, 2):
        r = 2 + (12 - 2) * (h - 4) / 72
        F.card(px(308), px(h), px(r), px(4), 1.0 if h <= 6 else 0.0,
               bg=field, line=line).save(os.path.join(d, f"card_h{h:02d}.png"))
        n += 1
    return n


def main(out="assets/banner"):
    total = 0
    for scale in SCALES:
        total += F.build(out, scale)                      # the purple field
        total += build_variant(out, scale, FAIL_FIELD, FAIL_LINE, "-fail")
    # The contract that must never drift, run exactly as the handoff wrote it:
    # at p = 1 the sweep is the LOGO, so the 65 deg gap at 1 o'clock is open.
    full = F.ring_frame(120, 1.0)
    gap, arc = full.getpixel((84, 14)), full.getpixel((8, 59))
    assert gap == F._rgb(F.PURPLE), f"p=1 closed the gap at 1 o'clock ({gap})"
    assert arc != F._rgb(F.PURPLE), f"p=1 did not draw the ring ({arc})"
    print(f"  banner frames: {total} files across {len(SCALES)} scales "
          f"x 2 fields")
    print("  assert ok: frame 16 is the logo - gap open, ring drawn")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "assets/banner"))
