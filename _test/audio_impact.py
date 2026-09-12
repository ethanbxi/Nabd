"""Does the audio half of the pipeline cost video frames?

ddagrab and the audio filters share one filter_complex, and ffmpeg services a
filtergraph from a single thread. If an audio input blocks, the video source
does not get serviced and frames are lost. Measures video frame delivery with
each audio input added in turn.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
OUT = Path(__file__).resolve().parent / "out" / "audio_impact"
SECONDS = 12
FPS = 60
SEG = 2
RATE, CH = nabd.RATE, nabd.CHANNELS


def animate():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def build(tag, use_pipe, mic):
    d = OUT / tag
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.ts"):
        old.unlink()

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-stats_period", "1", "-y",
           "-init_hw_device", "d3d11va"]
    if use_pipe:
        cmd += ["-f", "s16le", "-ar", str(RATE), "-ac", str(CH), "-i", "pipe:0"]
    if mic:
        cmd += ["-f", "dshow", "-audio_buffer_size", "50", "-i", f"audio={mic}"]

    chains = [f"ddagrab=output_idx=0:framerate={FPS}:draw_mouse=1[v]"]
    audio_labels = []
    idx = 0
    if use_pipe:
        chains.append(f"[{idx}:a]aresample=async=1:first_pts=0[d]")
        audio_labels.append("[d]")
        idx += 1
    if mic:
        chains.append(f"[{idx}:a]aresample=async=1:first_pts=0[m]")
        audio_labels.append("[m]")

    maps = ["-map", "[v]"]
    if len(audio_labels) == 2:
        chains.append("".join(audio_labels) +
                      "amix=inputs=2:duration=first:normalize=0,"
                      "alimiter=limit=0.97[a]")
        maps += ["-map", "[a]"]
    elif len(audio_labels) == 1:
        chains.append(f"{audio_labels[0]}alimiter=limit=0.97[a]")
        maps += ["-map", "[a]"]

    cmd += ["-filter_complex", ";".join(chains)] + maps
    cmd += ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23",
            "-bf", "0", "-rc-lookahead", "0", "-delay", "0",
            "-g", str(FPS * SEG), "-forced-idr", "1",
            "-force_key_frames", f"expr:gte(t,n_forced*{SEG})"]
    if audio_labels:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", str(CH)]
    cmd += ["-t", str(SECONDS),
            "-f", "segment", "-segment_time", str(SEG),
            "-segment_format", "mpegts", "-reset_timestamps", "1",
            "-flush_packets", "1", str(d / "s_%04d.ts")]
    return cmd


def run(label, use_pipe, mic):
    cmd = build(label.replace(" ", "_"), use_pipe, mic)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE if use_pipe else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=nabd.CREATE_NO_WINDOW | nabd.ABOVE_NORMAL_PRIORITY_CLASS)

    pump = None
    if use_pipe:
        pump = nabd.DesktopAudioPump("")
        pump.start(proc.stdin)

    fields = {}
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k] = v.strip()
    proc.wait()
    if pump:
        pump.stop()

    try:
        frames = int(fields.get("frame", 0))
        dup = int(fields.get("dup_frames", 0))
    except ValueError:
        print(f"  {label:<32} parse error")
        return None
    expected = FPS * SECONDS
    real = frames - dup
    print(f"  {label:<32} {frames:>4}/{expected} frames  {dup:>3} dup  "
          f"-> {real/SECONDS:5.1f} real fps  ({real/expected*100:5.1f}% of target)")
    return real / SECONDS


mic_name = None
mics = nabd.list_microphones(ffmpeg)
for m in mics:
    low = m.lower()
    if "webcam" not in low and "stream" not in low:
        mic_name = m
        break
print(f"Full-screen {FPS}fps animation, {SECONDS}s per configuration.")
print(f"Microphone: {mic_name}\n")

player = animate()
time.sleep(4)
try:
    a = run("video only", False, None)
    time.sleep(1)
    b = run("video + desktop audio (pipe)", True, None)
    time.sleep(1)
    c = run("video + microphone (dshow)", False, mic_name)
    time.sleep(1)
    d = run("video + both (as shipped)", True, mic_name)
finally:
    try:
        player.kill()
    except OSError:
        pass

print("\n--- verdict ---")
if a:
    for name, v in (("desktop audio", b), ("microphone", c), ("both", d)):
        if v:
            print(f"  adding {name:<15} costs {a - v:5.1f} fps "
                  f"({(a-v)/a*100:4.1f}%)")
