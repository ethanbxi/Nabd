# -*- coding: utf-8 -*-
"""nab'd save banner -- motion as data.

Replaces the previous nabd_banner.py. The card, the line and the ring are
unchanged; what is new is that the mark now assembles and performs.

    0     line slides out of the corner
    320   card stands up
    440   ring draws counter-clockwise
    660   horns grow out of the rim
    760   eyes open, landing on 900 as the ring closes
    620   ... dismiss rule drains ...
    1500  the head turns, tilts, squashes and winks -- one action
    2520  back to level
    3030  eyes close, 3075 horns retract  (reverse of the way they arrived)
    3200  ring winds back
    3630  card collapses
    3900  line slides off

TOTAL_MS is still 4,120, so nabd_sound's files still fit: every audio cue --
0, 320, 900, 3200, 3630, 3890 -- lands on a beat that did not move. The wink
is deliberately silent.

Drive it off a real clock, never a tick counter:

    start = time.perf_counter()
    def tick():
        t = (time.perf_counter() - start) * 1000.0
        if t >= TOTAL_MS: root.destroy(); return
        draw(sample(t)); root.after(8, tick)
"""
from __future__ import annotations
from dataclasses import dataclass

from nabd_ease import LINEAR, SLIDE, RISE, DRAW, WIND, COLLAPSE, LEAVE, FADE
import nabd_mark as M

CARD_W, CARD_H, LINE_H, MARGIN = 308, 76, 4, 20
TOTAL_MS = 4120

# the three dials the pose is built from
TILT_MAX, TURN_MAX, SQUASH = 14.0, 1.0, 0.88

TRACKS = {
    "alpha":  [(0, 80, 0.0, 1.0, FADE)],
    "w":      [(0, 260, 0, CARD_W, SLIDE), (3900, 4120, CARD_W, 0, LEAVE)],
    "h":      [(320, 580, LINE_H, CARD_H, RISE), (3630, 3830, CARD_H, LINE_H, COLLAPSE)],
    "ring":   [(440, 900, 0.0, 1.0, DRAW), (3200, 3540, 1.0, 0.0, WIND)],
    # horns lead the eyes by 100 ms in; leaving, they reverse -- eyes first
    "horns":  [(660, 810, 0.0, 1.0, RISE), (3075, 3195, 1.0, 0.0, LEAVE)],
    "eyes":   [(760, 900, 0.0, 1.0, RISE), (3030, 3150, 1.0, 0.0, LEAVE)],
    "copy":   [(440, 620, 0.0, 1.0, RISE), (3540, 3660, 1.0, 0.0, LINEAR)],
    "drain":  [(620, 3200, 1.0, 0.0, LINEAR)],
    "line":   [(320, 610, 1.0, 0.0, LINEAR), (3630, 3730, 0.0, 1.0, LINEAR)],
    # the wink. turn, tilt, squash and eye are ONE action in and one out.
    "tilt":   [(1500, 1700, 0.0, -3.5, RISE), (1700, 1870, -3.5, TILT_MAX, COLLAPSE),
               (1870, 2150, TILT_MAX, TILT_MAX, LINEAR),
               (2150, 2380, TILT_MAX, -4.5, RISE), (2380, 2520, -4.5, 0.0, RISE)],
    "turn":   [(1500, 1700, 0.0, -0.12, RISE), (1700, 1870, -0.12, TURN_MAX, COLLAPSE),
               (1870, 2150, TURN_MAX, TURN_MAX, LINEAR),
               (2150, 2380, TURN_MAX, -0.10, RISE), (2380, 2520, -0.10, 0.0, RISE)],
    "squash": [(1500, 1700, 1.0, 1.07, RISE), (1700, 1870, 1.07, SQUASH, COLLAPSE),
               (1870, 2000, SQUASH, 1.03, RISE), (2000, 2100, 1.03, 1.0, RISE)],
    "wink":   [(1700, 1870, 0.0, 1.0, COLLAPSE), (2080, 2240, 1.0, 0.0, RISE)],
}
INITIAL = {"alpha": 0.0, "w": 0, "h": LINE_H, "ring": 0.0, "horns": 0.0, "eyes": 0.0,
           "copy": 0.0, "drain": 1.0, "line": 1.0, "tilt": 0.0, "turn": 0.0,
           "squash": 1.0, "wink": 0.0}

# deliberate stillness. these are what separate the beats; do not close them.
HOLDS = ((260, 320), (3830, 3900))


