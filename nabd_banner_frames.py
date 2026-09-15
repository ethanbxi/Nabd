"""Build-time frame generation for the save banner.

Run this in the build, not at launch. The banner is a fresh process per nab and
onedir was chosen to keep that launch cheap; rendering rounded rectangles in
Pillow on startup would hand it straight back.

    python nabd_banner_frames.py assets/banner --scale 1 1.25 1.5 2
"""
from __future__ import annotations
import argparse, math, os

from PIL import Image, ImageDraw

PURPLE, PURPLE_LIGHT, CREAM = "#6C3BAA", "#9B6BD8", "#F3EFE9"
RING_FRAMES = 16
SWEEP_START, SWEEP_SPAN = 95.0, 295.0     # degrees; span ends exactly at the gap
SS = 4                                     # supersample -- PIL has no AA


def _rgb(h): h = h.lstrip("#"); return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def ring_frame(size: int, p: float, color=CREAM, bg=PURPLE) -> Image.Image:
    """p = 0..1 of the sweep. At p = 1 this is the logo, to the pixel."""
    s = size * SS
    img = Image.new("RGB", (s, s), _rgb(bg))
    if p > 0:
        d = ImageDraw.Draw(img)
        w = max(1, int(round(0.14 * s)))
        pad = w / 2
        # PIL: 0 deg is 3 o'clock and angles increase clockwise. The mark's run
        # is math t 95 -> 390 (counter-clockwise on screen), so grow `start` down.
        end = -SWEEP_START
        d.arc([pad, pad, s - pad - 1, s - pad - 1], end - SWEEP_SPAN * p, end,
              fill=_rgb(color), width=w)
    return img.resize((size, size), Image.LANCZOS)


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


def build(out_dir: str, scale: float) -> int:
    d = os.path.join(out_dir, f"{scale:g}x")
    os.makedirs(d, exist_ok=True)
    px = lambda v: int(round(v * scale))
    n = 0
    for i in range(RING_FRAMES + 1):                      # 0 .. 16 inclusive
        ring_frame(px(30), i / RING_FRAMES).save(os.path.join(d, f"ring_{i:02d}.png"))
        n += 1
    # the card at every height the rise and collapse pass through, 2 px apart
    for h in range(4, 77, 2):
        r = 2 + (12 - 2) * (h - 4) / 72                   # radius tracks height
        card(px(308), px(h), px(r), px(4), 1.0 if h <= 6 else 0.0).save(
            os.path.join(d, f"card_h{h:02d}.png"))
        n += 1
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--scale", nargs="*", type=float, default=[1.0, 1.25, 1.5, 2.0])
    a = ap.parse_args()
    for sc in a.scale:
        print(f"{sc:g}x -> {build(a.out, sc)} files")
    # the contract that must never drift: at p = 1 the sweep is the LOGO, which
    # means the 65 deg gap between 1 o'clock and noon is still open. if a future
    # tweak to SWEEP_SPAN closes it, the build fails here rather than shipping a
    # banner that trains people on a plain circle.
    full = ring_frame(120, 1.0)
    gap, arc = full.getpixel((84, 14)), full.getpixel((8, 59))
    assert gap == _rgb(PURPLE), f"p=1 closed the gap at 1 o'clock (got {gap})"
    assert arc != _rgb(PURPLE), f"p=1 did not draw the ring (got {arc})"
    print("assert ok: frame 16 is the logo -- gap open, ring drawn")
