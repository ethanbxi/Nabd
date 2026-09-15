"""Can you bind a key that Nab'd is already listening for?

    python _test/rebind_test.py

RegisterHotKey is system-wide and exclusive. While Nab'd holds a combo the
keystroke goes to Nab'd and to nothing else - including Nab'd's own settings
window - so pressing the key you wanted to bind took a nab instead of being
read, and there was no way to type it in at all.

The panel therefore asks the app to let go while it listens. Only saving
stops; the ring buffer goes on recording, so nothing is lost while a key is
being set. What has to hold:

  it lets go      a real RegisterHotKey claim is released when the hold goes
                  on, and the keystroke reaches the window underneath.
  it takes back   and reclaims the key afterwards, without a restart.
  it never sticks the note carries a deadline, and every way out of a capture
                  releases it - including the panel sliding away mid-capture.
"""
import ctypes
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import nabd  # noqa: E402

PASS, FAIL = [], []
u = ctypes.windll.user32


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def claimed(spec):
    """Is the combo free? Claiming it briefly is the only way to ask."""
    mods, vk = nabd.parse_hotkey(spec)
    done = threading.Event()
    out = {}

    def probe():
        ok = bool(u.RegisterHotKey(None, 77, mods, vk))
        out["free"] = ok
        if ok:
            u.UnregisterHotKey(None, 77)
        done.set()

    threading.Thread(target=probe, daemon=True).start()
    done.wait(3)
    return not out.get("free", False)


def listener():
    print("-- a real claim, let go and taken back --")
    # F24 - nothing else on a machine wants it, so the result is about this
    # code rather than about whatever else is running.
    spec = "f24"
    hold = threading.Event()
    fired = []
    hk = nabd.HotkeyListener(spec, lambda: fired.append(1), hotkey_id=91,
                             hold=hold)
    hk.start()
    hk.ok.wait(6)
    time.sleep(0.3)
    check("the listener claims its key", hk.registered, repr(hk.error))
    check("...and the key really is taken system-wide", claimed(spec))

    hold.set()
    hk.sync()
    for _ in range(40):
        if not hk.registered:
            break
        time.sleep(0.05)
    check("a hold releases it", not hk.registered and hk.suspended)
    check("...so the key is free for the window underneath", not claimed(spec))

    hold.clear()
    hk.sync()
    for _ in range(40):
        if hk.registered:
            break
        time.sleep(0.05)
    check("clearing the hold takes it back", hk.registered)
    check("...and it is ours again", claimed(spec))

    # A press while held must not nab, even if one was already queued.
    hold.set()
    hk.sync()
    time.sleep(0.3)
    before = len(fired)
    u.PostThreadMessageW(hk._tid, 0x0312, 91, 0)     # WM_HOTKEY by hand
    time.sleep(0.3)
    check("a press that slips through while held does not nab",
          len(fired) == before, "%d fired" % (len(fired) - before))
    hk.shutdown()


def shipped_defaults():
    """What a machine that has never run this gets.

    Distribution makes these load-bearing: nobody else is going to find the
    settings panel before they find out whether the key works.
    """
    print("\n-- the defaults a fresh install starts with --")
    import json
    import tempfile

    d = nabd.DEFAULTS
    # Insert is the obvious key and therefore the contested one - overlays and
    # rival recorders claim it at logon, and the first claimant wins outright.
    check("the nab key is not bare Insert", d["hotkey"] != "insert",
          repr(d["hotkey"]))
    check("the nab key carries a modifier",
          "+" in d["hotkey"], repr(d["hotkey"]))
    check("it parses", bool(nabd.parse_hotkey(d["hotkey"])), repr(d["hotkey"]))
    check("the open key parses",
          bool(nabd.parse_hotkey(d["open_hotkey"])), repr(d["open_hotkey"]))
    check("the two are different", d["hotkey"] != d["open_hotkey"])
    # A backup that duplicates the nab key is skipped at bind time; shipping
    # one at all only matters if it is a DIFFERENT key, and it should not be.
    check("no backup key is shipped", not d["hotkey_alt"],
          repr(d["hotkey_alt"]))

    # Nothing from the machine this was built on.
    leaked = {k: v for k, v in d.items()
              if isinstance(v, str) and (":\\" in v or v.startswith("C:"))}
    check("no paths from the build machine", not leaked, repr(leaked))
    check("the clips folder is worked out on the machine, not shipped",
          d["output_dir"] == "", repr(d["output_dir"]))

    real = nabd.CONFIG_PATH
    tmp = Path(tempfile.mkdtemp()) / "config.json"
    nabd.CONFIG_PATH = tmp
    try:
        cfg = nabd.load_config()
        check("a first run picks its own clips folder",
              bool(cfg["output_dir"]), cfg["output_dir"])
        check("a first run picks its own frame rate",
              isinstance(cfg["fps"], int) and 24 <= cfg["fps"] <= 480,
              "%s fps" % cfg["fps"])
        check("a first run starts A/V-calibrated",
              cfg["audio_offset_ms"] == 0
              and nabd.AUDIO_BASELINE_MS != 0,
              "slider 0, pipeline %+d ms" % nabd.AUDIO_BASELINE_MS)
        check("a first run has a sound", bool(cfg["capture_sound"]),
              repr(cfg["capture_sound"]))
        nabd.save_config(cfg)
        stored = json.loads(tmp.read_text(encoding="utf-8"))
        check("every shipped key round-trips to disk",
              set(stored) == set(nabd.DEFAULTS),
              repr(sorted(set(nabd.DEFAULTS) - set(stored))))
    finally:
        nabd.CONFIG_PATH = real


