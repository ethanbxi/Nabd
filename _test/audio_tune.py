"""Narrow down the best two-input audio configuration."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_fix as F  # noqa: E402  (reuses its runner)

mic = next((m for m in nabd.list_microphones(F.ffmpeg)
            if "webcam" not in m.lower() and "stream" not in m.lower()), None)
print(f"Microphone: {mic}\nTarget: {F.FPS} fps\n")

player = F.animate()
time.sleep(4)
best = (None, 0)
try:
    trials = [
        ("no audio_buffer_size, no tqs", dict(abuf=None)),
        ("no abuf + tqs=1024", dict(abuf=None, tqs=1024)),
        ("no abuf + tqs=4096", dict(abuf=None, tqs=4096)),
        ("abuf=200 + tqs=4096", dict(abuf="200", tqs=4096)),
        ("no abuf + tqs=4096 + async=1000", dict(abuf=None, tqs=4096,
                                                 async_n="1000")),
    ]
    for label, kw in trials:
        fps = F.run(label, mic, **kw)
        if fps > best[1]:
            best = (label, fps)
        time.sleep(1)
finally:
    try:
        player.kill()
    except OSError:
        pass

print(f"\nbest: {best[0]}  ->  {best[1]:.1f} real fps "
      f"({best[1]/F.FPS*100:.1f}% of target)")
