"""Is captured audio piling up before it reaches ffmpeg?

Anything sitting in the queue is latency the pacer never makes up, because it
drains at wall-clock speed. A steady non-zero backlog is a constant delay on
every sample that follows.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402


class Sink:
    def __init__(self):
        self.bytes = 0

    def write(self, data):
        self.bytes += len(data)


sink = Sink()
mixer = nabd.AudioMixer(mic=None)
mixer.start(sink)

print("sampling the audio queue depth...")
peak = 0.0
samples = []
for i in range(40):
    time.sleep(0.5)
    b = mixer.backlog_seconds
    peak = max(peak, b)
    samples.append(b)
    if i % 4 == 3:
        print(f"  t={(i+1)*0.5:5.1f}s  backlog={b*1000:6.1f} ms  "
              f"written={sink.bytes/nabd.BYTES_PER_SEC:6.2f}s  "
              f"padded={mixer.padded_seconds:.2f}s")

mixer.stop()
steady = samples[len(samples) // 2:]
avg = sum(steady) / len(steady)
print(f"\n  peak backlog   : {peak*1000:.0f} ms")
print(f"  steady backlog : {avg*1000:.0f} ms")
print(f"  total padding  : {mixer.padded_seconds:.2f}s")
if avg > 0.05:
    print("\n  -> a persistent backlog this size is a real audio delay")
else:
    print("\n  -> queue is shallow; delay is coming from somewhere else")