def note():
    print("\n-- the note the panel leaves --")

    class FakeApp:
        poll_hotkey_hold = nabd.App.poll_hotkey_hold
        hotkey = alt_hotkey = open_hotkey = None

        def __init__(self):
            self._hold = threading.Event()

    app = FakeApp()
    nabd.HOTKEY_HOLD.unlink(missing_ok=True)
    app.poll_hotkey_hold()
    check("no note means the keys stay ours", not app._hold.is_set())

    nabd.HOTKEY_HOLD.write_text("%.3f" % (time.time() + 90), encoding="utf-8")
    app.poll_hotkey_hold()
    check("a live note releases them", app._hold.is_set())

    # A panel that died mid-capture must not leave the app deaf for ever.
    nabd.HOTKEY_HOLD.write_text("%.3f" % (time.time() - 1), encoding="utf-8")
    app.poll_hotkey_hold()
    check("an expired note is ignored", not app._hold.is_set())

    nabd.HOTKEY_HOLD.write_text("not a number", encoding="utf-8")
    app.poll_hotkey_hold()
    check("a corrupt note is ignored", not app._hold.is_set())
    nabd.HOTKEY_HOLD.unlink(missing_ok=True)


def duplicate():
    """Rebinding onto the backup key is the obvious move once you discover the
    backup is the one that works - and it used to make the app report its own
    key as taken by another app."""
    print("\n-- the nab key and the backup set to the same combo --")
    bound = []

    class FakeApp:
        start_hotkey = nabd.App.start_hotkey
        save_clip = open_settings = None

        def __init__(self, cfg):
            self.cfg = cfg

        def _bind(self, spec, action, hotkey_id, label):
            if spec:
                bound.append((spec, label))
            return None

    FakeApp({"hotkey": "alt+insert", "hotkey_alt": "alt+insert",
             "open_hotkey": "ctrl+alt+n"}).start_hotkey()
    check("the backup is not claimed twice",
          [s for s, _ in bound].count("alt+insert") == 1,
          repr([s for s, _ in bound]))

    bound.clear()
    FakeApp({"hotkey": "insert", "hotkey_alt": "alt+insert",
             "open_hotkey": "ctrl+alt+n"}).start_hotkey()
    check("a different backup is still claimed",
          ("alt+insert", "nab (backup)") in bound, repr(bound))


def panel():
    """Every way out of a capture has to give the keys back."""
    print("\n-- the panel releases on every exit --")
    import settings as S
    nabd.HOTKEY_HOLD.unlink(missing_ok=True)
    p = S.Panel(daemon=True)
    p.auto_dismiss = False
    p._warm_layout()
    p._pump()
    t0 = time.perf_counter()
    while not p._warm and time.perf_counter() - t0 < 120:
        p.root.update()
        time.sleep(0.01)

    def pump(n=20):
        for _ in range(n):
            p.root.update()
            time.sleep(0.005)

    try:
        p._capture("hotkey", p.hk_nab)
        pump()
        check("listening leaves a note", nabd.HOTKEY_HOLD.exists())
        p._cancel_capture()
        pump()
        check("cancelling takes it away", not nabd.HOTKEY_HOLD.exists())

        # A key landing does not go through _cancel_capture, so it is its own
        # way out - and used to be the one that never let go.
        p._capture("hotkey", p.hk_nab)
        pump()
        ev = type("E", (), {"keysym": "F9", "state": 0})()
        p._on_key(ev)
        pump()
        check("a key landing takes it away too",
              not nabd.HOTKEY_HOLD.exists())

        p._capture("hotkey", p.hk_nab)
        pump()
        p.toggle()                      # open, then slide away mid-capture
        end = time.perf_counter() + 12
        while time.perf_counter() < end:
            if not (p._sliding or p._closing or p._capturing):
                break
            p.root.update()
            time.sleep(0.002)
        p.dismiss()
        end = time.perf_counter() + 12
        while time.perf_counter() < end:
            if not (p._sliding or p._closing or p._capturing):
                break
            p.root.update()
            time.sleep(0.002)
        pump()
        check("closing mid-capture takes it away",
              not nabd.HOTKEY_HOLD.exists())
    finally:
        nabd.HOTKEY_HOLD.unlink(missing_ok=True)
        try:
            p._closing = True
            p.root.destroy()
        except Exception:
            pass


def main():
    shipped_defaults()
    listener()
    note()
    duplicate()
    panel()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
