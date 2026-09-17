# -*- coding: utf-8 -*-
"""nab'd error banner -- the daemon says no.

The save banner's twin. The card arrives the same way and leaves the same way;
only the performance in the hold is different. Where the save banner winks,
this one shuts both eyes and shakes its head.

    0     line slides out of the corner          | identical
    320   card stands up                         | identical
    440   ring draws counter-clockwise           | to
    660   horns grow out of the rim              | the
    760   eyes open, landing on 900              | save banner
    1500  eyes close
    1640  five traverses, decaying               <- the gesture
    2600  eyes open again, slowly
    3030  eyes close, 3075 horns retract         | identical
    3200  ring winds back                        | to
    3630  card collapses                         | the
    3900  line slides off                        | save banner

TOTAL_MS is 4,120, the same as the save banner, and the six audio beats are in
the same places. That is the whole point: the entry and exit frames are shared
with the save banner's flipbook, the error sound fits the same envelope, and
the only thing a reader has to learn is the gesture in the middle.

The field is NOT the save banner's purple -- see FIELD below.
"""
from __future__ import annotations
from dataclasses import dataclass

from nabd_ease import LINEAR, SLIDE, RISE, DRAW, WIND, COLLAPSE, LEAVE, FADE
import nabd_mark as M
import nabd_banner as SAVE

CARD_W, CARD_H, LINE_H, MARGIN = SAVE.CARD_W, SAVE.CARD_H, SAVE.LINE_H, SAVE.MARGIN
TOTAL_MS = SAVE.TOTAL_MS          # 4120. Do not change; the WAV is this long.

# The error ground. NOT --danger #B4483E: cream on that is 4.21:1, which would
# make the failure copy harder to read than the success copy. Deepened to
# #8E3229, cream lands at 6.28:1 -- better than the save banner's own 5.82:1.
FIELD = "#8E3229"
FIELD_EDGE = "#D2695C"            # the lit 4 px edge, as purple-light is to purple

# the dials
# Peak turn. The save banner's wink never exceeds 1.0; this goes past it on
# purpose. With the eyes shut, the eye parallax that normally carries a turn is
# gone, so the amplitude has to do that work instead -- and pushing this one
# dial scales the eye travel, the horn asymmetry and the silhouette squeeze
# together, through the same physics, rather than bolting on a second effect.
SHAKE_MAX = 1.35
TILT_K = 4.5                      # degrees of roll per unit of turn
SHUT_MS = 140                     # how long the eyes take to close

# The shake. Five traverses with the amplitude decaying, each one eased
# in-and-out so it is fastest crossing centre and slowest at the reversals --
# which is what a head actually does. ~160 ms a traverse is about 3 Hz: brisk
# enough to read as "no", not so fast it looks like a glitch.
SHAKE = [(1640, 1750, 0.00, -0.38, RISE),      # anticipation, the wrong way
         (1750, 1915, -0.38, SHAKE_MAX, WIND),
         (1915, 2075, SHAKE_MAX, -1.18, WIND),
         (2075, 2225, -1.18, 0.82, WIND),
         (2225, 2365, 0.82, -0.47, WIND),
         (2365, 2495, -0.47, 0.19, WIND),
         (2495, 2600, 0.19, 0.00, RISE)]       # settles dead centre

TRACKS = {
    # ── entry and exit: taken from the save banner, not retyped ──────────
    "alpha": SAVE.TRACKS["alpha"], "w": SAVE.TRACKS["w"], "h": SAVE.TRACKS["h"],
    "ring": SAVE.TRACKS["ring"], "horns": SAVE.TRACKS["horns"],
    "eyes": SAVE.TRACKS["eyes"], "copy": SAVE.TRACKS["copy"],
    "drain": SAVE.TRACKS["drain"], "line": SAVE.TRACKS["line"],
    # ── the gesture ──────────────────────────────────────────────────────
    "turn": SHAKE,
    # both eyes. Shut before the first traverse, and slow to open afterwards:
    # the reluctance is the point, and it fills the hold so nothing sits still.
    "shut": [(1500, 1500 + SHUT_MS, 0.0, 1.0, COLLAPSE),
             (2600, 2820, 1.0, 0.0, RISE)],
    # a small sigh as the eyes go, and nothing during the shake itself --
    # one axis at a time.
    "squash": [(1500, 1610, 1.0, 0.955, COLLAPSE), (1610, 1720, 0.955, 1.0, RISE)],
}
INITIAL = {"alpha": 0.0, "w": 0, "h": LINE_H, "ring": 0.0, "horns": 0.0,
           "eyes": 0.0, "copy": 0.0, "drain": 1.0, "line": 1.0, "turn": 0.0,
           "shut": 0.0, "squash": 1.0}

HOLDS = SAVE.HOLDS
SOUND_CUES = SAVE.SOUND_CUES


@dataclass(frozen=True)
class Frame:
    alpha: float; w: int; h: int
    ring: float; horns: float; eyes: float
    copy: float; drain: float; line: float
    tilt: float; turn: float; squash: float
    wink: float; shut: float
    horn_lag: float

    def geometry(self, screen_w: int, screen_h: int, margin: int = MARGIN) -> str:
        return "%dx%d+%d+%d" % (self.w, self.h,
                                screen_w - margin - self.w, screen_h - margin - self.h)


