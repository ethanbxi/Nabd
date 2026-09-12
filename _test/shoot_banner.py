"""Capture the banner across its life: draw-on, settle, and the draining rule."""
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import banner as B  # noqa: E402
import nabd  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)
ffmpeg = nabd.find_ffmpeg()

SCREEN_W = 2560
PAD = 8
X = SCREEN_W - B.WIDTH - B.MARGIN_RIGHT - PAD
Y = B.MARGIN_TOP - PAD
W, H = B.WIDTH + PAD * 2, B.HEIGHT + PAD * 2
CROP = f"{W}:{H}:{X}:{Y}"

proc = subprocess.Popen(
    [sys.executable, str(APP / "banner.py"), "Nab'd Last 5 Minutes",
     "ok", "0"], creationflags=nabd.CREATE_NO_WINDOW)

shots = []
for i in range(6):
    dest = OUT / f"life_{i}.png"
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-init_hw_device", "d3d11va", "-filter_complex",
         f"ddagrab=output_idx=0:framerate=30,hwdownload,format=bgra,"
         f"crop={CROP}",
         "-frames:v", "1", str(dest)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    if dest.exists():
        shots.append(dest)
    time.sleep(0.22)

if shots:
    sheet = Image.new("RGB", (W, H * len(shots)), "#0A0A0C")
    for i, path in enumerate(shots):
        sheet.paste(Image.open(path).convert("RGB"), (0, i * H))
    sheet.save(OUT / "banner_life.png")
    print(f"wrote {OUT / 'banner_life.png'} from {len(shots)} frames")

proc.wait(timeout=15)


