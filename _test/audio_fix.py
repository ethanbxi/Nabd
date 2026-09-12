"""Can buffering flags rescue the two-audio-input case, or is amix the problem?"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
OUT = Path(__file__).resolve().parent / "out" / "audio_fix"
SECONDS = 12
FPS = 60
SEG = 2
RATE, CH = nabd.RATE, nabd.CHANNELS


def animate():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def run(label, mic, *, tqs=None, abuf="50", mix="amix", async_n="1"):
    d = OUT / label.replace(" ", "_").replace("=", "")
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.ts"):
        old.unlink()

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-progress", "pipe:1", "-stats_period", "1", "-y",
           "-init_hw_device", "d3d11va"]
    if tqs:
        cmd += ["-thread_queue_size", str(tqs)]
    cmd += ["-f", "s16le", "-ar", str(RATE), "-ac", str(CH), "-i", "pipe:0"]
    if tqs:
        cmd += ["-thread_queue_size", str(tqs)]
    cmd += ["-f", "dshow"]
    if abuf:
        cmd += ["-audio_buffer_size", abuf]
    cmd += ["-i", f"audio={mic}"]

    chains = [f"ddagrab=output_idx=0:framerate={FPS}:draw_mouse=1[v]",
              f"[0:a]aresample=async={async_n}:first_pts=0[d]",
              f"[1:a]aresample=async={async_n}:first_pts=0[m]"]
    if mix == "amix":
        chains.append("[d][m]amix=inputs=2:duration=first:normalize=0,"
                      "alimiter=limit=0.97[a]")
    else:  # amerge downmixed - different scheduling behaviour to amix
        chains.append("[d][m]amerge=inputs=2,pan=stereo|c0<c0+c2|c1<c1+c3,"
                      "alimiter=limit=0.97[a]")

    cmd += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]",
            "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23",
            "-bf", "0", "-rc-lookahead", "0", "-delay", "0",
            "-g", str(FPS * SEG), "-forced-idr", "1",
            "-force_key_frames", f"expr:gte(t,n_forced*{SEG})",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", str(CH),
            "-t", str(SECONDS),
            "-f", "segment", "-segment_time", str(SEG),
            "-segment_format", "mpegts", "-reset_timestamps", "1",
            "-flush_packets", "1", str(d / "s_%04d.ts")]

    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=nabd.CREATE_NO_WINDOW | nabd.ABOVE_NORMAL_PRIORITY_CLASS)
    pump = nabd.DesktopAudioPump("")
    pump.start(proc.stdin)

    fields = {}
    for raw in iter(proc.stdout.readline, b""):
        line = raw.decode("utf-8", "replace").strip()
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k] = v.strip()
    proc.wait()
    pump.stop()

    try:
        frames = int(fields.get("frame", 0))
        dup = int(fields.get("dup_frames", 0))
    except ValueError:
        print(f"  {label:<40} parse error")
        return 0
    real = (frames - dup) / SECONDS
    print(f"  {label:<40} {dup:>4} dup -> {real:5.1f} real fps "
          f"({real/FPS*100:5.1f}%)")
    return real


mic = next((m for m in nabd.list_microphones(ffmpeg)
            if "webcam" not in m.lower() and "stream" not in m.lower()), None)
print(f"Microphone: {mic}\nTarget: {FPS} fps\n")

player = animate()
time.sleep(4)
try:
    run("baseline (as shipped)", mic)
    time.sleep(1)
    run("thread_queue_size=4096", mic, tqs=4096)
    time.sleep(1)
    run("tqs=4096 + audio_buffer_size default", mic, tqs=4096, abuf=None)
    time.sleep(1)
    run("tqs=4096 + amerge instead of amix", mic, tqs=4096, mix="amerge")
    time.sleep(1)
    run("tqs=4096 + aresample async=0", mic, tqs=4096, async_n="0")
finally:
    try:
        player.kill()
    except OSError:
        pass
