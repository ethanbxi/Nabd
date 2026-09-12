"""Minimal repro for the access violation when capturing two WASAPI endpoints.

Each case runs in its own interpreter so a hard crash is reported rather than
taking the whole run down with it.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

PREAMBLE = textwrap.dedent("""
    import sys, time, threading
    sys.path.insert(0, r"{app}")
    import pyaudiowpatch as pyaudio

    def loopback(pa):
        w = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        spk = pa.get_device_info_by_index(w["defaultOutputDevice"])["name"]
        for d in pa.get_loopback_device_info_generator():
            if spk in d["name"]:
                return d
        raise RuntimeError("no loopback")

    def mic(pa):
        w = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if (d["hostApi"] == w["index"] and d["maxInputChannels"] >= 1
                    and "[Loopback]" not in d["name"]):
                return d
        raise RuntimeError("no mic")

    def opener(pa, dev, sink):
        def cb(data, n, info, status):
            sink.append(len(data))
            return (None, pyaudio.paContinue)
        return pa.open(format=pyaudio.paInt16,
                       channels=max(1, min(int(dev["maxInputChannels"]), 2)),
                       rate=int(dev["defaultSampleRate"]), input=True,
                       input_device_index=dev["index"],
                       frames_per_buffer=1024, stream_callback=cb)
""").format(app=APP)

CASES = {
    "loopback only (one PyAudio)": """
        pa = pyaudio.PyAudio()
        got = []
        s = opener(pa, loopback(pa), got)
        time.sleep(3); s.close(); pa.terminate()
        print("chunks:", len(got))
    """,
    "mic only (one PyAudio)": """
        pa = pyaudio.PyAudio()
        got = []
        d = mic(pa)
        print("mic:", d["name"], int(d["defaultSampleRate"]), "Hz",
              d["maxInputChannels"], "ch")
        s = opener(pa, d, got)
        time.sleep(3); s.close(); pa.terminate()
        print("chunks:", len(got))
    """,
    "both, SEPARATE PyAudio per thread": """
        results = {}
        def worker(name, pick):
            pa = pyaudio.PyAudio()
            got = []
            s = opener(pa, pick(pa), got)
            time.sleep(3)
            s.close(); pa.terminate()
            results[name] = len(got)
        ts = [threading.Thread(target=worker, args=("lb", loopback)),
              threading.Thread(target=worker, args=("mic", mic))]
        for t in ts: t.start()
        for t in ts: t.join()
        print("chunks:", results)
    """,
    "both, SHARED PyAudio instance": """
        pa = pyaudio.PyAudio()
        a, b = [], []
        s1 = opener(pa, loopback(pa), a)
        s2 = opener(pa, mic(pa), b)
        time.sleep(3)
        s1.close(); s2.close(); pa.terminate()
        print("chunks: loopback", len(a), " mic", len(b))
    """,
    "shared PyAudio, staggered restart": """
        pa = pyaudio.PyAudio()
        a, b = [], []
        s1 = opener(pa, loopback(pa), a)
        s2 = opener(pa, mic(pa), b)
        time.sleep(1.5)
        s2.close()                      # imitate a mic reopen mid-session
        s2 = opener(pa, mic(pa), b)
        time.sleep(1.5)
        s1.close(); s2.close(); pa.terminate()
        print("chunks: loopback", len(a), " mic", len(b))
    """,
}

for name, body in CASES.items():
    script = PREAMBLE + textwrap.dedent(body)
    res = subprocess.run([sys.executable, "-c", script],
                         capture_output=True, text=True, timeout=90)
    code = res.returncode
    status = "OK" if code == 0 else f"CRASH ({code & 0xFFFFFFFF:#010x})"
    out = " | ".join(l for l in res.stdout.strip().splitlines() if l)
    err = res.stderr.strip().splitlines()
    print(f"  {name:<38} {status:<22} {out}")
    if code != 0 and err:
        print(f"      {err[-1][:120]}")
