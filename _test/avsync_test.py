"""The A/V sync Test button: does it produce something you can measure?

    python _test/avsync_test.py

The button used to write a one-byte file that nothing read, under helper text
promising a clip. What it produces now is only useful if three things hold, and
each is checked here:

  the gap      A rung labelled -100 has to play its click 100ms before its
               flash. That gap IS the measurement - error in it is read back by
               the user as an audio offset that was never there. The slider
               moves in 10ms steps, so this has to be well inside that.

  the note     The panel tells the daemon WHEN to save, not "save now", and
               asks for a window long enough to hold the whole card plus the
               clipper's settle. Get that wrong and the pattern falls outside
               the clip.

  the offset   The card shows the SAVED offset, because that is the one the
               recording is being made with. A slider dragged but not saved
               has to be called out, not quietly tested.

The card is shrunk further still for these cases, so running the suite does not
put a quarter-minute of flashing in the middle of the screen.
"""
import ctypes
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
ctypes.windll.shcore.SetProcessDpiAwareness(2)

import nabd  # noqa: E402
import nabd_avtest as AV  # noqa: E402
import settings as S  # noqa: E402

PASS, FAIL, SKIP = [], [], []
SMALL = {"width": 900, "height": 506, "x": 30, "y": 30}


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def skip(name, why):
    SKIP.append(name)
    print(f"  SKIP  {name}  ({why})")


# ---------------------------------------------------------------------------
# 1. the gap between a flash and its click
# ---------------------------------------------------------------------------

def timing():
    root = tk.Tk()
    root.withdraw()
    flashes, clicks = [], []
    real = AV.TestCard._fire

    def fire(self, kind, arg):
        if kind == "flash":
            flashes.append(time.perf_counter())
        elif kind == "click":
            clicks.append(time.perf_counter())
        return real(self, kind, arg)

    AV.TestCard._fire = fire
    try:
        card = AV.TestCard(root, SMALL, "offset now  0 ms",
                           lambda: None, lambda: None)
        S.TIMER.begin()             # what the panel holds for the same reason
        card.start()
        while not card._done:
            root.update()
            time.sleep(0.001)
    finally:
        S.TIMER.end()
        AV.TestCard._fire = real

    want = list(AV.LADDER) + [0] * AV.CLAPS
    check("every pair fired", len(flashes) == len(clicks) == len(want),
          f"({len(flashes)} flashes, {len(clicks)} clicks)")
    if len(flashes) == len(clicks) == len(want):
        # No crossing to worry about: the rungs are 1500ms apart and the
        # widest click is 200ms off its own flash, so the order each list is
        # appended in is the order they were scheduled in.
        err = [abs((clicks[i] - flashes[i]) * 1000.0 - want[i])
               for i in range(len(want))]
        step = 10                   # the slider's granularity
        check("clicks land where the rung says, inside a slider step",
              max(err) < step, "worst %.1f ms, mean %.1f (step %dms)"
              % (max(err), sum(err) / len(err), step))
    root.destroy()


# ---------------------------------------------------------------------------
# 0. where the slider's zero is
#
# The slider used to stand on its own, so its neutral position was whatever
# the pipeline happened to be out by - about 200ms - and every user had to
# find that out for themselves. It now trims around AUDIO_BASELINE_MS, so 0
# means calibrated. What has to hold is that rebasing changed the NUMBER and
# not the RECORDING: a machine already set up keeps the offset it had.
# ---------------------------------------------------------------------------

