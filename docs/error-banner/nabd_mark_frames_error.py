# -*- coding: utf-8 -*-
"""Build-time flipbook for the error banner's mark.

The twin of nabd_mark_frames.py. Same 8 ms grid, same resting frame, and the
entry and exit windows are the SAME WINDOWS -- because the error banner shares
those tracks with the save banner rather than copying them.

    python nabd_mark_frames_error.py assets/mark-error --scale 1 1.25 1.5 2

`index_for(t)` is the contract between this and the runtime. Pure, stdlib-only,
so banner.py imports it without pulling in svglib.
"""
from __future__ import annotations

import sys, pathlib

FRAME_MS = 8

# entry and exit are the save banner's windows, unchanged. Only the middle
# differs: the shake runs longer than the wink did, because the eyes have to
# close first and open again afterwards.
MOTION = ((440, 908), (1500, 2828), (3030, 3548))
SHARED = ((440, 908), (3030, 3548))     # frames that must match the save banner
REST = 0


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
    out = [(REST, 1200.0)]
    for a, b, base, n in SPANS:
        for i in range(n):
            out.append((base + i, a + i * FRAME_MS))
    return out


def render(outdir, scales=(1.0,), px=30, art=None, bg=None):
    """Rasterise the flipbook. Needs svglib + reportlab + rlPyCairo.

    `bg` defaults to the ERROR field, not the save banner's purple. It is baked
    in for the same reason as the save banner's: the mark only ever appears on
    the solid card, and baking gives clean antialiased edges instead of the
    white fringing you get from a keyed-transparent PNG. It is also what makes
    the horn and eye fades possible at all -- svglib has no transparency, so
    pose_svg mixes those against this exact colour.
    """
    from io import BytesIO
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    from reportlab.lib.colors import HexColor
    import nabd_banner_error as B, nabd_mark as M
    art = art or M.CREAM
    bg_hex = bg or B.FIELD
    bg = HexColor(bg_hex)
    outdir = pathlib.Path(outdir)
    total = 0
    for sc in scales:
        d = outdir / ("%gx" % sc)
        d.mkdir(parents=True, exist_ok=True)
        size = int(round(px * sc))
        for idx, t in plan():
            svg = M.pose_svg(B.sample(t), size=size, art=art, bg=bg_hex)
            drawing = svg2rlg(BytesIO(svg.encode("utf-8")))
            k = float(size) / float(drawing.width)   # svglib reads width as POINTS
            drawing.width = drawing.height = size
            drawing.scale(k, k)
            renderPM.drawToFile(drawing, str(d / ("mark_%04d.png" % idx)),
                                fmt="PNG", bg=bg)
            total += 1
    return total


def assert_invariants():
    import nabd_banner_error as B
    prev, uncovered = None, []
    for i in range(0, B.TOTAL_MS, 4):
        f = B.sample(i)
        key = (round(f.ring, 4), round(f.horns, 4), round(f.eyes, 4),
               round(f.tilt, 3), round(f.turn, 4), round(f.squash, 4),
               round(f.shut, 4))
        if prev is not None and key != prev:
            if not any(a <= i < b for a, b, _, _ in SPANS):
                uncovered.append(i)
        prev = key
    assert not uncovered, "mark changes outside a motion window at %s" % uncovered[:6]
    r = B.sample(1200.0)
    assert (r.ring, r.horns, r.eyes, r.tilt, r.turn, r.shut) == (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
    assert index_for(0) == REST and index_for(4119) == REST
    return FRAME_COUNT


def assert_shared_with_save():
    """The entry and the exit must be the same pictures as the save banner's.

    This is the claim the whole design rests on: one product, two outcomes.
    If a pose ever diverges inside a shared window the two banners stop
    reading as the same thing, and nothing else would catch it -- the tracks
    are shared by reference, but `sample()` is not.
    """
    import nabd_banner_error as E, nabd_banner as S, nabd_mark as M
    checked = 0
    for a, b in SHARED:
        t = a
        while t < b:
            if M.pose_svg(E.sample(float(t)), size=120) != \
               M.pose_svg(S.sample(float(t)), size=120):
                raise AssertionError(
                    "error and save banners differ at %d ms, inside a shared "
                    "window -- they must be the same picture" % t)
            checked += 1
            t += 4
    return checked


def assert_raster():
    """Prove the rasteriser renders what the timeline moves. svglib drops
    stroke-dashoffset and every form of opacity; this counts ink instead."""
    from io import BytesIO
    from dataclasses import replace
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    import nabd_banner_error as B, nabd_mark as M

    def ink(f, px=200):
        svg = M.pose_svg(f, size=px, art=M.CREAM, bg=B.FIELD)
        d = svg2rlg(BytesIO(svg.encode("utf-8")))
        k = float(px) / float(d.width)
        d.width = d.height = px
        d.scale(k, k)
        rgb = int(B.FIELD[1:], 16)
        return sum(1 for v in renderPM.drawToPIL(d, bg=rgb).convert("L").tobytes()
                   if v > 120)

    rest = B.sample(1200.0)
    for name, lo, hi in (
            ("ring", replace(rest, ring=0.0, horns=0, eyes=0),
             replace(rest, ring=1.0, horns=0, eyes=0)),
            ("horns", replace(rest, ring=0, horns=0.0, eyes=0),
             replace(rest, ring=0, horns=1.0, eyes=0)),
            ("eyes", replace(rest, ring=0, horns=0, eyes=0.0),
             replace(rest, ring=0, horns=0, eyes=1.0))):
        a, b = ink(lo), ink(hi)
        assert b > a * 2 + 50, "%s does not render: %d ink at 0.0 vs %d at 1.0" % (name, a, b)
    # and the eyes must visibly shut
    open_eye = ink(replace(rest, ring=0, horns=0, shut=0.0))
    closed = ink(replace(rest, ring=0, horns=0, shut=1.0))
    assert closed < open_eye * 0.45, \
        "shut eyes still render at %d ink vs %d open -- the shut channel is not " \
        "reaching the raster" % (closed, open_eye)
    return True


if __name__ == "__main__":
    n = assert_invariants()
    shared = assert_shared_with_save()
    assert_raster()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scales = (1.0,)
    if "--scale" in sys.argv:
        i = sys.argv.index("--scale")
        scales = tuple(float(x) for x in sys.argv[i + 1:] if not x.startswith("--"))
    print("%d frames per scale (1 resting + %d moving)" % (n, n - 1))
    print("motion windows:", ", ".join("%d-%d" % (a, b) for a, b in MOTION))
    print("%d shared poses verified identical to the save banner" % shared)
    if args:
        made = render(args[0], scales)
        print("wrote %d PNGs to %s" % (made, args[0]))
