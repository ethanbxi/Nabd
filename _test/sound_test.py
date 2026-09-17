"""The capture sound: is it locked to the banner it is scored against?

    python _test/sound_test.py

The sound is one file with its beats baked in, started once and never
scheduled - which is what keeps it in sync, and also what makes it quiet to
break. SOUND.md section 7 lists the ways, and each one is checked here:

  the length   The file is the banner's TOTAL_MS to the sample. Async playback
               belongs to the process that started it and the banner destroys
               itself at TOTAL_MS, so a longer file loses its tail and a
               shorter one leaves the exit unscored. Two constants in two
               modules have to agree, and nothing at runtime would notice.

  the level    winsound has no volume control, so the mastering level IS the
               playback level. Re-normalising the WAV louder is a one-line
               change with no error.

  the call     play() goes immediately before the animation clock is first
               read. A line later and the sound trails the animation by
               however long the first frame took.

  the format   PlaySound fails SILENTLY on a non-PCM WAV.
"""
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import banner as B                   # noqa: E402
import nabd                          # noqa: E402
import nabd_banner as M              # noqa: E402
import nabd_sound as S               # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def asset():
    print("-- the file, and the length it has to be --")
    check("the two lengths agree", S.DURATION_MS == M.TOTAL_MS,
          f"sound {S.DURATION_MS}ms, banner {M.TOTAL_MS}ms")
    wavs = sorted((HERE.parent / "assets" / "sound").glob("*.wav"))
    check("the sound ships with the program", bool(wavs),
          ", ".join(w.name for w in wavs))
    for w in wavs:
        try:
            i = S.verify(w)
            check(f"{w.name} verifies", True,
                  "%.1f ms, %d Hz %d-bit %dch, peak %.2f dBFS"
                  % (i["ms"], i["rate"], i["bits"], i["channels"],
                     i["peak_db"]))
        except AssertionError as exc:
            check(f"{w.name} verifies", False, str(exc)[:90])

    print("\n-- resolve: the one place that decides what plays --")
    check("a built-in name finds its file",
          S.resolve("pip") is not None and S.resolve("pip").is_file())
    check("'off' is silence", S.resolve("off") is None)
    check("empty is silence", S.resolve("") is None and S.resolve(None) is None)
    check("a name with no file is silence, not an error",
          S.resolve("nosuchsound") is None)
    check("a .wav that is not there is silence",
          S.resolve(r"C:\nope\missing.wav") is None)
    if wavs:
        check("a path to a real .wav is taken as a path",
              S.resolve(str(wavs[0])) == wavs[0])
    check("play() on silence reports that it played nothing",
          S.play("off") is False)


def payload():
    """The banner is a separate long-lived process with no config of its own,
    so the choice has to travel in the trigger."""
    print("\n-- the choice reaching the banner process --")
    written = {}

    class FakeApp:
        cfg = dict(nabd.DEFAULTS)
        show_banner = nabd.App.show_banner
        # Borrowed rather than reimplemented: this test exists to prove the
        # real decision reaches the trigger, so a stand-in here would prove
        # nothing about the app.
        _banner_sound = nabd.App._banner_sound

        def ensure_banner_helper(self):
            pass

        def _write_banner(self, p):
            written.clear()
            written.update(p)

    app = FakeApp()
    app.cfg["notify"] = True
    app.cfg["capture_sound"] = "pip"
    app.show_banner("Nabbed", "5:00", ok=True, token="nab1")
    check("a save carries the sound", written.get("sound") == "pip",
          repr(written.get("sound")))

    app.cfg["capture_sound"] = "off"
    app.show_banner("Nabbed", "5:00", ok=True, token="nab2")
    check("switching it off carries through",
          written.get("sound") == "off", repr(written.get("sound")))

    # A failure used to stay silent, because the only cue that existed was a
    # confirmation and playing it would have told the user the opposite of what
    # happened. There is a dedicated error cue now, so it speaks with its own
    # voice - same six beats and the same length, a tritone where the fifth was.
    app.cfg["capture_sound"] = "pip"
    app.show_banner("Capture Lost", "", ok=False, token="nab3")
    check("a failure banner plays the error cue",
          written.get("sound") == "error", repr(written.get("sound")))

    # ...but "off" is a preference about being chimed at at all, not about
    # which chime, so it has to carry to the failure cue too.
    app.cfg["capture_sound"] = "off"
    app.show_banner("Capture Lost", "", ok=False, token="nab4")
    check("switching sound off silences failures too",
          written.get("sound") == "off", repr(written.get("sound")))

    # Colour and sound are separate decisions, so a banner can be purple and
    # silent at once - which is what "Still saving" has to be.
    app.show_banner("Still saving", "", ok=True, token="nab4", sound="off")
    check("a banner can be purple and silent",
          written.get("sound") == "off" and written.get("kind") == "ok",
          "kind=%r sound=%r" % (written.get("kind"), written.get("sound")))


