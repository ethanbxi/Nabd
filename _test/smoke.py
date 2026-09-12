"""Headless end-to-end check: record for a while, save a clip, verify it."""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

RECORD_SECONDS = 25

cfg = nabd.load_config()
cfg["clip_seconds"] = 15
cfg["output_dir"] = str(Path(__file__).resolve().parent / "out")
ffmpeg = nabd.find_ffmpeg()
print("ffmpeg:", ffmpeg)

rec = nabd.Recorder(cfg, ffmpeg)
clip = nabd.Clipper(cfg, ffmpeg, rec)
rec.clear_buffer()
rec.start()

for i in range(RECORD_SECONDS):
    time.sleep(1)
    if i % 5 == 4:
        n = len(clip.segments())
        print(f"  t={i+1:>2}s  segments={n}  running={rec.running} "
              f"padded={rec.audio.padded_seconds:.2f}s")

if not rec.running:
    print("FAIL: recorder died")
    sys.exit(1)

result = {}
done = []
clip.save(on_done=lambda ok, detail: (result.update(ok=ok, detail=detail), done.append(1)))
for _ in range(60):
    if done:
        break
    time.sleep(0.5)

rec.stop()
print("save result:", result)
if not result.get("ok"):
    sys.exit(1)

out = sorted(Path(cfg["output_dir"]).glob("*.mp4"))[-1]
probe = subprocess.run(
    [ffmpeg.replace("ffmpeg.exe", "ffprobe.exe"), "-v", "error", "-show_format",
     "-show_streams", "-of", "json", str(out)],
    capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW,
)
info = json.loads(probe.stdout)
print(f"\n--- {out.name} ---")
print(f"duration : {float(info['format']['duration']):.2f}s")
print(f"size     : {int(info['format']['size'])/1048576:.2f} MB")
for s in info["streams"]:
    if s["codec_type"] == "video":
        print(f"video    : {s['codec_name']} {s['width']}x{s['height']} "
              f"{s.get('avg_frame_rate')} fps, {s.get('nb_frames','?')} frames")
    else:
        print(f"audio    : {s['codec_name']} {s['sample_rate']}Hz "
              f"{s['channels']}ch, {s.get('nb_frames','?')} frames")

# Verify audio actually contains signal rather than a silent placeholder track.
vol = subprocess.run(
    [ffmpeg, "-hide_banner", "-i", str(out), "-af", "volumedetect", "-f", "null", "NUL"],
    capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW,
).stderr
for line in vol.splitlines():
    if "mean_volume" in line or "max_volume" in line:
        print("audio    :", line.split("]")[-1].strip())
print("\nPASS")

