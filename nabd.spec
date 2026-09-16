# PyInstaller spec for Nab'd.
#
# One binary in four roles: the tray app, the main window (--window), the
# settings drawer (--settings) and the banner helper (--banner). Frozen there is
# no interpreter to hand a script to, so the helpers are this same exe
# re-invoked with a flag - which is why window/settings/banner/brand are forced
# in as hidden imports even though nothing imports them at module scope.
#
# onedir, not onefile: onefile unpacks to a temp folder on every launch, and
# the banner helper starts on every nab.

import os
from pathlib import Path

APP = Path(os.getcwd())
FFMPEG = APP / "vendor" / "ffmpeg.exe"

datas = [(str(APP / "brand" / "render" / "*.png"), "brand/render")]
# The banner's frames, one directory per DPI scale and field colour. Kept as
# loose PNGs rather than packed: the banner loads only the set it needs.
for _d in sorted((APP / "assets" / "banner").glob("*")):
    if _d.is_dir():
        datas.append((str(_d / "*.png"), f"assets/banner/{_d.name}"))
# The capture sound. nabd_sound.asset_dir() resolves sys._MEIPASS when
# frozen and the module's own directory from source, so this path is the one
# it looks in either way. synth5.py generates these and needs numpy+scipy -
# it is a build-time tool and must not be imported by anything that ships.
if (APP / "assets" / "sound").is_dir():
    datas.append((str(APP / "assets" / "sound" / "*.wav"), "assets/sound"))
if FFMPEG.exists():
    datas.append((str(FFMPEG), "ffmpeg"))
fonts = APP / "vendor" / "fonts"
if fonts.exists():
    datas.append((str(fonts / "*.ttf"), "fonts"))

a = Analysis(
    ["nabd.py"],
    pathex=[str(APP)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "settings", "banner", "brand", "window", "nabd_window",
        "nabd_tokens", "nabd_paint", "nabd_ui",
        "nabd_banner", "nabd_ease", "nabd_panel_open",
        "pyaudiowpatch", "pystray._win32",
        "PIL.ImageTk", "PIL._tkinter_finder",
        "tkinter", "tkinter.filedialog", "tkinter.font",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["svglib", "reportlab", "rlPyCairo", "PyInstaller",
              "numpy", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Nabd",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # tray app: no console window, ever
    icon=str(APP / "icon.ico"),
    version=None,
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Nabd",
)
