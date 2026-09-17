# -*- coding: utf-8 -*-
"""Build-time flipbook for the animated mark.

The mark now tilts, turns, squashes and winks. Doing that with live transforms
in Tk means re-rasterising vector art every frame in a process that has ~60 ms
to reach its first paint, so instead the whole thing is baked to PNGs at build
time and the banner just blits.

At banner size this is cheap: the mark is 30 px, only ~2 s of the 4.12 s
timeline actually moves, and everything else reuses one resting frame.

    python nabd_mark_frames.py assets/mark --scale 1 1.25 1.5 2

`index_for(t)` is the contract between this and the runtime. It is pure and
stdlib-only, so banner.py can import it without pulling in the build deps.
"""
from __future__ import annotations

import sys, pathlib

FRAME_MS = 8

# only these windows move. everything else is the resting mark.
MOTION = ((440, 908), (1500, 2528), (3030, 3548))
REST = 0                      # index 0 is the fully-assembled resting mark


def _spans():
    out, idx = [], 1
    for a, b in MOTION:
        n = int((b - a) / FRAME_MS) + 1
        out.append((a, b, idx, n))
        idx += n
    return out, idx


SPANS, FRAME_COUNT = _spans()


def index_for(t: float) -> int:
    """-> the frame index to show at time t. REST outside the motion windows."""
    for a, b, base, n in SPANS:
        if a <= t < b:
            return base + min(n - 1, int((t - a) / FRAME_MS))
    return REST


def plan():
    """-> [(index, t_ms)] for every frame that has to be rendered."""
    out = [(REST, 1200.0)]                 # resting: assembled, level, eyes open
    for a, b, base, n in SPANS:
        for i in range(n):
            out.append((base + i, a + i * FRAME_MS))
    return out


def render(outdir, scales=(1.0,), px=30, art=None, bg=None):
    """Rasterise the flipbook. Needs svglib + reportlab + rlPyCairo, which the
    build already has.

    `bg` is baked in and defaults to the banner's purple field. That is not
    laziness: the mark only ever appears on the solid card, and baking the
    background gives clean antialiased edges instead of the white fringing you
    get compositing a keyed-transparent PNG. Pass a different colour for the
    rail or the tray.
    """
    from io import BytesIO
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    from reportlab.lib.colors import HexColor
    import nabd_banner as B, nabd_mark as M
    art = art or M.CREAM
    bg_hex = bg or M.FIELD
    bg = HexColor(bg_hex)
    outdir = pathlib.Path(outdir)
    total = 0
    for sc in scales:
        d = outdir / ("%gx" % sc)
        d.mkdir(parents=True, exist_ok=True)
        size = int(round(px * sc))
        for idx, t in plan():
            # bg goes to pose_svg as well as to the rasteriser: svglib has no
            # transparency, so the horn and eye fades are mixed into the fill
            # against this exact colour. See nabd_mark._mix.
            svg = M.pose_svg(B.sample(t), size=size, art=art, bg=bg_hex)
            drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
            # svglib reads the SVG's width as POINTS, so a 60 px request comes
            # back 45 px. Rescale the drawing explicitly.
            k = float(size) / float(drawing.width)
            drawing.width = drawing.height = size
            drawing.scale(k, k)
            renderPM.drawToFile(drawing, str(d / ("mark_%04d.png" % idx)),
                                fmt="PNG", bg=bg)
            total += 1
    return total


def assert_invariants():
    import nabd_banner as B
    # every millisecond where the mark actually changes must fall in a window
    prev, uncovered = None, []
    for i in range(0, B.TOTAL_MS, 4):
        f = B.sample(i)
        key = (round(f.ring, 4), round(f.horns, 4), round(f.eyes, 4),
               round(f.tilt, 3), round(f.turn, 4), round(f.squash, 4), round(f.wink, 4))
        if prev is not None and key != prev:
            if not any(a <= i < b for a, b, _, _ in SPANS):
                uncovered.append(i)
        prev = key
    assert not uncovered, "mark changes outside a motion window at %s" % uncovered[:6]
    # the resting frame must match what the timeline holds between beats
    r = B.sample(1200.0)
    assert (r.ring, r.horns, r.eyes, r.tilt, r.turn, r.wink) == (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
    assert index_for(0) == REST and index_for(4119) == REST
    return FRAME_COUNT


def assert_raster():
    """Prove the rasteriser actually renders the channels the timeline moves.

    The timeline checks above all passed while the baked frames showed a fully
    drawn ring, permanent horn stubs and eyes that never opened, because svglib
    silently drops stroke-dashoffset and every form of opacity. Data assertions
    cannot see that. This one counts ink.
    """
    from io import BytesIO
    from dataclasses import replace
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    import nabd_banner as B, nabd_mark as M

    def ink(f, px=200):
        svg = M.pose_svg(f, size=px, art=M.CREAM, bg=M.FIELD)
        d = svg2rlg(BytesIO(svg.encode("utf-8")))
        k = float(px) / float(d.width)
        d.width = d.height = px
        d.scale(k, k)
        img = renderPM.drawToPIL(d, bg=0x6C3BAA).convert("L")
        return sum(1 for v in img.tobytes() if v > 120)

    rest = B.sample(1200.0)
    for name, lo, hi in (("ring", replace(rest, ring=0.0, horns=0, eyes=0),
                          replace(rest, ring=1.0, horns=0, eyes=0)),
                         ("horns", replace(rest, ring=0, horns=0.0, eyes=0),
                          replace(rest, ring=0, horns=1.0, eyes=0)),
                         ("eyes", replace(rest, ring=0, horns=0, eyes=0.0),
                          replace(rest, ring=0, horns=0, eyes=1.0))):
        a, b = ink(lo), ink(hi)
        assert b > a * 2 + 50, (
            "%s does not render: %d ink at 0.0 vs %d at 1.0. The rasteriser is "
            "dropping it -- check for opacity or dash attributes." % (name, a, b))
    return True


if __name__ == "__main__":
    n = assert_invariants()
    assert_raster()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scales = (1.0,)
    if "--scale" in sys.argv:
        i = sys.argv.index("--scale")
        scales = tuple(float(x) for x in sys.argv[i + 1:] if not x.startswith("--"))
    print("%d frames per scale (1 resting + %d moving)" % (n, n - 1))
    print("motion windows:", ", ".join("%d-%d" % (a, b) for a, b in MOTION))
    if args:
        made = render(args[0], scales)
        print("wrote %d PNGs to %s" % (made, args[0]))
    else:
        print("no output dir given; ran checks only")
