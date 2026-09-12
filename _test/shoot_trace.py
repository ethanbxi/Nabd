"""Catch several frames of the draw-on so the stroke order can be checked."""
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import banner as B  # noqa: E402
import nabd  # noqa: E402
from PIL import Image  # noqa: E402

# Where the ring actually lands, derived rather than guessed.
SCREEN_W = 2560
RX = SCREEN_W - B.WIDTH - B.MARGIN_RIGHT + 16
RY = B.MARGIN_TOP + (B.HEIGHT - B.RING) // 2
PAD = 9
CROP = f"{B.RING + PAD * 2}:{B.RING + PAD * 2}:{RX - PAD}:{RY - PAD}"
CELL = B.RING + PAD * 2

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)
ffmpeg = nabd.find_ffmpeg()

proc = subprocess.Popen(
    [sys.executable, str(APP / "banner.py"), "Nab'd Last 5 Minutes",
     "ok", "0"], creationflags=nabd.CREATE_NO_WINDOW)

time.sleep(0.45)  # catch the draw-on in progress
shots = []
for i in range(6):
    dest = OUT / f"trace_{i}.png"
    subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-init_hw_device", "d3d11va", "-filter_complex",
         f"ddagrab=output_idx=0:framerate=30,hwdownload,format=bgra,"
         f"crop={CROP}",
         "-frames:v", "1", str(dest)],
        capture_output=True, creationflags=nabd.CREATE_NO_WINDOW)
    if dest.exists():
        shots.append(dest)
    time.sleep(0.10)

# Contact sheet, so the sequence can be read in one look.
if shots:
    sheet = Image.new("RGB", (len(shots) * CELL, CELL), "#0A0A0C")
    for i, path in enumerate(shots):
        sheet.paste(Image.open(path).convert("RGB"), (i * CELL, 0))
    sheet = sheet.resize((len(shots) * CELL * 3, CELL * 3), Image.NEAREST)
    sheet.save(OUT / "trace_sheet.png")
    print(f"wrote {OUT / 'trace_sheet.png'} from {len(shots)} frames")

proc.wait(timeout=15)

