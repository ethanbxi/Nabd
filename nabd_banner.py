"""nab'd save-banner motion, as data.

Every number here is the same number the CSS in the motion artifact uses. Drive
the banner off `sample(elapsed_ms)` against a real clock -- not off a tick
counter and not off four chained `after()` callbacks. Wall-clock sampling means
a dropped frame skips a value instead of desynchronising the phases.

    start = time.perf_counter()
    def tick():
        t = (time.perf_counter() - start) * 1000
        if t >= TOTAL_MS:
            root.destroy(); return
        draw(sample(t))
        root.after(8, tick)

Geometry is anchored to the bottom-right corner at all times:
    x = screen_w - MARGIN - f.w
    y = screen_h - MARGIN - f.h
so the slides move w and x, the rise and collapse move h and y, and the two
never happen in the same geometry() call. That separation is the design.
"""
from __future__ import annotations
from dataclasses import dataclass

from nabd_ease import LINEAR, SLIDE, RISE, DRAW, WIND, COLLAPSE, LEAVE, FADE

# -- fixed geometry (CSS px at 96 dpi; scale with nabd_tokens.px) ----------
CARD_W, CARD_H, LINE_H, MARGIN = 308, 76, 4, 20
TOTAL_MS = 4120

# -- tracks: (t0, t1, from, to, ease) -------------------------------------
TRACKS = {
    #                                            what it is
    "alpha": [(   0,   80, 0.0, 1.0, FADE)],     # window opacity
    "w":     [(   0,  260, 0,   CARD_W, SLIDE),  # line slides out of the corner
              (3900, 4120, CARD_W, 0,  LEAVE)],  # line slides off to the right
    "h":     [( 320,  580, LINE_H, CARD_H, RISE),      # card stands up
              (3630, 3830, CARD_H, LINE_H, COLLAPSE)], # card settles back down
    "ring":  [( 440,  900, 0.0, 1.0, DRAW),      # 0..1 of the 295 deg sweep
              (3200, 3540, 1.0, 0.0, WIND)],
    "copy":  [( 440,  620, 0.0, 1.0, RISE),      # mark + text opacity
              (3540, 3660, 1.0, 0.0, LINEAR)],
    "drain": [( 620, 3200, 1.0, 0.0, LINEAR)],   # fraction of the rule left
    "line":  [( 320,  610, 1.0, 0.0, LINEAR),    # purple-light overlay on the
              (3630, 3730, 0.0, 1.0, LINEAR)],   # bottom edge
}
INITIAL = {"alpha": 0.0, "w": 0, "h": LINE_H, "ring": 0.0,
           "copy": 0.0, "drain": 1.0, "line": 1.0}

# the 60 ms and 70 ms gaps are load-bearing: they are what keep the slide and
# the rise (and the collapse and the slide-off) reading as separate beats
# rather than one diagonal. do not close them to save time.
HOLDS = ((260, 320), (3830, 3900))


@dataclass(frozen=True)
class Frame:
    alpha: float
    w: int
    h: int
    ring: float
    copy: float
    drain: float
    line: float

    def geometry(self, screen_w: int, screen_h: int, margin: int = MARGIN) -> str:
        return "%dx%d+%d+%d" % (self.w, self.h,
                                screen_w - margin - self.w,
                                screen_h - margin - self.h)


def _track(segments, initial, t):
    v = initial
    for t0, t1, a, b, ease in segments:
        if t >= t1:
            v = b
        elif t > t0:
            return a + (b - a) * ease((t - t0) / (t1 - t0))
    return v


def sample(t: float) -> Frame:
    vals = {k: _track(TRACKS[k], INITIAL[k], t) for k in TRACKS}
    return Frame(alpha=vals["alpha"], w=int(round(vals["w"])), h=int(round(vals["h"])),
                 ring=vals["ring"], copy=vals["copy"],
                 drain=vals["drain"], line=vals["line"])


def timeline(fps: int = 120):
    """Every frame, for baking into a list or for testing."""
    step = 1000.0 / fps
    t = 0.0
    while t < TOTAL_MS:
        yield t, sample(t)
        t += step
