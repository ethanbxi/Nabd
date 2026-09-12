"""Where does the audio delay come from? Ask the device and the open stream."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402
import pyaudiowpatch as pyaudio  # noqa: E402

pa = pyaudio.PyAudio()
try:
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    spk = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
    print(f"default output: {spk['name']}")

    loop = None
    for d in pa.get_loopback_device_info_generator():
        if spk["name"] in d["name"]:
            loop = d
            break
    if not loop:
        print("no loopback endpoint")
        sys.exit(1)

    print("\nloopback device reports:")
    for key in ("defaultLowInputLatency", "defaultHighInputLatency",
                "defaultSampleRate", "maxInputChannels"):
        print(f"  {key:<26} {loop.get(key)}")

    print("\nopening the stream exactly as Nab'd does...")
    got = []

    def cb(data, n, info, status):
        got.append(time.perf_counter())
        return (None, pyaudio.paContinue)

    stream = pa.open(format=pyaudio.paInt16,
                     channels=max(1, min(int(loop["maxInputChannels"]), 2)),
                     rate=int(loop["defaultSampleRate"]), input=True,
                     input_device_index=loop["index"],
                     frames_per_buffer=1024, stream_callback=cb)
    time.sleep(3)
    actual = stream.get_input_latency()
    stream.close()

    print(f"  stream.get_input_latency()  {actual*1000:.1f} ms")
    if len(got) > 2:
        gaps = [b - a for a, b in zip(got, got[1:])]
        gaps.sort()
        print(f"  callback interval (median)  {gaps[len(gaps)//2]*1000:.1f} ms")
        print(f"  callbacks in 3s             {len(got)}")

    print("\nsmaller buffer, for comparison:")
    got.clear()
    stream = pa.open(format=pyaudio.paInt16,
                     channels=max(1, min(int(loop["maxInputChannels"]), 2)),
                     rate=int(loop["defaultSampleRate"]), input=True,
                     input_device_index=loop["index"],
                     frames_per_buffer=256, stream_callback=cb)
    time.sleep(3)
    print(f"  stream.get_input_latency()  {stream.get_input_latency()*1000:.1f} ms")
    stream.close()
finally:
    pa.terminate()
