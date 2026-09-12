"""Verify the audio supervisor rebuilds a dead stream and keeps the clock true.

A stalled endpoint is simulated by swallowing callbacks before they reach the
pump, which is indistinguishable from the device having gone silent.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402
import pyaudiowpatch as pyaudio  # noqa: E402


class CountingSink:
    def __init__(self):
        self.bytes = 0

    def write(self, data):
        self.bytes += len(data)


sink = CountingSink()
pump = nabd.AudioMixer(mic=None)  # desktop only, so the test is unambiguous

# Wrap the callback *before* start(), since the stream registers it at open time.
real_cb = pump.desktop._on_audio
deaf = threading.Event()


def wrapped(in_data, frame_count, time_info, status):
    if deaf.is_set():
        return (None, pyaudio.paContinue)  # endpoint looks dead to the mixer
    return real_cb(in_data, frame_count, time_info, status)


pump.desktop._on_audio = wrapped
pump.start(sink)

time.sleep(6)  # clear the reopen grace window
r0 = pump.reopens
print(f"steady state : {sink.bytes/nabd.BYTES_PER_SEC:.2f}s written, "
      f"padded={pump.padded_seconds:.2f}s, reopens={r0}")

print("\nsimulating a dead endpoint...")
deaf.set()
deadline = time.time() + 20
while pump.reopens == r0 and time.time() < deadline:
    time.sleep(0.25)

if pump.reopens == r0:
    print("FAIL: supervisor never reopened the stream")
    pump.stop()
    sys.exit(1)
print(f"supervisor reopened the stream (reopens={pump.reopens})")

# Let the device come back and confirm real bytes flow again, not just padding.
deaf.clear()
time.sleep(1.0)
mark_bytes, mark_pad = sink.bytes, pump.padded_seconds
time.sleep(4)
grew = (sink.bytes - mark_bytes) / nabd.BYTES_PER_SEC
new_pad = pump.padded_seconds - mark_pad
real = grew - new_pad
print(f"\nafter recovery: wrote {grew:.2f}s "
      f"({real:.2f}s real device audio, {new_pad:.2f}s padding)")

total = sink.bytes / nabd.BYTES_PER_SEC
pump.stop()

ok = True
if real < 3.0:
    print("FAIL: device audio did not resume after reopen")
    ok = False
print(f"total written = {total:.2f}s (pacer must track wall clock throughout)")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

