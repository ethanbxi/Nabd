"""With 'start a fresh buffer after each clip', clips must not overlap.

The second clip should only contain footage recorded since the first one, so it
is markedly shorter when taken soon after.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
OUT = Path(__file__).resolve().parent / "out"
WINDOW = 20
GAP = 10


def duration(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def take(clip, label):
    before = {p.name for p in OUT.glob("*.mp4")}
    done = []
    clip.save(on_done=lambda ok, d: done.append(ok))
    for _ in range(80):
        if done:
            break
        time.sleep(0.25)
    if not done or not done[0]:
        print(f"  clip {label}: FAILED to save")
        return None
    path = max((p for p in OUT.glob("*.mp4") if p.name not in before),
               key=lambda p: p.stat().st_mtime)
    d = duration(path)
    segs = len(list(nabd.BUFFER_DIR.glob("seg_*.ts")))
    print(f"  clip {label}: {d:5.1f}s   segments left in buffer: {segs}")
    return d


def run(reset_after):
    cfg = nabd.load_config()
    cfg["clip_seconds"] = WINDOW
    cfg["output_dir"] = str(OUT)
    cfg["save_delay"] = 2.0
    cfg["reset_after_clip"] = reset_after

    rec = nabd.Recorder(cfg, ffmpeg)
    clip = nabd.Clipper(cfg, ffmpeg, rec)
    OUT.mkdir(parents=True, exist_ok=True)
    rec.clear_buffer()
    rec.start()
    try:
        mode = "reset after clip" if reset_after else "rolling buffer"
        print(f"\n=== {mode} ===")
        time.sleep(WINDOW + 8)
        a = take(clip, "A")
        time.sleep(GAP)
        b = take(clip, "B")
    finally:
        rec.stop()
    return a, b


results = {}
roll_a, roll_b = run(False)
time.sleep(2)
reset_a, reset_b = run(True)

print("\n--- comparison ---")
print(f"  rolling buffer : A {roll_a:.1f}s   B {roll_b:.1f}s "
      f"(B should be a full window again)")
print(f"  reset on clip  : A {reset_a:.1f}s   B {reset_b:.1f}s "
      f"(B should be about {GAP}s)")

results["rolling: B is a full window"] = abs(roll_b - WINDOW) <= 5
results["reset: A is a full window"] = abs(reset_a - WINDOW) <= 5
results["reset: B only covers the gap"] = reset_b <= GAP + 5
results["reset: B is shorter than rolling B"] = reset_b < roll_b - 3

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if all(results.values()) else 1)