def refused():
    """The hotkey during assembly used to do nothing at all."""
    print("\n-- pressing the hotkey while the last nab is still writing --")
    written = {}

    class Busy:
        def save(self, **kw):
            return False            # what Clipper does while it is working

    class FakeApp:
        cfg = dict(nabd.DEFAULTS)
        save_clip = nabd.App.save_clip
        show_banner = nabd.App.show_banner
        clipper = Busy()

        def ensure_banner_helper(self):
            pass

        def _write_banner(self, p):
            written.clear()
            written.update(p)

    app = FakeApp()
    app.cfg["notify"] = True
    app.save_clip()
    check("a refused nab still says something",
          bool(written.get("title")), repr(written.get("title")))
    check("it is not dressed as a failure", written.get("kind") == "ok",
          repr(written.get("kind")))
    check("and it does not chime - nothing was nabbed",
          written.get("sound") == "off", repr(written.get("sound")))


def timing():
    print("\n-- play() before the clock, and cut when the timeline pins --")
    root = tk.Tk()
    root.withdraw()
    calls, stops, primes = [], [], []
    real_play, real_stop, real_prime = S.play, S.stop, S.prime
    B.nabd_sound.play = lambda c=None: (calls.append((c, time.perf_counter()))
                                        or True)
    B.nabd_sound.stop = lambda: stops.append(time.perf_counter())
    B.nabd_sound.prime = lambda: (primes.append(time.perf_counter()) or True)
    try:
        # Warm on purpose: a cold device earns a run-up and the banner waits
        # for it, which is cold_start()'s business, not this one's.
        S._last_play = time.monotonic()
        made = time.perf_counter()
        bn = B.Banner(root, "Nabbed", "5:00", "ok", 0, delay=0.2, sound="pip")
        bn.draw = lambda f: None        # the picture is banner_test's business
        t0 = time.perf_counter()
        while bn.start is None and time.perf_counter() - t0 < 8:
            root.update()
            time.sleep(0.002)
        check("the banner plays the choice it was handed",
              len(calls) == 1 and calls[0][0] == "pip",
              repr(calls and calls[0][0]))
        check("the endpoint is primed before any of it", len(primes) == 1
              and primes[0] <= calls[0][1], "%d prime(s)" % len(primes))
        # The sound has to leave BEFORE the clock starts, by the lead, because
        # the device does not make it audible for that long.
        lead = (bn.start - calls[0][1]) * 1000 if calls and bn.start else 0
        check("the sound leaves ahead of the clock by the lead",
              abs(lead - S.LEAD_MS) < 20,
              "%.0f ms ahead (LEAD_MS %d)" % (lead, S.LEAD_MS))
        # ...and the picture must not have moved to pay for it: the pre-roll
        # absorbs the lead.
        shown = (bn.start - made) * 1000
        check("the banner still appears when it always did",
              abs(shown - 200) < 40, "%.0f ms after the trigger (delay 200)"
              % shown)

        # Clicking before the nab has finished assembling pins the timeline at
        # HOLD_MS. The sound cannot pin with it, so it is cut - inaudibly,
        # because HOLD_MS falls inside the file's long silence.
        check("the hold lands inside the file's silence",
              900 < B.HOLD_MS < 3200, f"HOLD_MS {B.HOLD_MS}")
        bn.path = "C:\\nope\\unfinished.mp4"
        bn.ready = False
        bn._click()
        root.update()
        check("clicking an unfinished nab cuts the sound",
              len(stops) == 1 and bn._waiting)
        bn.finish()
        root.update()
    finally:
        B.nabd_sound.play, B.nabd_sound.stop = real_play, real_stop
        B.nabd_sound.prime = real_prime
        try:
            root.destroy()
        except tk.TclError:
            pass


