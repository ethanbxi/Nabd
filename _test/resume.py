"""Measure how fast loopback recovers when audio starts after a silent lull.

Runs the same experiment with and without a silent keep-alive render stream so
the difference is attributable to the keep-alive alone.
"""
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402
import pyaudiowpatch as pyaudio  # noqa: E402

FFPLAY = nabd.find_ffmpeg().replace("ffmpeg.exe", "ffplay.exe")
SILENT_LULL = 12   # long enough for Windows to idle the endpoint
TONE_AFTER = 6


class Sink:
    """Stands in for ffmpeg's stdin; timestamps every write."""
    def __init__(self):
        self.events = []   # (wall_time, peak_amplitude)
        self.t0 = time.perf_counter()

    def write(self, data):
        peak = 0
        for i in range(0, len(data) - 1, 64):
            v = struct.unpack_from("<h", data, i)[0]
            if abs(v) > peak:
                peak = abs(v)
        self.events.append((time.perf_counter() - self.t0, peak))


def keep_alive(stop):
    """Render inaudible silence so the endpoint never goes idle."""
    pa = pyaudio.PyAudio()
    try:
        info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        out = pa.open(format=pyaudio.paInt16, channels=2, rate=48000, output=True,
                      output_device_index=info["defaultOutputDevice"],
                      frames_per_buffer=1024)
        quiet = b"\x00" * (1024 * 2 * 2)
        while not stop.is_set():
            out.write(quiet)
        out.close()
    finally:
        pa.terminate()


def trial(label, use_keep_alive):
    sink = Sink()
    pump = nabd.DesktopAudioPump()
    stop_ka = threading.Event()
    ka = None
    if use_keep_alive:
        ka = threading.Thread(target=keep_alive, args=(stop_ka,), daemon=True)
        ka.start()
        time.sleep(0.5)

    pump.start(sink)
    time.sleep(SILENT_LULL)  # let Windows idle the endpoint

    padded_before = pump.padded_seconds
    tone_at = time.perf_counter() - sink.t0
    tone = subprocess.Popen(
        [FFPLAY, "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", "70"],
        creationflags=nabd.CREATE_NO_WINDOW,
    )
    time.sleep(TONE_AFTER)
    pump.stop()
    stop_ka.set()
    try:
        tone.kill()
    except OSError:
        pass
    time.sleep(0.3)

    first_signal = next((t for t, p in sink.events if t > tone_at and p > 500), None)
    lull_padding = padded_before
    print(f"\n[{label}]")
    print(f"  padding during {SILENT_LULL}s lull : {lull_padding:.2f}s")
    if first_signal is None:
        print("  signal after tone start     : NEVER DETECTED")
        return None
    latency = first_signal - tone_at
    print(f"  tone launched at t={tone_at:.2f}s, first signal at t={first_signal:.2f}s")
    print(f"  resume latency              : {latency*1000:.0f} ms  (incl. ~300ms ffplay startup)")
    return latency


without = trial("no keep-alive", False)
time.sleep(2)
with_ka = trial("with keep-alive", True)

print("\n" + "=" * 52)
if without is None:
    print("Without keep-alive the tone was never captured.")
elif with_ka is not None:
    print(f"without={without*1000:.0f}ms   with={with_ka*1000:.0f}ms   "
          f"improvement={(without-with_ka)*1000:.0f}ms")

