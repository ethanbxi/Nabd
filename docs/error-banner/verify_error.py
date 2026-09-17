# -*- coding: utf-8 -*-
"""1-for-1 check for the error banner.

    python verify_error.py

Five things, in order of how much they tell you:

  1. Both assert_invariants() -- the timeline rules.
  2. assert_shared_with_save() -- every pose inside the entry and exit windows
     is the SAME PICTURE as the save banner's. This is the claim the design
     rests on: one product, two outcomes.
  3. The save banner is untouched. pose_svg gained a `shut` channel; this
     proves no frame of the existing banner moved.
  4. Every channel of sample(t) against reference/timeline.csv at 4 ms.
  5. assert_raster() -- the rasteriser actually renders what the timeline moves,
     including the shut eyes.

Exit 0 means this tree is the reference error banner.
"""
from __future__ import annotations
import csv, pathlib, sys

TOL = 1e-6
REF = pathlib.Path(__file__).resolve().parent / "reference" / "timeline.csv"
CHANNELS = ["alpha", "ring", "horns", "eyes", "copy", "drain", "line",
            "tilt", "turn", "squash", "wink", "shut", "horn_lag"]
INTS = ["w", "h"]


def main():
    import nabd_banner_error as E, nabd_mark_frames_error as F, nabd_mark as M

    print("1. invariants")
    held, n = E.assert_invariants()
    count = F.assert_invariants()
    print("   timeline   total %d ms, eyes held shut %d ms, %d traverses, field %s"
          % (E.TOTAL_MS, held, n, E.FIELD))
    print("   flipbook   %d frames per scale, windows %s"
          % (count, ", ".join("%d-%d" % w for w in F.MOTION)))

    print("\n2. shared with the save banner")
    shared = F.assert_shared_with_save()
    print("   %d poses in the entry and exit windows are identical pictures" % shared)

    print("\n3. the save banner is untouched")
    n, short = _save_banner_unchanged()
    if n is None:
        print("   reference/save-poses.sha256 missing -- CANNOT verify this")
        return 1
    print("   %d of its poses re-render to the same bytes (sha %s...)" % (n, short))

    print("\n4. sample(t) vs reference, every 4 ms")
    if not REF.exists():
        print("   reference/timeline.csv missing -- cannot do the 1-for-1 check")
        return 1
    bad, rows = [], 0
    with REF.open() as fh:
        for row in csv.DictReader(fh):
            rows += 1
            t = float(row["t"])
            f = E.sample(t)
            for k in CHANNELS:
                a, b = getattr(f, k), float(row[k])
                if abs(a - b) > TOL:
                    bad.append((t, k, b, a))
            for k in INTS:
                if getattr(f, k) != int(row[k]):
                    bad.append((t, k, int(row[k]), getattr(f, k)))
            if F.index_for(t) != int(row["frame"]):
                bad.append((t, "frame", int(row["frame"]), F.index_for(t)))
    _report(bad, rows)

    print("\n5. raster")
    F.assert_raster()
    print("   ring, horns, eyes and the shut channel all reach the pixels")

    if bad:
        print("\nFAIL -- this is not the reference error banner.")
        return 1
    print("\nOK -- 1 for 1 with the reference.")
    return 0


def _save_banner_unchanged():
    """Recompute the save banner's poses with the patched nabd_mark.

    Checked against a digest taken from the ORIGINAL module, stored in
    reference/save-poses.sha256 -- so this works after the patched file has
    replaced the old one in the repo, which is exactly when it matters. Diffing
    against a copy of the old file would silently skip the moment it is gone.
    """
    import hashlib
    import nabd_banner as S, nabd_mark as M
    want = pathlib.Path(__file__).resolve().parent / "reference" / "save-poses.sha256"
    if not want.exists():
        return None, None
    line = [l for l in want.read_text().splitlines() if not l.startswith("#")][0]
    digest, count = line.split()
    h = hashlib.sha256()
    n, t = 0, 0
    while t < S.TOTAL_MS:
        h.update(M.pose_svg(S.sample(float(t)), size=200).encode())
        n += 1
        t += 2
    assert n == int(count), "expected %s frames, sampled %d" % (count, n)
    assert h.hexdigest() == digest, (
        "the save banner MOVED. pose_svg now renders it differently -- the "
        "`shut` channel must leave every existing frame byte-identical.\n"
        "   expected %s\n   got      %s" % (digest, h.hexdigest()))
    return n, digest[:12]


def _report(bad, rows):
    if not bad:
        print("   %d rows, nothing differs by more than %g" % (rows, TOL))
        return
    print("   %d mismatches across %d rows. First 12:" % (len(bad), rows))
    print("   %8s %-9s %12s %12s" % ("t(ms)", "channel", "expected", "got"))
    for t, k, want, got in bad[:12]:
        print("   %8.0f %-9s %12s %12s" % (t, k, want, got))
    print("   first divergence at %.0f ms, in: %s"
          % (min(b[0] for b in bad), ", ".join(sorted({b[1] for b in bad}))))


if __name__ == "__main__":
    sys.exit(main())
