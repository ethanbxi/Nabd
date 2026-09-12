"""Full lifecycle test against the real app process.

Covers: hotkey -> clip, banner appearing, config hot-reload, and rebinding the
hotkey while running.
"""
import ctypes
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402

CONFIG = APP / "config.json"
BACKUP = APP / "config.json.testbak"
LOG = APP / "nabd.log"

KEYEVENTF_KEYUP = 0x0002
VK_FOR_MOD = {nabd.MOD_CONTROL: 0x11, nabd.MOD_ALT: 0x12,
              nabd.MOD_SHIFT: 0x10, nabd.MOD_WIN: 0x5B}


def press(spec):
    # Avoid Ctrl+Alt combinations here: Windows treats Ctrl+Alt as AltGr and
    # mangles synthetic injection of it, which fails the test for reasons that
    # have nothing to do with the app.
    mods, vk = nabd.parse_hotkey(spec)
    held = [v for bit, v in VK_FOR_MOD.items() if mods & bit]
    u = ctypes.windll.user32
    for v in held:
        u.keybd_event(v, 0, 0, 0)
    u.keybd_event(vk, 0, 0, 0)
    time.sleep(0.05)
    u.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    for v in reversed(held):
        u.keybd_event(v, 0, KEYEVENTF_KEYUP, 0)


def banner_running():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR "
         "Name='python.exe'\" | Where-Object { $_.CommandLine -like '*banner.py*' }"
         " | Measure-Object).Count"],
        capture_output=True, text=True, creationflags=nabd.CREATE_NO_WINDOW).stdout.strip()
    return out.isdigit() and int(out) > 0


def ffmpeg_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process ffmpeg -ErrorAction SilentlyContinue).Id -join ','"],
        capture_output=True, text=True,
        creationflags=nabd.CREATE_NO_WINDOW).stdout.strip()
    return {int(x) for x in out.split(",") if x.strip().isdigit()}


def wait_for_clip(clips, before, timeout=40):
    for _ in range(timeout * 2):
        time.sleep(0.5)
        new = {p.name for p in clips.glob("*.mp4")} - before
        if new:
            return new.pop()
    return None


def press_until_clip(spec, clips, before, attempts=3, timeout=20):
    """Synthetic input is swallowed whenever a higher-integrity window holds
    focus, so a missed keypress says nothing about the app."""
    for i in range(attempts):
        press(spec)
        got = wait_for_clip(clips, before, timeout)
        if got:
            return got
        print(f"    (no clip after attempt {i + 1}; retrying)")
    return None


shutil.copyfile(CONFIG, BACKUP)
results = {}
proc = None
pre_existing = ffmpeg_pids()   # a separately running Nab'd is not our orphan
try:
    # Start from a known state.
    cfg = json.loads(CONFIG.read_text())
    cfg.update({"clip_seconds": 60, "hotkey": "ctrl+shift+f9"})
    CONFIG.write_text(json.dumps(cfg, indent=2))

    clips = Path(nabd.load_config()["output_dir"])
    clips.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in clips.glob("*.mp4")}
    log_mark = LOG.stat().st_size if LOG.exists() else 0

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    proc = subprocess.Popen([str(pythonw), str(APP / "nabd.py")], cwd=str(APP))
    print("app launched; filling buffer...")
    time.sleep(18)
    if proc.poll() is not None:
        print(f"FAIL: app exited early ({proc.returncode})")
        sys.exit(1)

    # 1. hotkey -> clip.  Banner timing is covered by banner_latency.py; the
    # resident helper makes a process count here meaningless.
    print("\n[1] pressing ctrl+shift+f9")
    clip = press_until_clip("ctrl+shift+f9", clips, before)
    results["clip via hotkey"] = clip is not None
    print(f"    clip={clip}")
    if clip:
        before.add(clip)

    # 2. hot-reload: change length and rebind the hotkey with the app running
    print("\n[2] rewriting config (clip_seconds 60->180, hotkey -> ctrl+shift+f10)")
    cfg = json.loads(CONFIG.read_text())
    cfg.update({"clip_seconds": 180, "hotkey": "ctrl+shift+f10"})
    CONFIG.write_text(json.dumps(cfg, indent=2))

    applied = False
    for _ in range(30):
        time.sleep(1)
        text = LOG.read_text(encoding="utf-8", errors="replace")[log_mark:]
        if "config changed" in text and "ctrl+shift+f10" in text:
            applied = True
            break
    results["config hot-reload"] = applied
    print(f"    applied={applied}")

    # 3. the newly bound hotkey must work, the old one must not
    print("\n[3] pressing the OLD hotkey (should do nothing)")
    press("ctrl+shift+f9")
    time.sleep(4)
    stale = {p.name for p in clips.glob("*.mp4")} - before
    results["old hotkey released"] = not stale
    print(f"    new clips from old hotkey: {len(stale)} (want 0)")

    print("\n[4] refilling buffer, then pressing the NEW hotkey")
    time.sleep(16)
    clip2 = press_until_clip("ctrl+shift+f10", clips, before)
    results["clip via rebound hotkey"] = clip2 is not None
    print(f"    clip={clip2}")

finally:
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    shutil.copyfile(BACKUP, CONFIG)
    BACKUP.unlink(missing_ok=True)
    time.sleep(2)

print("\n--- new log ---")
with open(LOG, encoding="utf-8", errors="replace") as fh:
    fh.seek(log_mark)
    print(fh.read().strip())

print("\n--- results ---")
for name, ok in results.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")

# Only this test's own child matters: a separately running Nab'd has an ffmpeg
# of its own, and counting system-wide reports it as an orphan.
# The job object reaps asynchronously, so poll rather than snapshot.
stray = ffmpeg_pids() - pre_existing
for _ in range(20):
    if not stray:
        break
    time.sleep(0.5)
    stray = ffmpeg_pids() - pre_existing
print(f"  {'PASS' if not stray else 'FAIL'}  no orphaned ffmpeg "
      f"(stray={sorted(stray) or 'none'})")
left = "0" if not stray else str(len(stray))

sys.exit(0 if all(results.values()) and left == "0" else 1)

