"""How fast can ddagrab actually deliver *new* frames?

Runs bare ffmpeg (no Nab'd pipeline) against a full-screen 60fps animation and
reads dup_frames from -progress. A duplicate means ddagrab had nothing new to
hand over at that tick, so the duplicate share is the gap between the frame rate
the file claims and the frame rate you actually see.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
SECONDS = 10


def animate():
    """Full-screen 60fps source, so the whole desktop changes every frame."""
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def run(label, filter_args, extra=None):
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-stats_period", "1",
           "-init_hw_device", "d3d11va",
           "-filter_complex", filter_args]
    cmd += (extra or [])
    cmd += ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23",
            "-bf", "0", "-rc-lookahead", "0",
            "-t", str(SECONDS), "-f", "null", "NUL"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            creationflags=nabd.CREATE_NO_WINDOW)
    fields = {}
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k] = v.strip()
    proc.wait()

    try:
        frames = int(fields.get("frame", 0))
        dup = int(fields.get("dup_frames", 0))
        fps = float(fields.get("fps", 0) or 0)
    except ValueError:
        print(f"  {label:<34} could not parse progress")
        return None

    real = frames - dup
    share = (dup / frames * 100) if frames else 0
    effective = real / SECONDS
    print(f"  {label:<34} {frames:>4} frames  {dup:>4} dup ({share:4.1f}%)  "
          f"-> {effective:5.1f} real fps   [encoder said {fps:.1f}]")
    return effective


print(f"Full-screen 60fps animation, {SECONDS}s per configuration.\n")
player = animate()
time.sleep(4)
try:
    print("Capture frame rate:")
    for rate in (30, 60, 120):
        run(f"framerate={rate}, draw_mouse=1",
            f"ddagrab=output_idx=0:framerate={rate}:draw_mouse=1")

    print("\nCursor compositing:")
    run("framerate=60, draw_mouse=0",
        "ddagrab=output_idx=0:framerate=60:draw_mouse=0")

    print("\nWithout duplicate padding (true delivery rate):")
    run("framerate=60, dup_frames=0",
        "ddagrab=output_idx=0:framerate=60:dup_frames=0")
    run("framerate=120, dup_frames=0",
        "ddagrab=output_idx=0:framerate=120:dup_frames=0")
finally:
    try:
        player.kill()
    except OSError:
        pass
print("\nIf 'real fps' stays well under the requested rate everywhere, ddagrab "
      "is the limit rather than the encoder.")