def baseline():
    import json
    import tempfile

    check("zero is the calibrated setting, not the raw one",
          nabd.DEFAULTS["audio_offset_ms"] == 0
          and nabd.AUDIO_BASELINE_MS != 0,
          "slider default %d, baseline %d ms"
          % (nabd.DEFAULTS["audio_offset_ms"], nabd.AUDIO_BASELINE_MS))

    real = nabd.CONFIG_PATH
    tmp = Path(tempfile.mkdtemp()) / "config.json"
    nabd.CONFIG_PATH = tmp
    try:
        # An existing machine: the number moves, what it records does not.
        for was in (-200, -150, 0, 120):
            tmp.write_text(json.dumps({"audio_offset_ms": was}),
                           encoding="utf-8")
            cfg = nabd.load_config()
            now = cfg["audio_offset_ms"]
            before = was
            after = nabd.AUDIO_BASELINE_MS + now
            check("a stored %+d ms records the same after rebasing" % was,
                  after == before, "slider %+d -> %+d, pipeline %+d ms"
                  % (was, now, after))
        # And the one the user actually settled on lands on zero.
        tmp.write_text(json.dumps({"audio_offset_ms": nabd.AUDIO_BASELINE_MS}),
                       encoding="utf-8")
        cfg = nabd.load_config()
        check("the measured-correct setting becomes the new zero",
              cfg["audio_offset_ms"] == 0, "%+d" % cfg["audio_offset_ms"])

        # Rebasing twice would move a machine 200ms every launch.
        check("the rebase is recorded in the file",
              json.loads(tmp.read_text(encoding="utf-8"))
              .get("config_version") == 2)
        again = nabd.load_config()
        check("and does not happen again",
              again["audio_offset_ms"] == 0, "%+d" % again["audio_offset_ms"])

        # A fresh install starts calibrated.
        tmp.unlink()
        fresh = nabd.load_config()
        check("a fresh install starts at zero, already corrected",
              fresh["audio_offset_ms"] == 0
              and nabd.AUDIO_BASELINE_MS + fresh["audio_offset_ms"]
              == nabd.AUDIO_BASELINE_MS)
    finally:
        nabd.CONFIG_PATH = real


# ---------------------------------------------------------------------------
# 1a. the click can actually be played
#
# Not a formality. The first version passed the WAV as bytes with
# SND_MEMORY | SND_ASYNC, which winsound refuses outright - and the panel
# caught the exception and carried on, so the card ran, the clip saved, and
# there was no sound in it to judge anything against. Every other test here
# stubbed PlaySound, so every one of them passed.
# ---------------------------------------------------------------------------