def cold_start():
    """The first banner after a quiet spell is the one that pays.

    The endpoint charges to wake - measured at +136ms against the file's own
    length after 45s of silence, against +25ms back to back - and it charges
    whichever sound is played first. prime() is meant to absorb that, but the
    real sound PREEMPTS the primer, so a primer with 175ms to work in is
    killed before a slow device has finished waking. A cold device therefore
    gets a longer run-up, and the banner waits for it - once.
    """
    print("\n-- a cold device gets a run-up; a warm one does not --")
    root = tk.Tk()
    root.withdraw()
    calls, primes = [], []
    real_play, real_prime = S.play, S.prime
    was_last = S._last_play
    B.nabd_sound.play = lambda c=None: (calls.append(time.perf_counter())
                                        or True)
    B.nabd_sound.prime = lambda: (primes.append(time.perf_counter()) or True)

    def run(quiet_for):
        calls.clear()
        primes.clear()
        S._last_play = time.monotonic() - quiet_for
        made = time.perf_counter()
        bn = B.Banner(root, "Nabbed", "5:00", "ok", 0, delay=0.2, sound="pip")
        bn.draw = lambda f: None
        t0 = time.perf_counter()
        while bn.start is None and time.perf_counter() - t0 < 8:
            root.update()
            time.sleep(0.002)
        out = ((bn.start - made) * 1000,
               (calls[0] - primes[0]) * 1000 if calls and primes else 0,
               (bn.start - calls[0]) * 1000 if calls else 0)
        bn.finish()
        root.update()
        return out

    try:
        shown, warmup, lead = run(S.COLD_AFTER_S + 5)
        check("a cold device gets a longer run-up",
              warmup > S.COLD_EXTRA_MS, "%.0f ms before the sound" % warmup)
        check("...and the banner waits for it",
              abs(shown - (200 + S.COLD_EXTRA_MS)) < 60,
              "%.0f ms after the trigger" % shown)
        check("...with the lead still intact",
              abs(lead - S.LEAD_MS) < 25, "%.0f ms ahead" % lead)

        shown, warmup, lead = run(0.0)
        check("a warm device waits for nothing",
              abs(shown - 200) < 60, "%.0f ms after the trigger" % shown)
        check("...and the lead is unchanged",
              abs(lead - S.LEAD_MS) < 25, "%.0f ms ahead" % lead)

        # Silence must not buy a run-up nobody is going to use.
        calls.clear()
        primes.clear()
        S._last_play = time.monotonic() - (S.COLD_AFTER_S + 5)
        made = time.perf_counter()
        bn = B.Banner(root, "Still saving", "", "ok", 0, delay=0.2,
                      sound="off")
        bn.draw = lambda f: None
        t0 = time.perf_counter()
        while bn.start is None and time.perf_counter() - t0 < 8:
            root.update()
            time.sleep(0.002)
        check("a silent banner is not delayed for a device it will not use",
              abs((bn.start - made) * 1000 - 200) < 60 and not primes,
              "%.0f ms, %d primes" % ((bn.start - made) * 1000, len(primes)))
        bn.finish()
        root.update()
    finally:
        B.nabd_sound.play, B.nabd_sound.prime = real_play, real_prime
        S._last_play = was_last
        try:
            root.destroy()
        except tk.TclError:
            pass


def main():
    asset()
    payload()
    refused()
    timing()
    cold_start()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
