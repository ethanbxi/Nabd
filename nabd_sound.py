"""nab'd capture sound -- playback.

Stdlib only. No numpy, no new dependency; `winsound` ships with CPython on
Windows and plays a PCM WAV without going anywhere near the capture pipeline.

Call it from the BANNER process, on the line immediately before the animation
clock starts:

    from nabd_sound import play
    play(settings.capture_sound)          # returns immediately
    start = time.perf_counter()

The file is 4,120 ms -- the banner's TOTAL_MS, to the sample. That is not a
coincidence and it should not drift: async playback is owned by the process
that started it, and the banner calls root.destroy() at TOTAL_MS, so a file
even slightly longer than the animation gets its tail cut off.

Run this module directly to verify the shipped asset:

    python nabd_sound.py
"""
from __future__ import annotations

import sys
import tempfile
import time
import wave
from pathlib import Path

DURATION_MS = 4120          # must equal the banner's TOTAL_MS
BUILTIN = ("pip", "settle", "bloom")
DEFAULT = "pip"

# What the output device costs between PlaySound being called and the first
# sample being audible. Measured by playing a file of known length
# SYNCHRONOUSLY - the call returns when playback ends, so elapsed minus
# duration is the latency:
#
#     cold (device idle 45s)   +136 ms
#     warm                      +25 ms
#
# Those are two different problems. The 111ms of cold is the endpoint waking
# up, and prime() removes it by opening the device before the sound is needed.
# The remaining ~25ms is shared-mode latency that never goes away, so the
# sound is started that much earlier than the animation clock instead.
#
# Deliberately not larger. Sound arriving EARLY is more objectionable than
# sound arriving late, so this targets the warm figure and leaves prime() to
# deal with the cold one - rather than splitting the difference and
# overshooting every time the device is already awake.
LEAD_MS = 25
PRIME_MS = 250              # long enough to wake an idle endpoint

# How long the endpoint can go untouched before it has to be woken again, and
# how much extra run-up to give the primer when it has. The banner waits for
# that run-up, so this trades a slightly later FIRST banner for one that is in
# sync - which is the trade the user asked for, and it costs nothing on every
# banner after it.
COLD_AFTER_S = 20.0
COLD_EXTRA_MS = 200

_last_play = 0.0            # monotonic, per process; the helper is resident


def asset_dir() -> Path:
    """Where the WAVs live, frozen or not.

    PyInstaller onedir sets sys._MEIPASS to the bundle directory. Running from
    source there is no _MEIPASS and the assets sit next to this file.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / "sound"


def resolve(choice: str | None) -> Path | None:
    """-> the file to play, or None for 'no sound'. Never raises."""
    if not choice or choice == "off":
        return None
    try:
        if choice.lower().endswith(".wav"):          # user's own file
            p = Path(choice).expanduser()
        else:
            p = asset_dir() / ("nabd-sound-%s.wav" % choice)
        return p if p.is_file() else None
    except Exception:
        return None


def play(choice: str | None = DEFAULT) -> bool:
    """Start the sound. Returns immediately; True if playback was handed off.

    Every failure path is swallowed on purpose. A missing file, a machine with
    no audio endpoint, an exclusive-mode device -- none of those are reasons to
    take down the banner, and there is nothing useful to tell the user about a
    confirmation sound that did not play.
    """
    path = resolve(choice)
    if path is None:
        return False
    try:
        import winsound
    except ImportError:
        return False                                  # not Windows
    try:
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME     # play from disk
            | winsound.SND_ASYNC      # return now; do not block the UI thread
            | winsound.SND_NODEFAULT  # silence, not the Windows ding, if it fails
        )
        global _last_play
        _last_play = time.monotonic()
        return True
    except Exception:
        return False


def cold() -> bool:
    """Has the output device gone quiet long enough to need waking?"""
    return (time.monotonic() - _last_play) > COLD_AFTER_S


def prime() -> bool:
    """Open the output device before the sound is needed.

    An idle endpoint - a wireless headset especially - charges for waking up,
    and it charges whichever sound is played first. Starting a moment of
    silence ahead of the banner means the banner's sound is never the one that
    pays.

    Cheap to call and harmless to repeat: PlaySound preempts itself, so the
    real sound cuts this off rather than queueing behind it.

    The silence is generated into the temp directory rather than shipped. The
    asset directory is inside the frozen bundle and is not ours to write to,
    and a 250ms file of zeros is not worth a build step.
    """
    try:
        path = Path(tempfile.gettempdir()) / "nabd-prime.wav"
        if not path.is_file() or path.stat().st_size == 0:
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes(b"\x00\x00" * int(48000 * PRIME_MS / 1000))
    except Exception:
        return False
    try:
        import winsound
        winsound.PlaySound(
            str(path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        return False
    global _last_play
    _last_play = time.monotonic()
    return True


def stop() -> None:
    """Cut playback. PlaySound(None) does this; a second play() also preempts."""
    try:
        import winsound
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


# ── verification (stdlib only, so it can run in CI without numpy) ─────────
def verify(path: Path) -> dict:
    import wave, audioop
    with wave.open(str(path), "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        frames = w.readframes(n)
    ms = 1000.0 * n / sr
    peak = audioop.max(frames, sw) / float(1 << (8 * sw - 1))
    rms = audioop.rms(frames, sw) / float(1 << (8 * sw - 1))
    import math
    info = dict(channels=ch, bits=8 * sw, rate=sr, ms=ms,
                peak_db=20 * math.log10(peak), rms_db=20 * math.log10(rms),
                first=audioop.getsample(frames, sw, 0),
                last=audioop.getsample(frames, sw, n - 1))
    assert ch == 1 and sw == 2 and sr == 48000, ("expected 48 kHz 16-bit mono", info)
    assert abs(ms - DURATION_MS) < 1.0, ("length must equal the banner's TOTAL_MS", info)
    assert -12.6 < info["peak_db"] < -11.4, ("mastered at -12 dBFS; winsound has no volume", info)
    assert abs(info["first"]) <= 2 and abs(info["last"]) <= 2, ("edge click", info)
    return info


if __name__ == "__main__":
    d = asset_dir()
    print("assets:", d, "\n")
    found = 0
    for name in BUILTIN:
        p = d / ("nabd-sound-%s.wav" % name)
        if not p.is_file():
            continue
        found += 1
        i = verify(p)
        print("%-8s %7.1f ms  %d Hz %d-bit %dch  peak %.2f dBFS  rms %.1f dBFS  edges %+d/%+d"
              % (name, i["ms"], i["rate"], i["bits"], i["channels"],
                 i["peak_db"], i["rms_db"], i["first"], i["last"]))
    print("\n%d file(s) verified." % found if found else "\nNo sound assets found.")
