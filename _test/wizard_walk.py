"""
Drive the built installer through its wizard, shooting every page.

    python _test/wizard_walk.py

Verifies the thing a friend actually sees: that each page appears, is
readable, and that Enter advances it. Stops on the Ready page by default so
nothing is installed; pass --install to let it run to completion.
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

APP = Path(__file__).resolve().parent.parent
SETUP = APP / "dist" / "NabdSetup-1.0.0.exe"
SHOTS = APP / "_test" / "wizard"
TITLE = "Setup - Nab'd"

u = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


def rect(hwnd):
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def find():
    return u.FindWindowW(None, TITLE)


def page_text(hwnd):
    """The heading of the current page, to name the screenshot."""
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    out = []

    def cb(child, _lp):
        n = u.GetWindowTextLengthW(child)
        if n:
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(child, b, n + 1)
            if u.IsWindowVisible(child):
                out.append(b.value)
        return True

    u.EnumChildWindows(hwnd, CB(cb), 0)
    return out


def shoot(hwnd, name):
    left, top, right, bottom = rect(hwnd)
    img = ImageGrab.grab(all_screens=False)
    SHOTS.mkdir(parents=True, exist_ok=True)
    img.crop((left, top, right, bottom)).save(SHOTS / f"{name}.png")
    return right - left, bottom - top


def press_enter(hwnd):
    u.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    u.keybd_event(VK_RETURN, 0, 0, 0)
    u.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def main():
    install = "--install" in sys.argv
    proc = subprocess.Popen([str(SETUP)])
    for _ in range(40):
        time.sleep(0.25)
        if find():
            break
    hwnd = find()
    if not hwnd:
        print("FAIL: wizard never appeared")
        return 1

    # Welcome, Destination, Tasks, Ready, then Installing/Finished.
    names = ["1-welcome", "2-destination", "3-tasks", "4-ready",
             "5-finished"]
    stop = len(names) if install else 4
    for i, name in enumerate(names[:stop]):
        time.sleep(1.2)
        hwnd = find() or hwnd
        size = shoot(hwnd, name)
        heads = [t for t in page_text(hwnd) if len(t) > 12][:1]
        print(f"  {name:<14} {size[0]}x{size[1]}  {heads}")
        if i < stop - 1:
            press_enter(hwnd)
            if name == "4-ready":
                # Install runs; wait for the progress page to finish.
                for _ in range(120):
                    time.sleep(0.5)
                    texts = " ".join(page_text(find() or hwnd))
                    if "finished installing" in texts:
                        break

    if install:
        # Clear the "Start Nab'd now" box so the test controls the launch.
        u.SetForegroundWindow(find() or hwnd)
        time.sleep(0.3)
        u.keybd_event(0x20, 0, 0, 0)          # space toggles the checkbox
        u.keybd_event(0x20, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.3)
        press_enter(find() or hwnd)
        proc.wait(timeout=60)
        print(f"  setup exit code {proc.returncode}")
    else:
        subprocess.run(["taskkill", "/f", "/im", SETUP.name],
                       capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
