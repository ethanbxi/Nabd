"""Screenshot the settings panel so the rendering can be inspected."""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import nabd  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)
ffmpeg = nabd.find_ffmpeg()
pythonw = Path(sys.executable).with_name("pythonw.exe")

panel = subprocess.Popen([str(pythonw), str(APP / "settings.py"), "--pin"],
                         cwd=str(APP))
ctypes.windll.user32.AllowSetForegroundWindow(panel.pid)
time.sleep(7)

WIDTH, CROP_H = 620, 780
x = ctypes.windll.user32.GetSystemMetrics(0) - WIDTH

for name, crop in (("panel_top", f"{WIDTH}:{CROP_H}:{x}:0"),
                   ("panel_bottom", f"{WIDTH}:{CROP_H}:{x}:"
                                    f"{ctypes.windll.user32.GetSystemMetrics(1) - CROP_H}")):
    dest = OUT / f"{name}.png"
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-init_hw_device", "d3d11va",
         "-filter_complex",
         f"ddagrab=output_idx=0:framerate=5,hwdownload,format=bgra,crop={crop}",
         "-frames:v", "1", str(dest)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    print(f"{dest}  {'ok' if dest.exists() else 'FAILED'}")

try:
    panel.kill()
except OSError:
    pass