@dataclass(frozen=True)
class Frame:
    alpha: float; w: int; h: int
    ring: float; horns: float; eyes: float
    copy: float; drain: float; line: float
    tilt: float; turn: float; squash: float; wink: float
    horn_lag: float

    def geometry(self, screen_w: int, screen_h: int, margin: int = MARGIN) -> str:
        return "%dx%d+%d+%d" % (self.w, self.h,
                                screen_w - margin - self.w, screen_h - margin - self.h)


def _track(segs, initial, t):
    v = initial
    for t0, t1, a, b, ease in segs:
        if t >= t1:
            v = b
        elif t > t0:
            return a + (b - a) * ease((t - t0) / (t1 - t0))
    return v


def _raw(t):
    return {k: _track(TRACKS[k], INITIAL[k], t) for k in TRACKS}


def sample(t: float) -> Frame:
    v = _raw(t)
    # the horns trail the head and overshoot. computed from where the head was
    # 45 ms ago rather than keyframed, so it stays right if TILT_MAX changes.
    back = _track(TRACKS["tilt"], INITIAL["tilt"], max(0.0, t - M.LAG_MS))
    lag = (back - v["tilt"]) * M.LAG_K
    return Frame(alpha=v["alpha"], w=int(round(v["w"])), h=int(round(v["h"])),
                 ring=v["ring"], horns=v["horns"], eyes=v["eyes"], copy=v["copy"],
                 drain=v["drain"], line=v["line"], tilt=v["tilt"], turn=v["turn"],
                 squash=v["squash"], wink=v["wink"], horn_lag=lag)


def timeline(fps: int = 125):
    step = 1000.0 / fps
    t = 0.0
    while t < TOTAL_MS:
        yield t, sample(t)
        t += step


# ── invariants ───────────────────────────────────────────────────────────
SOUND_CUES = (0, 320, 900, 3200, 3630, 3890)


def assert_invariants():
    """Run in the build. Each of these has been broken at least once."""
    assert TOTAL_MS == 4120, "nabd_sound.DURATION_MS must equal this"

    # 1. one axis at a time: the slides (w) and the rise/collapse (h) never
    #    move in the same millisecond, or the card opens as a diagonal.
    for t, f in timeline(fps=500):
        moving = []
        for k in ("w", "h"):
            for t0, t1, a, b, _ in TRACKS[k]:
                if t0 < t < t1 and a != b:
                    moving.append(k)
        assert len(set(moving)) < 2, "w and h both moving at %.0f ms" % t

    # 2. the eyes land exactly on the ring's close, which is where the sound's
    #    resolve sits. the horns lead them, and leaving they reverse.
    assert TRACKS["eyes"][0][1] == TRACKS["ring"][0][1] == 900
    assert TRACKS["horns"][0][0] < TRACKS["eyes"][0][0], "horns must lead the eyes in"
    assert TRACKS["eyes"][1][0] < TRACKS["horns"][1][0], "eyes must lead the horns out"

    # 3. the wink is one action with the turn, not two. they start together.
    assert TRACKS["wink"][0][0] == TRACKS["tilt"][1][0] == TRACKS["turn"][1][0]

    # 4. the eye is shut long enough to read and short enough not to hang.
    shut = [t for t, f in timeline(fps=1000) if f.wink > 0.999]
    held = max(shut) - min(shut)
    assert 150 <= held <= 320, "eye held shut %.0f ms" % held

    # 5. the pose is clear of the exit.
    assert sample(3030).tilt == 0.0 and sample(3030).turn == 0.0, \
        "head must be level before the eyes start clearing"

    # 6. the whole gesture sits inside the hold, not over the entry or exit.
    assert TRACKS["tilt"][0][0] > 900 and TRACKS["tilt"][-1][1] < 3030

    # 7. every audio cue still lands on a beat.
    # a cue may sit on the start OR the end of a beat -- 900 is the ring
    # closing, which is an end.
    marks = set()
    for k in TRACKS:
        for t0, t1, _, _, _ in TRACKS[k]:
            marks.add(t0); marks.add(t1)
    for c in SOUND_CUES:
        assert any(abs(c - mk) <= 10 for mk in marks), \
            "sound cue at %d ms has no beat within 10 ms" % c
    return held


if __name__ == "__main__":
    held = assert_invariants()
    print("total %d ms   eye held shut %d ms   sound cues all land" % (TOTAL_MS, held))
    print("\n%6s %6s %5s %5s %6s %6s %6s %6s %6s" %
          ("t", "ring", "horn", "eyes", "tilt", "turn", "squash", "wink", "lag"))
    for t, f in timeline(fps=8):
        print("%6.0f %6.2f %5.2f %5.2f %6.1f %6.2f %6.3f %6.2f %6.2f"
              % (t, f.ring, f.horns, f.eyes, f.tilt, f.turn, f.squash, f.wink, f.horn_lag))