_track = SAVE._track


def _turn_at(t):
    return _track(SHAKE, 0.0, t)


def _tilt_at(t):
    """Roll is computed from yaw, never keyframed.

    The same rule the horn lag follows. A shake that rolls a little reads as a
    head; one that only yaws reads as a turntable. Deriving it means the two
    can never drift out of phase, and changing SHAKE_MAX carries the roll with
    it automatically.
    """
    return _turn_at(t) * TILT_K


def sample(t: float) -> Frame:
    v = {k: _track(TRACKS[k], INITIAL[k], t) for k in TRACKS}
    tilt = _tilt_at(t)
    lag = (_tilt_at(max(0.0, t - M.LAG_MS)) - tilt) * M.LAG_K
    return Frame(alpha=v["alpha"], w=int(round(v["w"])), h=int(round(v["h"])),
                 ring=v["ring"], horns=v["horns"], eyes=v["eyes"], copy=v["copy"],
                 drain=v["drain"], line=v["line"], tilt=tilt, turn=v["turn"],
                 squash=v["squash"], wink=0.0, shut=v["shut"], horn_lag=lag)


def timeline(fps: int = 125):
    step = 1000.0 / fps
    t = 0.0
    while t < TOTAL_MS:
        yield t, sample(t)
        t += step


# ── invariants ───────────────────────────────────────────────────────────
def assert_invariants():
    """Run in the build. Everything here is either shared with the save banner
    or specific to the shake."""
    assert TOTAL_MS == 4120 == SAVE.TOTAL_MS, "the WAV and the save banner are both this long"

    # 1. the entry and the exit are SHARED, not copied. If the save banner is
    #    retimed this fails rather than silently diverging.
    for k in ("alpha", "w", "h", "ring", "horns", "eyes", "copy", "drain", "line"):
        assert TRACKS[k] is SAVE.TRACKS[k], "%s must be the save banner's own track" % k

    # 2. one axis at a time, same as the save banner.
    for t, f in timeline(fps=500):
        moving = [k for k in ("w", "h")
                  for t0, t1, a, b, _ in TRACKS[k] if t0 < t < t1 and a != b]
        assert len(set(moving)) < 2, "w and h both moving at %.0f ms" % t

    # 3. the eyes are fully shut before the first traverse, and the shake is
    #    over before they start to open. A shake with the eyes open is a
    #    different gesture -- it reads as looking around, not refusing.
    assert TRACKS["shut"][0][1] <= SHAKE[0][0], "eyes must be shut before the shake"
    assert TRACKS["shut"][1][0] >= SHAKE[-1][1], "eyes must not open mid-shake"
    assert sample(SHAKE[2][0]).shut > 0.999, "both eyes shut through the shake"

    # 4. the amplitude decays, every traverse crosses centre, and it lands on 0.
    peaks = [b for _, _, _, b, _ in SHAKE[1:-1]]
    assert all(peaks[i] * peaks[i + 1] < 0 for i in range(len(peaks) - 1)), \
        "traverses must alternate sides"
    mags = [abs(p) for p in peaks]
    assert all(mags[i] > mags[i + 1] for i in range(len(mags) - 1)), \
        "the shake must decay: %s" % mags
    assert SHAKE[-1][3] == 0.0 and abs(sample(SHAKE[-1][1]).turn) < 1e-9, \
        "must settle dead centre"
    assert len(peaks) >= 4, "fewer than four traverses does not read as a shake"

    # 5. roll is derived from yaw, not keyframed.
    for t in (1700, 1900, 2100, 2300):
        assert abs(sample(t).tilt - sample(t).turn * TILT_K) < 1e-9

    # 6. the whole gesture sits inside the hold.
    assert TRACKS["shut"][0][0] > 900, "gesture must start after the mark has arrived"
    assert TRACKS["shut"][1][1] < 3030, "gesture must finish before the exit"

    # 7. level, eyes open, before the exit.
    e = sample(3030)
    assert abs(e.turn) < 1e-9 and abs(e.tilt) < 1e-9, "head must be level at the exit"
    assert e.shut < 1e-9, "eyes must be open again before they close for the exit"

    # 8. this is not the save banner.
    assert all(f.wink == 0.0 for _, f in timeline(fps=200)), "no wink in the error banner"

    # 9. every audio cue still lands on a beat.
    marks = {m for k in TRACKS for seg in TRACKS[k] for m in (seg[0], seg[1])}
    for c in SOUND_CUES:
        assert any(abs(c - mk) <= 10 for mk in marks), \
            "sound cue at %d ms has no beat within 10 ms" % c

    shut_ms = [t for t, f in timeline(fps=1000) if f.shut > 0.999]
    return max(shut_ms) - min(shut_ms), len(peaks)


if __name__ == "__main__":
    held, n = assert_invariants()
    print("total %d ms   eyes held shut %d ms   %d traverses   field %s"
          % (TOTAL_MS, held, n, FIELD))
    print("\n%6s %6s %6s %6s %7s %7s %7s" %
          ("t", "ring", "eyes", "shut", "turn", "tilt", "lag"))
    for t, f in timeline(fps=8):
        print("%6.0f %6.2f %6.2f %6.2f %7.2f %7.2f %7.2f"
              % (t, f.ring, f.eyes, f.shut, f.turn, f.tilt, f.horn_lag))
