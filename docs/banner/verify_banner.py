# -*- coding: utf-8 -*-
"""1-for-1 check: does this tree reproduce the reference banner exactly?

    python verify_banner.py

Runs three things, in order of how much they tell you:

  1. Both assert_invariants() -- the design rules that have each been broken
     at least once.
  2. Every channel of sample(t) against reference/timeline.csv at 4 ms.
     This is the real 1-for-1 test: 1,030 rows x 15 channels. A retimed beat,
     a swapped easing curve or a changed dial all show up here as a numeric
     diff with the exact millisecond it starts.
  3. index_for(t) against the same file, so the flipbook contract matches too.

Exit code 0 means this tree is the reference animation. Anything else prints
the first divergences and exits 1.
"""
from __future__ import annotations
import csv, pathlib, sys

TOL = 1e-6
REF = pathlib.Path(__file__).resolve().parent / "reference" / "timeline.csv"
CHANNELS = ["alpha", "ring", "horns", "eyes", "copy", "drain", "line",
            "tilt", "turn", "squash", "wink", "horn_lag"]
INTS = ["w", "h"]


def main():
    import nabd_banner as B, nabd_mark_frames as F

    print("1. invariants")
    held = B.assert_invariants()
    count = F.assert_invariants()
    print("   nabd_banner      total %d ms, eye held shut %d ms, sound cues land"
          % (B.TOTAL_MS, held))
    print("   nabd_mark_frames %d frames per scale, windows %s"
          % (count, ", ".join("%d-%d" % w for w in F.MOTION)))

    if not REF.exists():
        print("\n   reference/timeline.csv missing -- cannot do the 1-for-1 check")
        return 1

    print("\n2. sample(t) vs reference, every 4 ms")
    bad, rows = [], 0
    with REF.open() as fh:
        for row in csv.DictReader(fh):
            rows += 1
            t = float(row["t"])
            f = B.sample(t)
            for k in CHANNELS:
                a, b = getattr(f, k), float(row[k])
                if abs(a - b) > TOL:
                    bad.append((t, k, b, a))
            for k in INTS:
                a, b = getattr(f, k), int(row[k])
                if a != b:
                    bad.append((t, k, b, a))
    _report(bad, rows, "channel")

    print("\n3. index_for(t) vs reference")
    bad2 = []
    with REF.open() as fh:
        for row in csv.DictReader(fh):
            t = float(row["t"])
            got = F.index_for(t)
            if got != int(row["frame"]):
                bad2.append((t, "frame", int(row["frame"]), got))
    _report(bad2, rows, "frame index")

    if bad or bad2:
        print("\nFAIL -- this is not the reference animation.")
        return 1
    print("\nOK -- 1 for 1 with the reference.")
    return 0


def _report(bad, rows, what):
    if not bad:
        print("   %d rows, no %s differs by more than %g" % (rows, what, TOL))
        return
    print("   %d mismatches across %d rows. First 12:" % (len(bad), rows))
    print("   %8s %-9s %12s %12s" % ("t(ms)", what, "expected", "got"))
    for t, k, want, got in bad[:12]:
        print("   %8.0f %-9s %12s %12s" % (t, k, want, got))
    first = min(b[0] for b in bad)
    names = sorted({b[1] for b in bad})
    print("   first divergence at %.0f ms, in: %s" % (first, ", ".join(names)))


if __name__ == "__main__":
    sys.exit(main())
