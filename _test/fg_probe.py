"""Does the settings panel ever hold the foreground?"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402

u = ctypes.windll.user32


def foreground():
    hwnd = u.GetForegroundWindow()
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    buf = ctypes.create_unicode_buffer(200)
    u.GetWindowTextW(hwnd, buf, 200)
    return hwnd, pid.value, buf.value


pythonw = Path(sys.executable).with_name("pythonw.exe")
panel = subprocess.Popen([str(pythonw), str(APP / "settings.py")], cwd=str(APP))
u.AllowSetForegroundWindow(panel.pid)
print(f"panel pid {panel.pid}\n")

held = False
for i in range(24):
    time.sleep(0.5)
    hwnd, pid, title = foreground()
    mine = pid == panel.pid
    held = held or mine
    if i % 2 == 0 or mine:
        print(f"  t={i*0.5:4.1f}s  fg pid={pid:<6} "
              f"{'<-- PANEL' if mine else ''}  title={title[:46]!r}")

print(f"\npanel ever held foreground: {held}")
try:
    panel.kill()
except OSError:
    pass
