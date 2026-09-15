"""The app -> banner-helper hand-off: does every nab actually get a banner?

    python _test/handoff_test.py

The app does not draw the banner; it writes a trigger file and a resident
helper polls it every 40ms. A single nab writes that file two or three times -
show_banner, then the figures from _clip_early, then the completion - and the
gaps between those writes are milliseconds. Everything here is about what
happens when those writes land closer together than the poll.

Three faults lived in that gap, and between them the Nabbed banner appeared
once, silently, and then never again:

  the rename   os.replace over a file the reader has open fails outright on
               Windows rather than waiting, and the payload was lost with it.

  the sound    show_banner's payload carried the sound; update_banner's did
               not - and the update is usually the write the helper actually
               sees, so the banner that appeared was the silent one.

  the token    An update for a different nab returned early even when the
               banner it was protecting had already finished. state["current"]
               keeps the last banner for ever, so from the second nab onwards
               there was always a stale token to fail against.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import nabd                          # noqa: E402
import nabd_banner as M              # noqa: E402

PASS, FAIL = [], []
u = ctypes.windll.user32


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


class _Writer:
    _write_banner = nabd.App._write_banner


def payloads():
    print("-- what each payload carries --")
    written = {}

    class FakeApp:
        cfg = dict(nabd.DEFAULTS)
        show_banner = nabd.App.show_banner
        update_banner = nabd.App.update_banner

        def ensure_banner_helper(self):
            pass

        def _write_banner(self, p):
            written.clear()
            written.update(p)

    app = FakeApp()
    app.cfg["notify"] = True
    app.cfg["capture_sound"] = "pip"
    app.update_banner("1:00 - 150 MB", path="x.mp4", token="nab1")
    # It has a title, so it can raise a banner on its own - and anything that
    # can raise one has to be able to score it.
    check("the figures payload can raise a banner",
          bool(written.get("title")), repr(written.get("title")))
    check("...so it carries the sound too", written.get("sound") == "pip",
          repr(written.get("sound")))
    app.cfg["capture_sound"] = "off"
    app.update_banner("1:00", token="nab2")
    check("and honours silence", written.get("sound") == "off",
          repr(written.get("sound")))


def rename_under_a_reader():
    print("\n-- writing the trigger while something has it open --")
    trig = nabd.BANNER_TRIGGER
    trig.write_text("{}", encoding="utf-8")
    w = _Writer()
    # The helper opens it, reads it and closes it - microseconds. Held open
    # for a beat here, which is the race as it actually happens rather than a
    # reader that never lets go.
    import threading
    fh = open(trig, "r", encoding="utf-8")
    threading.Timer(0.02, fh.close).start()
    w._write_banner({"title": "Nabbed", "kind": "ok", "token": "held"})
    try:
        got = json.loads(trig.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        got = {}
    check("the payload still lands", got.get("token") == "held", repr(got))
    check("no .tmp left behind", not trig.with_suffix(".tmp").exists())


def end_to_end():
    """The real helper, fed the way a real nab feeds it."""
    print("\n-- three nabs, figures 15ms behind each (inside one poll) --")
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process -Name 'Nabd' -ErrorAction SilentlyContinue | "
         "Stop-Process -Force -ErrorAction SilentlyContinue"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    time.sleep(2)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    helper = subprocess.Popen([str(pythonw), str(APP / "banner.py"),
                               "--daemon"], cwd=str(APP))
    time.sleep(4)
    w = _Writer()

    def up():
        out = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _):
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == helper.pid and u.IsWindowVisible(h):
                r = wintypes.RECT()
                u.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left > 40:
                    out.append(1)
            return True

        u.EnumWindows(cb, 0)
        return bool(out)

    seen = 0
    try:
        for n in range(1, 4):
            tok = "nab%d" % n
            w._write_banner({"title": "Nabbed", "kind": "ok", "detail": "",
                             "monitor": 0, "delay": 0.2, "sound": "pip",
                             "token": tok})
            time.sleep(0.015)
            w._write_banner({"update": True, "detail": "1:00 - 150 MB",
                             "token": tok, "title": "Nabbed", "kind": "ok",
                             "monitor": 0, "delay": 0.2, "sound": "pip",
                             "path": "", "ready": False})
            end = time.perf_counter() + 2.5
            while time.perf_counter() < end:
                if up():
                    seen += 1
                    break
                time.sleep(0.05)
            time.sleep(M.TOTAL_MS / 1000.0 + 0.8)
        check("every nab raises a banner, not just the first",
              seen == 3, "%d of 3" % seen)
        check("the helper survived all three", helper.poll() is None)
    finally:
        if helper.poll() is None:
            helper.kill()


def main():
    payloads()
    rename_under_a_reader()
    end_to_end()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
