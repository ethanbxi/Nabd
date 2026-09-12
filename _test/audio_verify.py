"""Does the real pipeline hold its frame rate now that the mic is mixed in-process?

Also confirms the mixed track still carries audio, since moving the mix out of
ffmpeg is only worth anything if both sources survive.
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ffmpeg = nabd.find_ffmpeg()
ffplay = ffmpeg.replace("ffmpeg.exe", "ffplay.exe")
OUT = Path(__file__).resolve().parent / "out"
SECONDS = 14

print("WASAPI capture devices:")
mics = nabd.list_microphones()
for m in mics:
    print(f"    {m}")
print()


def animate():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "testsrc2=size=2560x1440:rate=60",
         "-loglevel", "quiet", "-fs", "-autoexit"],
        creationflags=nabd.CREATE_NO_WINDOW)


def tone():
    return subprocess.Popen(
        [ffplay, "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
         "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", "70"],
        creationflags=nabd.CREATE_NO_WINDOW)


def trial(label, capture_mic):
    cfg = nabd.load_config()
    cfg["clip_seconds"] = 120
    cfg["output_dir"] = str(OUT)
    cfg["save_delay"] = 2.0
    cfg["capture_mic"] = capture_mic

    rec = nabd.Recorder(cfg, ffmpeg)
    clip = nabd.Clipper(cfg, ffmpeg, rec)
    OUT.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in OUT.glob("*.mp4")}
    rec.clear_buffer()
    rec.start()
    time.sleep(SECONDS)

    health = dict(rec.health)
    done = []
    clip.save(on_done=lambda ok, d: done.append(ok))
    for _ in range(80):
        if done:
            break
        time.sleep(0.25)
    padded = rec.audio.padded_seconds if rec.audio else -1
    rec.stop()

    fps = health.get("fps", 0)
    dup = health.get("dup", 0)
    frames = fps * SECONDS
    real = max(0.0, (frames - dup)) / SECONDS if frames else 0
    target = float(cfg["fps"])
    print(f"  {label:<28} {fps:5.1f} fps encoded, {dup:>4} dup "
          f"-> {real:5.1f} real fps ({real/target*100:5.1f}%)  "
          f"padded {padded:.2f}s")

    path = None
    if done and done[0]:
        path = max((p for p in OUT.glob("*.mp4") if p.name not in before),
                   key=lambda p: p.stat().st_mtime)
    return real, path


def audio_level(path):
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "NUL"],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW).stderr
    for line in out.splitlines():
        if "max_volume" in line:
            return line.split("]")[-1].strip()
    return "unknown"


player, sound = animate(), tone()
time.sleep(4)
try:
    print(f"Full-screen 60fps animation, {SECONDS}s per configuration.")
    no_mic, _ = trial("desktop audio only", False)
    time.sleep(2)
    with_mic, path = trial("desktop + mic (mixed here)", True)
finally:
    for p in (player, sound):
        try:
            p.kill()
        except OSError:
            pass

print()
if path:
    print(f"  mixed clip audio: {audio_level(path)}")
target = 60.0
ok = with_mic >= target * 0.9
print(f"\n  cost of enabling the mic: {no_mic - with_mic:+.1f} fps")
print("PASS" if ok else "FAIL",
      f"- with the mic on, real rate is {with_mic:.1f} fps "
      f"({with_mic/target*100:.0f}% of target)")
sys.exit(0 if ok else 1)
