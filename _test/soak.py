"""Long-run check: A/V drift, ring-buffer cap, and memory stability."""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

SOAK_SECONDS = 180
WINDOW = 20  # small buffer so pruning is exercised

cfg = nabd.load_config()
cfg["clip_seconds"] = WINDOW
cfg["output_dir"] = str(Path(__file__).resolve().parent / "out")
ffmpeg = nabd.find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")

rec = nabd.Recorder(cfg, ffmpeg)
clip = nabd.Clipper(cfg, ffmpeg, rec)
rec.clear_buffer()
rec.start()
proc_pid = rec.proc.pid

expected_cap = int(WINDOW / cfg["segment_seconds"]) + 4
print(f"ring cap should settle at {expected_cap} segments\n")

peak_segments = 0
peak_disk = 0
for i in range(SOAK_SECONDS):
    time.sleep(1)
    clip.prune()
    if i % 20 == 19:
        segs = clip.segments()
        disk = sum(p.stat().st_size for p in segs if p.exists()) / 1048576
        peak_segments = max(peak_segments, len(segs))
        peak_disk = max(peak_disk, disk)
        rss = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process -Id {proc_pid}).WorkingSet64"],
            capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW,
        ).stdout.strip()
        rss_mb = int(rss) / 1048576 if rss.isdigit() else -1
        print(f"  t={i+1:>3}s  segments={len(segs):>3}  disk={disk:>6.1f}MB  "
              f"ffmpeg_rss={rss_mb:>6.1f}MB  padded={rec.audio.padded_seconds:.2f}s")

print(f"\npeak segments={peak_segments} (cap {expected_cap})  peak disk={peak_disk:.1f}MB")

done = []
result = {}
clip.save(on_done=lambda ok, d: (result.update(ok=ok, detail=d), done.append(1)))
for _ in range(60):
    if done:
        break
    time.sleep(0.5)
rec.stop()

if not result.get("ok"):
    print("FAIL:", result)
    sys.exit(1)

out = sorted(Path(cfg["output_dir"]).glob("*.mp4"))[-1]
info = json.loads(subprocess.run(
    [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(out)],
    capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW).stdout)

durations = {}
for s in info["streams"]:
    durations[s["codec_type"]] = float(s.get("duration", 0))
    print(f"{s['codec_type']:<6} start={float(s.get('start_time',0)):+.3f}s "
          f"duration={float(s.get('duration',0)):.3f}s")

skew = abs(durations.get("video", 0) - durations.get("audio", 0))
print(f"\nA/V duration skew: {skew*1000:.0f} ms")

ok = True
if peak_segments > expected_cap + 2:
    print(f"FAIL: ring buffer not capped ({peak_segments} > {expected_cap})")
    ok = False
if skew > 0.25:
    print(f"FAIL: A/V skew {skew:.3f}s exceeds 250ms")
    ok = False
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

