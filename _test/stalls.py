"""Where do the missing frames go?

Average rate looks fine while playback judders when frames vanish in bursts.
This locates the gaps and tests whether the 2-second segment muxer is causing
them, by capturing the same animation with and without segmenting.
"""
import json
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
SECONDS = 16
FPS = 60
SEG = 2


def animate():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def base_cmd():
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-init_hw_device", "d3d11va",
            "-filter_complex",
            f"ddagrab=output_idx=0:framerate={FPS}:draw_mouse=1",
            "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23",
            "-bf", "0", "-rc-lookahead", "0", "-delay", "0",
            "-t", str(SECONDS)]


def capture_segmented(tag, flush):
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.ts"):
        old.unlink()
    cmd = base_cmd() + [
        "-g", str(FPS * SEG), "-forced-idr", "1",
        "-force_key_frames", f"expr:gte(t,n_forced*{SEG})",
        "-f", "segment", "-segment_time", str(SEG),
        "-segment_format", "mpegts", "-reset_timestamps", "1"]
    if flush:
        cmd += ["-flush_packets", "1"]
    cmd += [str(d / "s_%04d.ts")]
    subprocess.run(cmd, capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)

    files = sorted(d.glob("*.ts"))
    listing = d / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in files),
                       encoding="utf-8")
    out = d / "joined.mp4"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", str(listing), "-c", "copy", str(out)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    return out


def capture_single(tag):
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    out = d / "single.mp4"
    cmd = base_cmd() + ["-g", str(FPS * SEG), str(out)]
    subprocess.run(cmd, capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    return out


def gaps(path):
    res = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "json", str(path)],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW)
    times = sorted(float(f["pts_time"]) for f in
                   json.loads(res.stdout).get("frames", []) if "pts_time" in f)
    ideal = 1.0 / FPS
    out = []
    for a, b in zip(times, times[1:]):
        d = b - a
        if d > ideal * 1.5:
            out.append((a, d))
    return times, out


def report(label, path):
    if not path.exists():
        print(f"\n=== {label} ===\n  capture failed")
        return
    times, big = gaps(path)
    if not times:
        print(f"\n=== {label} ===\n  no frames")
        return
    span = times[-1] - times[0]
    lost = sum(d - 1.0 / FPS for _, d in big)
    print(f"\n=== {label} ===")
    print(f"  frames {len(times)} over {span:.2f}s -> {len(times)/span:.1f} fps")
    print(f"  stalls (>25ms gap): {len(big)}   time lost to them: {lost*1000:.0f} ms")
    if big:
        worst = sorted(big, key=lambda x: -x[1])[:6]
        print("  worst gaps:")
        for at, d in worst:
            # Distance to the nearest segment boundary.
            near = abs((at % SEG) - SEG) if (at % SEG) > SEG / 2 else (at % SEG)
            print(f"    at t={at:6.2f}s  gap {d*1000:6.1f} ms "
                  f"({d*FPS:.1f} frames)   {near*1000:5.0f} ms from a "
                  f"{SEG}s boundary")
        at_boundary = sum(1 for at, _ in big
                          if min(at % SEG, SEG - (at % SEG)) < 0.1)
        print(f"  stalls within 100ms of a segment boundary: "
              f"{at_boundary}/{len(big)}")


print(f"Full-screen {FPS}fps animation, {SECONDS}s per configuration.")
player = animate()
time.sleep(4)
try:
    report("segmented + flush_packets (as shipped)",
           capture_segmented("seg_flush", True))
    time.sleep(1)
    report("segmented, no flush_packets", capture_segmented("seg_noflush", False))
    time.sleep(1)
    report("single file, no segmenting", capture_single("single"))
finally:
    try:
        player.kill()
    except OSError:
        pass
