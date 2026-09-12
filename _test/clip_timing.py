"""Does a clip actually reach the moment the hotkey was pressed?

Records for a fixed stretch, saves, and compares the clip's duration against
how long recording had been running. Anything materially short means the tail
never reached disk - the bug where clips ended just before the keypress.

Runs with the settle delay off and on so the difference is measurable.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

RECORD = 24
OUT = Path(__file__).resolve().parent / "out"
ffmpeg = nabd.find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")


def duration(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def trial(save_delay):
    cfg = nabd.load_config()
    cfg["clip_seconds"] = 120          # well above RECORD, so nothing is capped
    cfg["output_dir"] = str(OUT)
    cfg["save_delay"] = save_delay

    rec = nabd.Recorder(cfg, ffmpeg)
    clip = nabd.Clipper(cfg, ffmpeg, rec)
    rec.clear_buffer()
    before = {p.name for p in OUT.glob("*.mp4")} if OUT.exists() else set()

    rec.start()
    started = time.time()
    time.sleep(RECORD)

    pressed = time.time()
    elapsed_at_press = pressed - started

    done, result = [], {}
    clip.save(on_done=lambda ok, d: (result.update(ok=ok), done.append(1)))
    for _ in range(120):
        if done:
            break
        time.sleep(0.25)
    health = dict(rec.health)
    rec.stop()

    if not result.get("ok"):
        print(f"  save_delay={save_delay}: SAVE FAILED")
        return None

    path = max((p for p in OUT.glob("*.mp4") if p.name not in before),
               key=lambda p: p.stat().st_mtime)
    dur = duration(path)
    reach = dur - elapsed_at_press   # >0 means it covers past the keypress
    print(f"  save_delay={save_delay}s: recorded {elapsed_at_press:.1f}s, "
          f"clip {dur:.1f}s  ->  reaches {reach:+.1f}s relative to the keypress")
    if health:
        print(f"     capture health: {health.get('fps', 0):.1f} fps, "
              f"{health.get('dup', 0)} duplicated, {health.get('drop', 0)} dropped")
    return reach


print("Measuring how close a clip gets to the moment of the keypress.")
print("Negative means footage before the keypress is missing.\n")

OUT.mkdir(parents=True, exist_ok=True)
without = trial(0.0)
time.sleep(2)
with_delay = trial(3.0)

print()
ok = True
if without is None or with_delay is None:
    ok = False
else:
    # With the settle delay the clip must cover the keypress and a little after.
    if with_delay < 0:
        print(f"FAIL: clip still ends {abs(with_delay):.1f}s before the keypress")
        ok = False
    else:
        print(f"PASS: clip reaches {with_delay:.1f}s past the keypress")
    print(f"improvement from the settle delay: {with_delay - without:+.1f}s")

sys.exit(0 if ok else 1)
