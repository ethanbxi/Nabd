"""Produce a few short clips so the recent strip has something to show."""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")

cfg = nabd.load_config()
cfg["clip_seconds"] = 10
cfg["save_delay"] = 2.0
cfg["reset_after_clip"] = True   # so each clip is distinct footage

player = subprocess.Popen(
    [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
     "-loglevel", "quiet", "-fs", "-autoexit"],
    creationflags=nabd.CREATE_NO_WINDOW)

rec = nabd.Recorder(cfg, ffmpeg)
clip = nabd.Clipper(cfg, ffmpeg, rec)
rec.clear_buffer()
rec.start()
try:
    for n in range(3):
        time.sleep(13)
        done = []
        clip.save(on_done=lambda ok, d: done.append((ok, d)))
        for _ in range(60):
            if done:
                break
            time.sleep(0.25)
        print(f"  clip {n + 1}: {done[0] if done else 'timed out'}")
finally:
    rec.stop()
    try:
        player.kill()
    except OSError:
        pass

for p in nabd.recent_clips(cfg["output_dir"]):
    print(f"  {p.name}  {nabd.clip_summary(p)}")
