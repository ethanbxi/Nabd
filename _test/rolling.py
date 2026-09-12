"""Consecutive clips must be different windows, not the same footage again.

Uses a short buffer so it fills quickly, and animates the screen so footage from
different moments is genuinely distinguishable.
"""
import hashlib
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
OUT = Path(__file__).resolve().parent / "out"
WINDOW = 20


def animate():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def duration(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def first_frame_hash(path):
    png = path.with_suffix(".firstframe.png")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
         "-frames:v", "1", "-vf", "scale=160:-1", str(png)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    if not png.exists():
        return None
    digest = hashlib.sha1(png.read_bytes()).hexdigest()[:12]
    png.unlink(missing_ok=True)
    return digest


cfg = nabd.load_config()
cfg["clip_seconds"] = WINDOW
cfg["output_dir"] = str(OUT)
cfg["save_delay"] = 2.0

rec = nabd.Recorder(cfg, ffmpeg)
clip = nabd.Clipper(cfg, ffmpeg, rec)
OUT.mkdir(parents=True, exist_ok=True)

# Leave a fake orphan behind to prove the sweeper collects it.
orphan = nabd.BUFFER_DIR / ".stage_test_orphan"
orphan.mkdir(parents=True, exist_ok=True)
(orphan / "junk.ts").write_bytes(b"x" * 1024)
import os as _os
old = time.time() - 3600
_os.utime(orphan, (old, old))

rec.clear_buffer()
rec.start()
player = animate()
results = {}
saved = []
try:
    print(f"buffer window {WINDOW}s; filling past it...")
    time.sleep(WINDOW + 12)

    for label, wait in (("A", 0), ("B", 22)):
        if wait:
            print(f"waiting {wait}s before clip {label}...")
            time.sleep(wait)
        before = {p.name for p in OUT.glob("*.mp4")}
        done = []
        clip.save(on_done=lambda ok, d: done.append(ok))
        for _ in range(80):
            if done:
                break
            time.sleep(0.25)
        if not done or not done[0]:
            print(f"clip {label} failed to save")
            continue
        path = max((p for p in OUT.glob("*.mp4") if p.name not in before),
                   key=lambda p: p.stat().st_mtime)
        saved.append((label, path, duration(path), first_frame_hash(path)))
        print(f"  clip {label}: {path.name}  {saved[-1][2]:.1f}s  "
              f"first frame {saved[-1][3]}")

    clip.prune()
finally:
    try:
        player.kill()
    except OSError:
        pass
    rec.stop()

results["two clips saved"] = len(saved) == 2
if len(saved) == 2:
    (_, _, dur_a, hash_a), (_, _, dur_b, hash_b) = saved
    # A full buffer must stop growing, unlike a buffer still filling.
    results["clip A is one window"] = abs(dur_a - WINDOW) <= 4
    results["clip B is one window"] = abs(dur_b - WINDOW) <= 4
    results["B did not grow"] = abs(dur_b - dur_a) <= 4
    results["clips start at different moments"] = (
        hash_a is not None and hash_b is not None and hash_a != hash_b)

results["orphan staging swept"] = not orphan.exists()

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if results and all(results.values()) else 1)
