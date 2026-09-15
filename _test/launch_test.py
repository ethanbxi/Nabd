"""Opening the app should show the app.

    python _test/launch_test.py

Four things start Nabd.exe and nothing told them apart: the installer's "start
now" box, the Start Menu and desktop icons, a double click on the exe, and
Windows at sign-in. The first three are somebody opening the app and want a
window; the last must stay out of the way. So sign-in gets --autostart and
everything else means "show me".

The panel is a separate resident process, and it is told at spawn time rather
than through the trigger file. The trigger cannot do this job: the daemon takes
its baseline stamp before building ~340 widgets, so a write from the app that
spawned it either lands before the baseline and is swallowed, or has to be
timed against a build no other process can observe.
"""
import ctypes
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

import nabd  # noqa: E402

PASS, FAIL = [], []
u = ctypes.windll.user32


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def decision():
    print("-- which launches show a window --")
    cases = [
        (["Nabd.exe"], True, True, "Start Menu, desktop, double click"),
        (["Nabd.exe"], False, True, "first run, launched by hand"),
        (["Nabd.exe", "--autostart"], True, False, "Windows at sign-in"),
        (["Nabd.exe", "--autostart"], False, True,
         "sign-in, but never configured"),
    ]
    for argv, have_cfg, want, what in cases:
        got = nabd.wants_panel(argv, have_cfg)
        check("%s -> %s" % (what, "panel" if want else "silent"), got == want)


def panel_on_screen(pid, limit=40.0):
    """Wait for a panel that is actually being SEEN by that process.

    IsWindowVisible is not the question. A warm panel parks itself shown but
    layered at alpha 0 - that is the whole trick that makes an open nothing
    but an animation - so by Win32's reckoning the hidden panel is visible and
    full size. The alpha is what separates armed from presented.
    """
    end = time.perf_counter() + limit
    while time.perf_counter() < end:
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _):
            owner = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value != pid or not u.IsWindowVisible(h):
                return True
            r = wintypes.RECT()
            u.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left < 200 or r.bottom - r.top < 200:
                return True
            # c_ubyte, not wintypes.BYTE: that one is SIGNED, so a fully
            # opaque window reads back as -1 and never looks opaque at all.
            alpha = ctypes.c_ubyte()
            key, flags = wintypes.DWORD(), wintypes.DWORD()
            if not u.GetLayeredWindowAttributes(h, ctypes.byref(key),
                                                ctypes.byref(alpha),
                                                ctypes.byref(flags)):
                alpha.value = 255          # not layered at all: plainly shown
            if alpha.value > 200:
                found.append((r.right - r.left, r.bottom - r.top,
                              alpha.value))
            return True

        u.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.2)
    return None


def helper(flags, label, expect_window):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    proc = subprocess.Popen([str(pythonw), str(APP / "settings.py")] + flags)
    try:
        # A panel that is going to appear has to build first, so allow it the
        # same patience either way - otherwise "no window" just means "not yet".
        got = panel_on_screen(proc.pid, 40.0 if expect_window else 18.0)
        if expect_window:
            check("%s shows the panel" % label, got is not None,
                  "%dx%d at alpha %d" % got if got else "nothing appeared")
        else:
            check("%s stays hidden" % label, got is None,
                  "a %dx%d window at alpha %d appeared" % got if got else
                  "armed but not presented, as it should be")
        check("%s keeps the helper alive" % label, proc.poll() is None)
    finally:
        if proc.poll() is None:
            proc.kill()
        time.sleep(1.5)


def spawned():
    print("\n-- the resident panel, told at spawn time --")
    # Nothing else holding the daemon mutex, or the helper exits immediately.
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process -Name 'Nabd' -ErrorAction SilentlyContinue | "
         "Stop-Process -Force -ErrorAction SilentlyContinue; "
         "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         "Where-Object { $_.CommandLine -like '*settings.py*' } | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
         "-ErrorAction SilentlyContinue }"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    time.sleep(2.5)
    helper(["--daemon", "--show"], "--daemon --show", True)
    helper(["--daemon"], "--daemon alone", False)


def spawn_args():
    print("\n-- what the app asks the helper for --")
    seen = {}

    class FakeApp:
        ensure_settings_helper = nabd.App.ensure_settings_helper
        _settings = None
        _job = None

    import types
    real_popen = subprocess.Popen

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return types.SimpleNamespace(poll=lambda: None, _handle=0)

    subprocess.Popen = fake
    try:
        FakeApp().ensure_settings_helper(show=True)
        check("show=True passes --show", "--show" in seen["cmd"],
              " ".join(str(c) for c in seen["cmd"][-3:]))
        FakeApp().ensure_settings_helper()
        check("the default does not", "--show" not in seen["cmd"],
              " ".join(str(c) for c in seen["cmd"][-3:]))
    finally:
        subprocess.Popen = real_popen


def trigger_meaning():
    """A hotkey toggles; launching the exe opens.

    Both arrive down the same trigger file, so the file has to say which was
    meant - otherwise running the exe while the panel happened to be up
    dismissed it, which looks like the app closing itself.
    """
    print("\n-- toggle versus open, down one trigger file --")
    import settings as S
    p = S.Panel(daemon=True)
    p.auto_dismiss = False
    p._warm_layout()
    p._pump()
    t0 = time.perf_counter()
    while not p._warm and time.perf_counter() - t0 < 120:
        p.root.update()
        time.sleep(0.01)

    def quiet(limit=12.0):
        end = time.perf_counter() + limit
        while time.perf_counter() < end:
            if not (p._sliding or p._closing or p._capturing):
                break
            p.root.update()
            time.sleep(0.002)
        for _ in range(60):
            p.root.update()
            time.sleep(0.005)

    def fire(text):
        nabd.SETTINGS_TRIGGER.write_text(text, encoding="utf-8")
        p._trigger_stamp = None          # force _watch to see a change
        p._watch()
        quiet()

    try:
        fire(nabd.SETTINGS_SHOW)
        check("'show' opens a hidden panel", p._shown)
        fire(nabd.SETTINGS_SHOW)
        check("'show' leaves an open panel alone", p._shown)
        fire(str(time.time()))
        check("a timestamp still toggles it shut", not p._shown)
        fire(str(time.time()))
        check("...and back open", p._shown)
    finally:
        try:
            p._closing = True
            p.root.destroy()
        except Exception:
            pass


def main():
    decision()
    trigger_meaning()
    spawn_args()
    spawned()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
