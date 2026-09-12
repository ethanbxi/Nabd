"""Are the frames in a clip evenly spaced?

Average fps can look perfect while individual frames land at irregular
timestamps, which plays back as judder regardless of frame count. Animates the
screen so the capture has genuinely changing content, then measures the gap
between consecutive frames.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

RECORD = 14
OUT = Path(__file__).resolve().parent / "out"
ffmpeg = nabd.find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe")
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")


def animate():
    """Something that repaints every frame, so DDA has real work to deliver."""
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60",
         "-loglevel", "quiet", "-noborder", "-x", "1280", "-y", "720",
         "-left", "200", "-top", "200"],
        creationflags=nabd.CREATE_NO_WINDOW)


def frame_times(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    frames = json.loads(res.stdout).get("frames", [])
    times = []
    for f in frames:
        try:
            times.append(float(f["pts_time"]))
        except (KeyError, ValueError):
            pass
    return sorted(times)


def stream_info(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate,avg_frame_rate,nb_frames", "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    return json.loads(res.stdout)["streams"][0]


def analyse(path, target_fps):
    info = stream_info(path)
    times = frame_times(path)
    print(f"\n  r_frame_rate   : {info.get('r_frame_rate')}")
    print(f"  avg_frame_rate : {info.get('avg_frame_rate')}")
    print(f"  frames         : {len(times)}")
    if len(times) < 10:
        print("  not enough frames to analyse")
        return None

    ideal = 1.0 / target_fps
    deltas = [b - a for a, b in zip(times, times[1:])]
    deltas.sort()
    n = len(deltas)
    median = deltas[n // 2]
    p99 = deltas[int(n * 0.99)]
    # A frame arriving more than 1.5 ideal intervals late reads as a hitch.
    late = sum(1 for d in deltas if d > ideal * 1.5)
    jitter = sum(abs(d - ideal) for d in deltas) / n

    print(f"  ideal gap      : {ideal*1000:.2f} ms")
    print(f"  median gap     : {median*1000:.2f} ms")
    print(f"  p99 gap        : {p99*1000:.2f} ms")
    print(f"  mean jitter    : {jitter*1000:.2f} ms")
    print(f"  long gaps      : {late} of {n} ({late/n*100:.1f}%)")
    return {"late_pct": late / n * 100, "jitter_ms": jitter * 1000,
            "avg_rate": info.get("avg_frame_rate")}


def capture(label, extra_out_args=None):
    cfg = nabd.load_config()
    cfg["clip_seconds"] = 120
    cfg["output_dir"] = str(OUT)
    cfg["save_delay"] = 2.0

    rec = nabd.Recorder(cfg, ffmpeg)
    clip = nabd.Clipper(cfg, ffmpeg, rec)

    if extra_out_args is not None:
        original = rec._build_cmd

        def patched(mic):
            cmd = original(mic)
            # Inject just before the output path.
            return cmd[:-1] + extra_out_args + cmd[-1:]
        rec._build_cmd = patched

    OUT.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in OUT.glob("*.mp4")}
    rec.clear_buffer()
    rec.start()
    time.sleep(RECORD)

    done = []
    clip.save(on_done=lambda ok, d: done.append(ok))
    for _ in range(80):
        if done:
            break
        time.sleep(0.25)
    health = dict(rec.health)
    rec.stop()
    if not done or not done[0]:
        print(f"[{label}] save failed")
        return None

    path = max((p for p in OUT.glob("*.mp4") if p.name not in before),
               key=lambda p: p.stat().st_mtime)
    print(f"\n=== {label} ===")
    print(f"  capture health : {health.get('fps', 0):.1f} fps, "
          f"{health.get('dup', 0)} duplicated")
    return analyse(path, cfg["fps"])


print("Animating the screen so capture has real content to deliver...")
player = animate()
time.sleep(3)
try:
    current = capture("as shipped")
    time.sleep(2)
    forced = capture("with -fps_mode cfr -r 60",
                     ["-fps_mode", "cfr", "-r", "60"])
finally:
    try:
        player.kill()
    except OSError:
        pass

print("\n--- verdict ---")
for name, r in (("as shipped", current), ("forced CFR", forced)):
    if r:
        print(f"  {name:<12} long gaps {r['late_pct']:5.1f}%   "
              f"jitter {r['jitter_ms']:5.2f} ms   avg_rate {r['avg_rate']}")
