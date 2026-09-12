"""The buffer must survive an ffmpeg crash.

Desktop Duplication throws DXGI_ERROR_ACCESS_LOST whenever something takes the
display (exclusive fullscreen, a mode switch, a UAC prompt). ffmpeg dies and is
restarted; footage recorded before that must still be there afterwards.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

cfg = nabd.load_config()
cfg["clip_seconds"] = 60
cfg["output_dir"] = str(Path(__file__).resolve().parent / "out")
ffmpeg = nabd.find_ffmpeg()

rec = nabd.Recorder(cfg, ffmpeg)
clip = nabd.Clipper(cfg, ffmpeg, rec)
rec.clear_buffer()
rec.start()
results = {}

try:
    print("filling buffer for 16s...")
    time.sleep(16)
    before = clip.segments()
    first_pid = rec.proc.pid
    print(f"  segments={len(before)}  session={rec.session}  ffmpeg pid={first_pid}")
    oldest_before = before[0].name if before else None

    # Simulate the access-loss crash.
    print(f"\nkilling ffmpeg {first_pid} (simulating DXGI_ERROR_ACCESS_LOST)")
    subprocess.run(["taskkill", "/F", "/PID", str(first_pid)],
                   capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)

    for _ in range(40):
        time.sleep(0.5)
        if rec.running and rec.proc.pid != first_pid:
            break
    recovered = rec.running and rec.proc.pid != first_pid
    results["ffmpeg restarted"] = recovered
    print(f"  restarted={recovered}  new pid={rec.proc.pid if rec.running else None}"
          f"  session={rec.session}")

    after = clip.segments()
    survived = [p for p in after if p.name in {b.name for b in before}]
    results["old segments survived"] = len(survived) >= len(before) - 1
    print(f"\n  segments before kill : {len(before)}")
    print(f"  segments still there : {len(survived)}")
    print(f"  oldest before        : {oldest_before}")
    print(f"  oldest now           : {after[0].name if after else None}")

    print("\nrecording 10s more, then clipping across the seam...")
    time.sleep(10)
    sessions = {clip._session_of(p) for p in clip.segments()}
    results["buffer spans 2 sessions"] = len(sessions) >= 2
    print(f"  sessions present: {sorted(sessions)}")

    done, out = [], {}
    clip.save(on_done=lambda ok, d: (out.update(ok=ok, detail=d), done.append(1)))
    for _ in range(80):
        if done:
            break
        time.sleep(0.5)
    results["clip saved"] = out.get("ok", False)
    print(f"  save: {out}")

    if out.get("ok"):
        path = sorted(Path(cfg["output_dir"]).glob("*.mp4"))[-1]
        probe = subprocess.run(
            [ffmpeg.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error",
             "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
        dur = float(probe.stdout.strip() or 0)
        print(f"  clip duration: {dur:.1f}s")
        # Pre-crash footage must be in there: ~26s of material was recorded.
        results["clip spans the crash"] = dur > 18
finally:
    rec.stop()

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if results and all(results.values()) else 1)
