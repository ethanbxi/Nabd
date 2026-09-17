"""cubic-bezier easing for tkinter.

Tk has no easing. If the banner's frames are spaced evenly on a timer you get a
linear open, and a linear open is most of what reads as "harsh". Sample these
instead.

The four numbers match the CSS exactly, so the spec and the build cannot drift.
"""
from __future__ import annotations


def cubic_bezier(x1: float, y1: float, x2: float, y2: float):
    """-> f(t) for t in 0..1, matching CSS cubic-bezier(x1, y1, x2, y2)."""
    def _cx(t): return 3 * x1 * (1 - t) ** 2 * t + 3 * x2 * (1 - t) * t * t + t ** 3
    def _cy(t): return 3 * y1 * (1 - t) ** 2 * t + 3 * y2 * (1 - t) * t * t + t ** 3
    def _dx(t):
        return (3 * x1 * (1 - 4 * t + 3 * t * t)
                + 3 * x2 * (2 * t - 3 * t * t) + 3 * t * t)

    def f(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        u = t                                   # Newton-Raphson, then bisect
        for _ in range(8):
            d = _dx(u)
            if abs(d) < 1e-6:
                break
            err = _cx(u) - t
            if abs(err) < 1e-7:
                return _cy(u)
            u -= err / d
        lo, hi = 0.0, 1.0
        u = t
        for _ in range(32):
            if _cx(u) < t:
                lo = u
            else:
                hi = u
            u = (lo + hi) / 2
        return _cy(u)

    return f


LINEAR   = lambda t: max(0.0, min(1.0, t))
SLIDE    = cubic_bezier(.22, .61, .36, 1)    # line slides out
RISE     = cubic_bezier(.33, 1,   .68, 1)    # card stands up  / copy fades up
DRAW     = cubic_bezier(.4,  0,   .25, 1)    # ring draws in
WIND     = cubic_bezier(.6,  0,   .4,  1)    # ring winds back
COLLAPSE = cubic_bezier(.45, 0,   .25, 1)    # card settles onto the line
LEAVE    = cubic_bezier(.5,  0,   .75, .6)   # line slides off
FADE     = cubic_bezier(.4,  0,   .35, 1)    # plain opacity
