"""Drive the real save banner and check it against BANNER-MOTION.md.

    python _test/banner_test.py

Runs it on a monitor placed outside the virtual desktop, so a real Tk window
with real geometry and real assets is exercised without a pixel appearing over
whatever is in the foreground.
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import tkinter as tk                 # noqa: E402

import banner as B                   # noqa: E402
import nabd_banner as M              # noqa: E402
from nabd_ease import COLLAPSE, LEAVE   # noqa: E402

# far outside the virtual desktop (-2560..2560 on this machine)
OFFSCREEN = (-9000, 0, 1000, 800)
B.Banner._monitor = staticmethod(lambda index: OFFSCREEN)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def main():
    # -- the motion, as data ----------------------------------------------
    def moving(track, t):
        return any(t0 < t < t1 and a != b
                   for t0, t1, a, b, _e in M.TRACKS[track])

    clash = [t for t in range(M.TOTAL_MS + 1)
             if moving("w", t) and moving("h", t)]
    check("one axis at a time", not clash, str(clash[:4]))

    for a, b in M.HOLDS:
        busy = [t for t in range(a + 1, b)
                if any(moving(k, t) for k in M.TRACKS)]
        check(f"hold {a}-{b} is still ({b - a}ms)", not busy, str(busy[:3]))

    tail = lambda f: f(1.0) - f(0.90)
    head = lambda f: f(0.10) - f(0.0)
    check("collapse decelerates onto the line", tail(COLLAPSE) < head(COLLAPSE),
          f"({head(COLLAPSE):.3f} -> {tail(COLLAPSE):.3f})")
    check("only the leave accelerates", tail(LEAVE) > head(LEAVE),
          f"({head(LEAVE):.3f} -> {tail(LEAVE):.3f})")

    last = max(seg[1] for segs in M.TRACKS.values() for seg in segs)
    check("timeline is 4120ms", last == M.TOTAL_MS == 4120, f"({last})")

    # -- the frames --------------------------------------------------------
    d = B.asset_dir(1.0, "ok")
    check("frame set present", (d / "ring_16.png").exists()
          and (d / "card_h76.png").exists(), str(d))
    check("fail frame set present",
          (B.asset_dir(1.0, "fail") / "ring_16.png").exists())

    from PIL import Image
    full = Image.open(d / "ring_16.png").convert("RGB")
    # the mark keeps its 65 deg gap at 1 o'clock; frame 16 IS the logo
    gap = full.getpixel((21, 3))
    check("frame 16 keeps the gap at 1 o'clock", gap == B._rgb(B.FIELD["ok"]),
          f"rgb{gap}")

    # -- a real run --------------------------------------------------------
    root = tk.Tk()
    root.withdraw()
    seen = []
    closed = []
    bn = B.Banner(root, "Nabbed", "5:00 · 1.2 GB", "ok", 0,
                  on_close=lambda: closed.append(True))
    real_draw = bn.draw

    # Intercept the geometry the code commands. Reading it back off the window
    # returns whatever Tk last knows, which lags the pending call.
    geoms = []
    real_geom = bn.win.geometry

    def geom_spy(spec=None):
        if spec:
            geoms.append(spec)
        return real_geom(spec) if spec else real_geom()
    bn.win.geometry = geom_spy

    def spy(f):
        seen.append((f.w, f.h))
        return real_draw(f)
    bn.draw = spy

    t0 = time.perf_counter()
    while not closed and time.perf_counter() - t0 < 8:
        root.update()
        time.sleep(0.002)
    elapsed = (time.perf_counter() - t0) * 1000

    check("banner ran and closed itself", bool(closed), f"({elapsed:.0f} ms)")
    check("ran for about 4.1s", 3900 < elapsed < 5200, f"({elapsed:.0f} ms)")
    check("drew a real number of frames", len(seen) > 200, f"({len(seen)})")

    # width and height never changed on the same frame
    both = [i for i in range(1, len(seen))
            if seen[i][0] != seen[i - 1][0] and seen[i][1] != seen[i - 1][1]]
    check("w and h never move in one frame", not both,
          f"({len(both)} frames did)")

    widths = [w for w, _h in seen]
    heights = [h for _w, h in seen]
    check("reaches full size", max(widths) == M.CARD_W and max(heights) == M.CARD_H,
          f"({max(widths)}x{max(heights)})")
    check("returns to the line", heights[-1] <= M.LINE_H + 1
          and widths[-1] < M.CARD_W // 2, f"({widths[-1]}x{heights[-1]})")

    # -- placement ---------------------------------------------------------
    # Top-right, anchored by the card's BOTTOM edge so the rise still reads as
    # the card standing up out of the line.
    mx, my, mw, mh = OFFSCREEN
    parsed = []
    for g in geoms:
        size, rest = g.split("+", 1)
        w_, h_ = (int(v) for v in size.split("x"))
        x_, y_ = (int(v) for v in rest.split("+"))
        parsed.append((w_, h_, x_, y_))
    rights = {x + w for w, h, x, y in parsed}
    bottoms = {y + h for w, h, x, y in parsed}
    check("right edge is fixed", len(rights) == 1, f"{sorted(rights)}")
    check("bottom edge is fixed", len(bottoms) == 1, f"{sorted(bottoms)}")
    check("right margin is 24px",
          rights == {mx + mw - B.MARGIN_RIGHT}, f"{sorted(rights)}")
    check("top of the full card is 64px down",
          bottoms == {my + B.MARGIN_TOP + M.CARD_H},
          f"{sorted(bottoms)} (card top at {min(bottoms) - M.CARD_H})")

    try:
        root.destroy()
    except tk.TclError:
        pass

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
