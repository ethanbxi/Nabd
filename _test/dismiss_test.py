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
HERE = Path(__file__).resolve().parent
results = {}

# A window in another process, raised to the foreground and held there.
THIEF = (
    "import ctypes, time, tkinter as tk" + chr(10) +
    "ctypes.windll.shcore.SetProcessDpiAwareness(2)" + chr(10) +
    "r = tk.Tk()" + chr(10) +
    "r.geometry('360x140+200+200')" + chr(10) +
    "r.title('focus thief')" + chr(10) +
    "r.update()" + chr(10) +
    "u = ctypes.windll.user32" + chr(10) +
    "h = u.GetParent(r.winfo_id()) or r.winfo_id()" + chr(10) +
    "u.ShowWindow(h, 5); u.BringWindowToTop(h); u.SetForegroundWindow(h)" +
    chr(10) +
    "t0 = time.perf_counter()" + chr(10) +
    "while time.perf_counter() - t0 < 3.5:" + chr(10) +
    "    r.update(); time.sleep(0.01)" + chr(10) +
    "r.destroy()" + chr(10)
)


def quiesce():
    """No other Nab'd anywhere during a focus test.

    A tray app or helper left over from a previous test will take the
    foreground as it starts and dismiss the panel for reasons that have nothing
    to do with the behaviour under test.

    The INSTALLED build counts too, and it is the easier one to forget. A
    one-shot `settings.py` hands straight over to a running daemon and exits,
    so with Nabd.exe up, [1] read as "the panel closed itself" and [2] read as
    "the panel exited when focus left" - both about a process that was already
    gone. Killing only the python copies is not enough.
    """
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR "
         "Name='python.exe'\" | Where-Object { $_.CommandLine -like "
         "'*nabd.py*' -or $_.CommandLine -like '*banner.py*' -or "
         "$_.CommandLine -like '*settings.py*' } | ForEach-Object { "
         "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };"
         " Get-Process -Name 'Nabd' -ErrorAction SilentlyContinue | "
         "Stop-Process -Force -ErrorAction SilentlyContinue"],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    time.sleep(2.5)
    if S.daemon_running():
        print("    WARNING: a settings daemon is still up; [1] and [2] will "
              "test a handover, not the panel")


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

# ---------------------------------------------------------------------------
# [3] the panel must NOT close for its own popups, dialogs and captures.
#
# Dismissal used to wait 250ms before acting, which hid every one of these
# behind the delay. The test is by process now - the foreground has to belong
# to a different pid - so the wait is gone and the latency is nil. These are
# the cases that wait was standing in for.
# ---------------------------------------------------------------------------
print("")
print("[3] the panel's own windows must not dismiss it")
quiesce()
ctypes.windll.shcore.SetProcessDpiAwareness(2)
p = S.Panel(daemon=True)
p._warm_layout()
p._pump()
t0 = time.perf_counter()
while not p._warm and time.perf_counter() - t0 < 120:
    p.root.update()
    time.sleep(0.01)


def settle(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        p.root.update()
        time.sleep(0.001)


def quiet(limit=10.0):
    end = time.perf_counter() + limit
    while time.perf_counter() < end:
        if not (p._sliding or p._closing or p._capturing):
            break
        p.root.update()
        time.sleep(0.002)
    settle(0.3)


p.toggle()
quiet()
results["opens for the test"] = p._shown

p.spk.open()                      # a Select popup is its own Toplevel
settle(0.9)
results["stays open while its own dropdown is up"] = p._shown and not p._closing
try:
    p.spk.close()
except Exception:
    pass
settle(0.5)

if not p._shown:
    p.toggle()
    quiet()
p._capture("hotkey", p.hk_nab)    # focus_force inside the panel
settle(0.9)
results["stays open during a hotkey capture"] = p._shown and not p._closing
p._cancel_capture()
settle(0.4)

p._modal = True                   # what askdirectory sets
p.auto_dismiss = False
for _ in range(8):
    p._check_dismiss()
    settle(0.08)
results["stays open while a dialog owns it"] = p._shown and not p._closing
p._modal = False
p.auto_dismiss = True
settle(0.3)

p._had_focus = True               # focus moving between its own widgets
for _ in range(5):
    p._focus_left()
    settle(0.06)
results["internal focus moves do not close it"] = p._shown and not p._closing

# [4] and it still goes the instant focus really leaves - no 250ms wait
print("")
print("[4] dismissal latency once the foreground moves away")
if not p._shown:
    p.toggle()
    quiet()
settle(0.4)
started = [None]
real_dismiss = p.dismiss


def spy(*a, **k):
    if started[0] is None:
        started[0] = time.perf_counter()
    return real_dismiss(*a, **k)


p.dismiss = spy
# The thief has to be a SEPARATE process: the dismissal is decided by
# comparing the foreground window's pid against its own, so a Toplevel in
# this process would never look like leaving.
thief_py = HERE / "_thief.py"
thief_py.write_text(THIEF, encoding="utf-8")
proc = subprocess.Popen([str(sys.executable), str(thief_py)])
ctypes.windll.user32.AllowSetForegroundWindow(proc.pid)
stolen = None
end = time.perf_counter() + 10
while time.perf_counter() < end:
    p.root.update()
    fg2 = ctypes.windll.user32.GetForegroundWindow()
    pid2 = ctypes.wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(fg2, ctypes.byref(pid2))
    if fg2 and pid2.value == proc.pid:
        stolen = time.perf_counter()
        break
    time.sleep(0.002)
end = time.perf_counter() + 5
while started[0] is None and time.perf_counter() < end:
    p.root.update()
    time.sleep(0.001)
if stolen and started[0]:
    ms = (started[0] - stolen) * 1000
    print(f"    focus stolen -> dismiss started in {ms:.0f} ms")
    # The FocusOut event can fire before the poll here even notices the
    # steal, so this is allowed to come out slightly negative. It used to
    # sit at ~350ms: a 100ms poll on top of a 250ms debounce.
    results["dismisses within a frame of losing focus"] = ms < 120
else:
    print(f"    no dismissal (stolen={bool(stolen)})")
    results["dismisses within a frame of losing focus"] = False
p.dismiss = real_dismiss
try:
    proc.wait(timeout=10)
except Exception:
    proc.kill()
try:
    thief_py.unlink()
except OSError:
    pass
try:
    p._closing = True
    p.root.destroy()
except Exception:
    pass

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if all(results.values()) else 1)
