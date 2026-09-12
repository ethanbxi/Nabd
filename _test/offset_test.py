"""Does the A/V trim actually move audio on the timeline?

ffmpeg numbers raw PCM by sample count, so shifting audio is the same as
changing how many samples exist before a given moment. Writing N ms fewer
samples in the same wall-clock window moves everything after it N ms earlier.
This measures that directly, with no video and no detector involved.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

RUN = 6.0


class Sink:
    def __init__(self):
        self.bytes = 0
        self.first_write = None

    def write(self, data):
        if self.first_write is None and data:
            self.first_write = time.perf_counter()
        self.bytes += len(data)


def run(offset_ms):
    sink = Sink()
    mixer = nabd.AudioMixer(mic=None, offset_ms=offset_ms)
    started = time.perf_counter()
    mixer.start(sink)
    time.sleep(RUN)
    elapsed = time.perf_counter() - started
    written = sink.bytes / nabd.BYTES_PER_SEC
    delay = (sink.first_write - started) if sink.first_write else -1
    mixer.stop()
    time.sleep(0.4)
    print(f"  offset {offset_ms:+5d} ms : wrote {written:5.2f}s of audio in "
          f"{elapsed:.2f}s wall   first write after {delay*1000:6.1f} ms")
    return written, elapsed


print("A shift moves audio earlier by emitting that much less leading silence.\n")
base_written, base_elapsed = run(0)
time.sleep(1)
shift_written, shift_elapsed = run(-150)

# Normalise for any difference in how long each run actually took.
base_rate = base_written - base_elapsed
shift_rate = shift_written - shift_elapsed
moved = (base_rate - shift_rate) * 1000

print(f"\n  samples withheld by the -150 ms setting: {moved:.0f} ms")
ok = 120 <= moved <= 180
print("PASS" if ok else "FAIL",
      f"- expected about 150 ms, got {moved:.0f} ms")
sys.exit(0 if ok else 1)
