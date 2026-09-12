"""The confirmation must appear on the keypress, not after the settle delay.

Measures when the banner *window* becomes visible, not merely when a process
exists - the helper is resident, so process presence proves nothing.
"""
import ctypes
import json
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402

CONFIG = APP / "config.json"
BACKUP = APP / "config.json.blbak"
KEYEVENTF_KEYUP = 0x0002
VK_FOR_MOD = {nabd.MOD_CONTROL: 0x11, nabd.MOD_ALT: 0x12,
              nabd.MOD_SHIFT: 0x10, nabd.MOD_WIN: 0x5B}


def daemon_pid():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
         "Where-Object { $_.CommandLine -like '*banner.py*--daemon*' } | "
         "Select-Object -First 1).ProcessId"],
        capture_output=True, text=True,
        creationflags=nabd.CREATE_NO_WINDOW).stdout.strip()
    return int(out) if out.isdigit() else None


def has_visible_window(pid):
    """The daemon's root is withdrawn, so any visible window is a live banner."""
    found = []

    def cb(hwnd, _lparam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            owner = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(
                hwnd, ctypes.byref(owner))
            if owner.value == pid:
                found.append(hwnd)
        return True

    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(proto(cb), 0)
    return bool(found)


def banner_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR "
         "Name='python.exe'\" | Where-Object { $_.CommandLine -like "
         "'*banner.py*' }).ProcessId -join ','"],
        capture_output=True, text=True,
        creationflags=nabd.CREATE_NO_WINDOW).stdout.strip()
    return {int(x) for x in out.split(",") if x.strip().isdigit()}


shutil.copyfile(CONFIG, BACKUP)
proc = None
results = {}
# A separately running Nab'd has a helper of its own; only ours is in scope.
pre_existing = banner_pids()
try:
    cfg = json.loads(CONFIG.read_text())
    save_delay = float(cfg.get("save_delay", 3.0))
    hotkey = cfg.get("hotkey", "ctrl+alt+f9")
    clips = Path(nabd.load_config()["output_dir"])
    clips.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in clips.glob("*.mp4")}

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    proc = subprocess.Popen([str(pythonw), str(APP / "nabd.py")], cwd=str(APP))
    print(f"app launched (hotkey={hotkey}, save_delay={save_delay}s); filling buffer")
    time.sleep(16)
    if proc.poll() is not None:
        print("FAIL: app exited early")
        sys.exit(1)

    pid = daemon_pid()
    results["banner helper is resident"] = pid is not None
    print(f"banner helper pid: {pid}")
    if pid is None:
        raise SystemExit(1)
    results["no banner showing yet"] = not has_visible_window(pid)

    mods, vk = nabd.parse_hotkey(hotkey)
    held = [v for bit, v in VK_FOR_MOD.items() if mods & bit]
    u = ctypes.windll.user32

    print(f"pressing {hotkey}")
    t0 = time.time()
    for v in held:
        u.keybd_event(v, 0, 0, 0)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    for v in reversed(held):
        u.keybd_event(v, 0, KEYEVENTF_KEYUP, 0)

    seen_at = None
    while time.time() - t0 < 12:
        if has_visible_window(pid):
            seen_at = time.time()
            break
        time.sleep(0.01)

    if seen_at is None:
        print("FAIL: banner window never appeared")
        results["banner appeared"] = False
    else:
        latency = seen_at - t0
        print(f"banner on screen after {latency*1000:.0f} ms "
              f"(settle delay is {save_delay}s)")
        results["banner appeared"] = True
        results["banner is immediate (<600ms)"] = latency < 0.6

    saved = None
    while time.time() - t0 < 45:
        new = {p.name for p in clips.glob("*.mp4")} - before
        if new:
            saved = new.pop()
            break
        time.sleep(0.25)
    results["clip still saved"] = saved is not None
    if saved:
        print(f"clip written {time.time()-t0:.1f}s after the keypress")
        try:
            (clips / saved).unlink()
        except OSError:
            pass
finally:
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    shutil.copyfile(BACKUP, CONFIG)
    BACKUP.unlink(missing_ok=True)
    time.sleep(1.5)

# The job object reaps asynchronously, so poll rather than snapshot.
stray = banner_pids() - pre_existing
for _ in range(20):
    if not stray:
        break
    time.sleep(0.5)
    stray = banner_pids() - pre_existing
results["helper dies with the app"] = not stray
if stray:
    print(f"    stray helpers: {sorted(stray)}")

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
sys.exit(0 if results and all(results.values()) else 1)