def sound():
    import winsound
    path = AV.click_path(nabd.DATA_DIR)
    check("the click is written to a file", bool(path) and Path(path).exists(),
          str(path))
    if not path:
        return
    played = True
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
    except Exception as exc:
        played = False
        print("       %s: %s" % (type(exc).__name__, exc))
    check("winsound accepts the flags the panel uses", played)

    # And the primer, which is what stops the first pair wearing the output
    # device's wake-up as an offset that is not real.
    prime = AV.silence_path(nabd.DATA_DIR)
    check("the device primer is written too",
          bool(prime) and Path(prime).exists(), str(prime))
    quiet = True
    try:
        winsound.PlaySound(prime, winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
    except Exception:
        quiet = False
    check("the primer plays", quiet)
    # And the combination that did not work, so the reason stays on record.
    from_memory = True
    try:
        winsound.PlaySound(AV.click_wav(),
                           winsound.SND_MEMORY | winsound.SND_ASYNC)
    except RuntimeError:
        from_memory = False
    check("playing async from memory is still refused, as documented",
          not from_memory)


# ---------------------------------------------------------------------------
# 1b. the card is a window, and you can always get rid of it
#
# The first version was fullscreen, borderless, always on top and had no key
# handling. When it stalled there was no way to reach anything behind it and
# the machine had to be restarted. Three things stop that being possible.
# ---------------------------------------------------------------------------

def window():
    root = tk.Tk()
    root.withdraw()
    mon = {"width": 2560, "height": 1440, "x": 0, "y": 0}
    card = AV.TestCard(root, mon, "offset now  0 ms", lambda: None,
                       lambda: None)
    root.update()
    area = 100.0 * card.w * card.h / (mon["width"] * mon["height"])
    check("the card is a window, not the whole screen",
          card.w < mon["width"] and card.h < mon["height"] and area < 40,
          "%dx%d, %.0f%% of the screen" % (card.w, card.h, area))
    # card.x/card.y, not winfo_x: an unmapped Toplevel reports 0, which is a
    # perfectly plausible-looking top-left corner.
    check("it sits in the middle of the monitor",
          card.x == (mon["width"] - card.w) // 2
          and card.y == (mon["height"] - card.h) // 2,
          "at +%d+%d" % (card.x, card.y))
    root.update()
    check("and Windows puts it where the card says it is",
          abs(card.top.winfo_x() - card.x) <= 2
          and abs(card.top.winfo_y() - card.y) <= 2,
          "reported +%d+%d" % (card.top.winfo_x(), card.top.winfo_y()))
    card.start()
    for _ in range(40):
        root.update()
        time.sleep(0.005)
    card.top.event_generate("<Escape>", when="now")
    root.update()
    time.sleep(0.2)
    root.update()
    check("Escape closes it", card._done)

    # And with the tick loop dead - which is what a swallowed error looks like
    # from outside - the guard still has to take it off the screen.
    rang = []
    card2 = AV.TestCard(root, mon, "guard", lambda: None,
                        lambda: rang.append(1))
    card2._tick = lambda: None
    card2.start()
    limit = (AV.TOTAL_MS + AV.GUARD_MS) / 1000.0 + 3
    t0 = time.perf_counter()
    while not card2._done and time.perf_counter() - t0 < limit:
        root.update()
        time.sleep(0.005)
    check("a dead tick loop still closes it", card2._done and bool(rang),
          "after %.1fs" % (time.perf_counter() - t0))
    root.destroy()


# ---------------------------------------------------------------------------
# 2. what the panel leaves for the daemon, and what it puts on the card
# ---------------------------------------------------------------------------

def panel():
    trig = nabd.AV_TEST_TRIGGER
    trig.unlink(missing_ok=True)
    played = []
    real_play, real_card = S.winsound.PlaySound, AV.TestCard
    # Record WHAT was played, not just how many: the primer goes through the
    # same call, and counting both together reads as an extra click.
    S.winsound.PlaySound = lambda snd, *a, **k: played.append(str(snd))
    seen = {}

    def small(parent, monitor, note, on_click, on_done):
        seen["note"] = note
        return real_card(parent, SMALL, note, on_click, on_done)

    AV.TestCard = S.AV.TestCard = small
    p = S.Panel(daemon=True)
    p.auto_dismiss = False
    p._warm_layout()
    p._pump()
    t0 = time.perf_counter()
    while not p._warm and time.perf_counter() - t0 < 120:
        p.root.update()
        time.sleep(0.01)

    def settle(sec):
        end = time.perf_counter() + sec
        while time.perf_counter() < end:
            p.root.update()
            time.sleep(0.001)

    def quiet(limit=12.0):
        end = time.perf_counter() + limit
        while time.perf_counter() < end:
            if not (p._sliding or p._closing or p._capturing):
                break
            p.root.update()
            time.sleep(0.002)
        settle(0.3)

    def idle():
        while p._avtest is not None:
            p.root.update()
            time.sleep(0.002)

    try:
        # A cold buffer means nothing would be there to save. Saying so beats
        # a button that silently does nothing - which is what it used to be.
        real_rate = S.measured_bytes_per_sec
        S.measured_bytes_per_sec = lambda sample=15: None
        p.toggle()
        quiet()
        p._av_test()
        settle(0.2)
        check("a cold buffer is refused, and says so",
              not trig.exists() and "recorded" in p.sync_help.cget("text"),
              repr(p.sync_help.cget("text")[:46]))
        # From source the data dir IS the project folder, whose ring buffer is
        # whatever some earlier test left in it - so the real reading here is
        # None and every case below would be refused.
        S.measured_bytes_per_sec = lambda sample=15: 8_000_000.0
        p.sync_help.set(S.AV_HELP)

        p.start["audio_offset_ms"] = -150
        p.cfg["audio_offset_ms"] = -150
        p.dirty.discard("audio_offset_ms")
        if not p._shown:
            p.toggle()
            quiet()
        pressed = time.time()
        p._av_test()
        settle(0.05)
        raw = trig.read_text(encoding="utf-8").split() if trig.exists() else []
        check("the button leaves a note for the daemon", len(raw) == 2,
              repr(" ".join(raw)))
        if len(raw) == 2:
            at, secs = float(raw[0]), int(raw[1])
            lead = at - pressed
            check("it names when to save, not now",
                  abs(lead - (AV.TOTAL_MS / 1000.0 + 0.3)) < 0.5,
                  "save at +%.1fs, card runs %.1fs"
                  % (lead, AV.TOTAL_MS / 1000.0))
            # wanted+1 segments, less the newest - ffmpeg still has it open and
            # it is routinely skipped as unreadable.
            seg = nabd.DEFAULTS["segment_seconds"]
            reach = max(1, int(round(secs / seg))) * seg
            need = AV.TOTAL_MS / 1000.0 + float(nabd.DEFAULTS["save_delay"])
            check("the window holds the card and the settle, with a segment "
                  "to spare", reach >= need,
                  "reaches %ds, needs %.1fs" % (reach, need))
        check("the panel gets out of shot", not p._shown or p._closing)
        idle()
        check("the card is told the offset in force",
              seen.get("note", "").endswith("150 ms"), repr(seen.get("note")))
        clicks = [x for x in played if x.endswith("av_click.wav")]
        primes = [x for x in played if x.endswith("av_prime.wav")]
        check("every click reached the sound card",
              len(clicks) == len(AV.LADDER) + AV.CLAPS,
              "%d of %d" % (len(clicks), len(AV.LADDER) + AV.CLAPS))
        check("the output device is primed before the pattern",
              len(primes) >= 1)
        check("it puts itself away", p._avtest is None and not p._modal)

        # Dirty AFTER the re-open: opening prewarms, which reloads config and
        # clears dirty.
        trig.unlink(missing_ok=True)
        seen.clear()
        if not p._shown:
            p.toggle()
            quiet()
        p.cfg["audio_offset_ms"] = -120
        p.dirty.add("audio_offset_ms")
        p._av_test()
        settle(0.05)
        idle()
        check("an unsaved slider is called out, not quietly tested",
              "not saved" in seen.get("note", ""), repr(seen.get("note")))
        S.measured_bytes_per_sec = real_rate
    finally:
        trig.unlink(missing_ok=True)
        S.winsound.PlaySound, AV.TestCard = real_play, real_card
        S.AV.TestCard = real_card
        try:
            p._closing = True
            p.root.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 3. the daemon reading it back
# ---------------------------------------------------------------------------

class _Fake:
    poll_av_test = nabd.App.poll_av_test

    def __init__(self):
        self.calls = []

    def _av_test(self, at, seconds):
        self.calls.append((at, seconds))


def daemon():
    trig = nabd.AV_TEST_TRIGGER
    app = _Fake()

    trig.write_text("%.3f 20" % (time.time() + 9), encoding="utf-8")
    app.poll_av_test()
    time.sleep(0.2)
    check("a good note is acted on and consumed",
          len(app.calls) == 1 and not trig.exists())

    app.calls.clear()
    trig.write_text("%.3f 20" % (time.time() + 600), encoding="utf-8")
    app.poll_av_test()
    time.sleep(0.2)
    check("a note from the far future is ignored", not app.calls)

    # The dangerous direction. A note the daemon was not running to see
    # outlives its own moment; acting on it saves whatever is on screen now and
    # opens a player over the top of it.
    app.calls.clear()
    trig.write_text("%.3f 20" % (time.time() - 3600), encoding="utf-8")
    app.poll_av_test()
    time.sleep(0.2)
    check("a note whose moment has passed is ignored", not app.calls)

    app.calls.clear()
    trig.write_text("nonsense", encoding="utf-8")
    app.poll_av_test()
    time.sleep(0.2)
    check("garbage is dropped, not raised",
          not app.calls and not trig.exists())

    app.calls.clear()
    app.poll_av_test()
    check("no note is a no-op", not app.calls)

    # And a real short save, if there are segments to make one from.
    segs = sorted(nabd.BUFFER_DIR.glob("seg_*.ts"))
    if len(segs) < 12:
        skip("a short save honours its length and destination",
             "only %d segments in the buffer" % len(segs))
        return
    out = HERE / "_avsync_out.mp4"
    out.unlink(missing_ok=True)
    cfg = dict(nabd.DEFAULTS)
    cfg["output_dir"] = str(HERE)
    cfg["save_delay"] = 0.2
    done = {}
    clip = nabd.Clipper(cfg, nabd.find_ffmpeg(), None)
    clip.save(on_done=lambda *a: done.update(
        zip(("ok", "detail", "seconds", "size", "path"), a)),
        seconds=S.AV_CLIP_SECONDS, out_path=out)
    t0 = time.perf_counter()
    while not done and time.perf_counter() - t0 < 90:
        time.sleep(0.05)
    got = done.get("seconds") or 0
    need = AV.TOTAL_MS / 1000.0 + float(nabd.DEFAULTS["save_delay"])
    check("a short save lands where it was told",
          bool(done.get("ok")) and out.exists(), str(done.get("detail"))[:60])
    check("it uses the asked-for length, not the user's whole buffer",
          0 < got < 60, "%ds (clip_seconds is %ds)" % (got, cfg["clip_seconds"]))
    check("and still reaches back over the card and the settle", got >= need,
          "%ds, needs %.1fs" % (got, need))
    check("nothing lands in the clips folder",
          not list(HERE.glob("nab_*.mp4")))
    out.unlink(missing_ok=True)


def main():
    print("-- where the slider's zero is --")
    baseline()
    print("\n-- the click can be played at all --")
    sound()
    print("\n-- the gap between a flash and its click --")
    timing()
    print("\n-- the card as a window, and the ways out of it --")
    window()
    print("\n-- what the panel leaves, and what it shows --")
    panel()
    print("\n-- the daemon reading it back --")
    daemon()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
