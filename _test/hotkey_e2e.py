"""Launch the real tray app and drive it with a synthetic global hotkey."""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402

cfg = nabd.load_config()
clips = Path(cfg["output_dir"])
clips.mkdir(parents=True, exist_ok=True)
before = {p.name for p in clips.glob("*.mp4")}

log_path = APP / "nabd.log"
log_mark = log_path.stat().st_size if log_path.exists() else 0

pythonw = Path(sys.executable).with_name("pythonw.exe")
print(f"launching {pythonw.name} {APP.name}/nabd.py")
proc = subprocess.Popen([str(pythonw), str(APP / "nabd.py")], cwd=str(APP))

BUFFER_FILL = 20
print(f"letting the buffer fill for {BUFFER_FILL}s...")
time.sleep(BUFFER_FILL)

if proc.poll() is not None:
    print(f"FAIL: app exited early (code {proc.returncode})")
    sys.exit(1)

# Fire the configured combo through the real input stack.
KEYEVENTF_KEYUP = 0x0002
VK_FOR_MOD = {nabd.MOD_CONTROL: 0x11, nabd.MOD_ALT: 0x12,
              nabd.MOD_SHIFT: 0x10, nabd.MOD_WIN: 0x5B}
mods, vk = nabd.parse_hotkey(cfg["hotkey"])
held = [v for bit, v in VK_FOR_MOD.items() if mods & bit]

user32 = ctypes.windll.user32
print(f"sending {cfg['hotkey']}")
for v in held:
    user32.keybd_event(v, 0, 0, 0)
user32.keybd_event(vk, 0, 0, 0)
time.sleep(0.05)
user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
for v in reversed(held):
    user32.keybd_event(v, 0, KEYEVENTF_KEYUP, 0)

saved = None
for _ in range(60):
    time.sleep(0.5)
    new = {p.name for p in clips.glob("*.mp4")} - before
    if new:
        saved = new.pop()
        break

print("\n--- new log output ---")
with open(log_path, encoding="utf-8") as fh:
    fh.seek(log_mark)
    print(fh.read().strip())

try:
    proc.terminate()
    proc.wait(timeout=10)
except Exception:
    proc.kill()

if not saved:
    print("\nFAIL: hotkey did not produce a clip")
    sys.exit(1)

path = clips / saved
print(f"\nclip: {path}")
print(f"size: {path.stat().st_size/1048576:.2f} MB")
print("PASS")

