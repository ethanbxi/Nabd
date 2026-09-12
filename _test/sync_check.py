"""Sanity-check the sync source and the detector before trusting a measurement.

Run the same analysis against the generated source, where flashes and bursts are
simultaneous by construction. Anything other than ~0 ms means the detector is
wrong, not the recording.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_measure as S  # noqa: E402

S.build_source()
print(f"source: {S.SOURCE}")

lum = S.brightness(S.SOURCE)
print(f"\nframes: {len(lum)}   min={min(lum)} max={max(lum)}")
bright = [(i / S.FPS, v) for i, v in enumerate(lum) if v > 128]
print(f"bright frames: {len(bright)}")
print("  " + ", ".join(f"{t:.3f}s({v})" for t, v in bright[:14]))

samples = S.envelope(S.SOURCE)
win = 240
loud = []
for i in range(0, len(samples) - win, win):
    chunk = samples[i:i + win]
    amp = max(abs(min(chunk)), abs(max(chunk)))
    if amp > 3000:
        loud.append((i / 48000, amp))
print(f"\nloud windows: {len(loud)}")
print("  " + ", ".join(f"{t:.3f}s" for t, _ in loud[:14]))

offsets = S.analyse(S.SOURCE)
print(f"\ndetector on the source -> {offsets}")
if offsets:
    med = sorted(offsets)[len(offsets) // 2]
    print(f"median {med*1000:+.0f} ms (must be near 0 for the detector to be trusted)")
