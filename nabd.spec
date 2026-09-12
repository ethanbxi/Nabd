# PyInstaller spec for Nab'd.
#
# One binary in three roles: the tray app, the settings panel (--settings) and
# the banner helper (--banner). Frozen there is no interpreter to hand a script
# to, so the helpers are this same exe re-invoked with a flag - which is why
# settings/banner/theme/brand are forced in as hidden imports even though
# nothing imports them at module scope.
#
# onedir, not onefile: onefile unpacks to a temp folder on every launch, and
# the banner helper starts on every nab.

import os
from pathlib import Path

APP = Path(os.getcwd())
FFMPEG = APP / "vendor" / "ffmpeg.exe"

datas = [(str(APP / "brand" / "render" / "*.png"), "brand/render")]
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
        "settings", "banner", "theme", "brand",
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
