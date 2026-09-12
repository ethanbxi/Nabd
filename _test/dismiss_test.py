"""Clicking away should slide the panel out; staying put should not."""
import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402
import settings as S  # noqa: E402

pythonw = Path(sys.executable).with_name("pythonw.exe")
results = {}


def quiesce():
    """No other Nab'd windows during a focus test.

    A tray app or helper left over from a previous test will take the
    foreground as it starts and dismiss the panel for reasons that have nothing
    to do with the behaviour under test.
    """
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR "
         "Name='python.exe'\" | Where-Object { $_.CommandLine -like "
         "'*nabd.py*' -or $_.CommandLine -like '*banner.py*' -or "
         "$_.CommandLine -like '*settings.py*' } | ForEach-Object { "
         "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    time.sleep(2.5)


quiesce()


def launch():
    p = subprocess.Popen([str(pythonw), str(APP / "settings.py")], cwd=str(APP))
    # The tray does the same: without it Windows will not let a
    # background-launched process take the foreground.
    ctypes.windll.user32.AllowSetForegroundWindow(p.pid)
    time.sleep(6)   # build + device scan + slide-in
    return p


print("[1] panel should stay open while nothing steals focus")
panel = launch()
alive_before = panel.poll() is None
time.sleep(5)
results["stays open when left alone"] = alive_before and panel.poll() is None
print(f"    still running: {panel.poll() is None}")

print("\n[2] stealing focus with another process's window")
thief = tk.Tk()
thief.title("focus thief")
thief.geometry("320x180+80+80")
thief.configure(bg="#222")
thief.deiconify()
thief.lift()
thief.focus_force()
thief.update_idletasks()
# focus_force alone does not take the Win32 foreground away from another
# process - the same restriction the panel itself has to work around.
hwnd = (ctypes.windll.user32.GetParent(thief.winfo_id()) or thief.winfo_id())
S.force_foreground(hwnd)
for _ in range(20):
    thief.update()
    time.sleep(0.05)

fg = ctypes.windll.user32.GetForegroundWindow()
pid = ctypes.wintypes.DWORD()
ctypes.windll.user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
print(f"    foreground pid now {pid.value} (test is {os.getpid()}, "
      f"panel is {panel.pid})")

closed = False
for _ in range(80):
    thief.update()
    time.sleep(0.1)
    if panel.poll() is not None:
        closed = True
        break
results["dismisses when focus leaves"] = closed
print(f"    panel exited: {closed}")

thief.destroy()
if panel.poll() is None:
    panel.kill()

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if all(results.values()) else 1)
