"""
Install the brand faces (Outfit, JetBrains Mono) for the current user.

Both are open-licensed. Installs per-user - no admin, no system font folder -
and registers them so Tk can see them without a reboot. Re-runnable.

    python install_fonts.py
"""
import ctypes
import io
import sys
import urllib.request
import winreg
import zipfile
from pathlib import Path

FONT_DIR = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"
REG_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"

# Static instances, not the variable builds: GDI (and therefore Tk) exposes a
# variable font as a single default instance, so the weights would collapse.
WANTED = ("Outfit-Regular", "Outfit-Medium", "Outfit-SemiBold", "Outfit-Bold",
          "JetBrainsMono-Regular", "JetBrainsMono-Bold")

SOURCES = [
    ("Outfit", "https://github.com/Outfitio/Outfit-Fonts/archive/refs/heads/"
               "main.zip"),
    ("JetBrains Mono", "https://github.com/JetBrains/JetBrainsMono/releases/"
                       "download/v2.304/JetBrainsMono-2.304.zip"),
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nabd-setup"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def wanted(name):
    stem = Path(name).stem
    return Path(name).suffix.lower() == ".ttf" and stem in WANTED


def install(path):
    """Copy in and register. Returns the face name Windows will report."""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    dest = FONT_DIR / path.name
    dest.write_bytes(path.read_bytes())

    # "Family Style (TrueType)" is the shape the registry expects.
    stem = path.stem
    family, _, style = stem.partition("-")
    spaced = "".join(f" {c}" if c.isupper() else c for c in family).strip()
    label = f"{spaced} {style}".strip() if style else spaced
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as key:
        winreg.SetValueEx(key, f"{label} (TrueType)", 0, winreg.REG_SZ,
                          str(dest))
    # Make it usable in this session too, not just after a sign-out.
    ctypes.windll.gdi32.AddFontResourceW(ctypes.c_wchar_p(str(dest)))
    return label


installed = []
for label, url in SOURCES:
    print(f"fetching {label}...")
    try:
        blob = fetch(url)
    except Exception as exc:
        print(f"  FAILED: {exc}")
        continue
    scratch = Path(f"{FONT_DIR}/../_nabd_fonts").resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members = [m for m in z.namelist() if wanted(m)]
        if not members:
            print("  no matching static TTFs in the archive")
            continue
        for member in members:
            out = scratch / Path(member).name
            out.write_bytes(z.read(member))
            installed.append(install(out))
            print(f"  installed {out.stem}")
    for leftover in scratch.glob("*.ttf"):
        leftover.unlink()
    scratch.rmdir()

# Tell running apps the font table changed.
HWND_BROADCAST, WM_FONTCHANGE = 0xFFFF, 0x001D
ctypes.windll.user32.SendMessageTimeoutW(
    HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0, 1000, None)

print(f"\n{len(installed)} faces installed" if installed
      else "\nnothing installed")
sys.exit(0 if installed else 1)
