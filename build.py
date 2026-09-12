"""
Build the Nab'd installer.

    python build.py

Stages: gather what has to ship (ffmpeg, fonts, rendered artwork), freeze the
app with PyInstaller, then wrap the result with Inno Setup. The output is a
single distributable .exe in dist/.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent
VENDOR = APP / "vendor"
DIST = APP / "dist"
FONT_DIR = Path.home() / "AppData/Local/Microsoft/Windows/Fonts"
WANTED_FONTS = ("Outfit-Regular", "Outfit-Medium", "Outfit-SemiBold",
                "Outfit-Bold", "JetBrainsMono-Regular", "JetBrainsMono-Bold")


def step(msg):
    print(f"\n=== {msg} ===")


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return Path(exe)
    packages = (Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet"
                / "Packages")
    for candidate in packages.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return candidate
    return None


def find_iscc():
    exe = shutil.which("iscc")
    if exe:
        return Path(exe)
    for root in (os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("ProgramFiles", ""),
                 str(Path.home() / "AppData/Local/Programs")):
        if not root:
            continue
        for candidate in Path(root).glob("Inno Setup*/ISCC.exe"):
            return candidate
    return None


def gather():
    step("gathering payload")
    VENDOR.mkdir(exist_ok=True)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("  ffmpeg NOT FOUND - the installer would ship without it")
        return False
    dest = VENDOR / "ffmpeg.exe"
    # winget's copy is a resolved symlink; copy the real bytes.
    if not dest.exists() or dest.stat().st_size != ffmpeg.stat().st_size:
        shutil.copyfile(ffmpeg, dest)
    print(f"  ffmpeg      {dest.stat().st_size / 1048576:.0f} MB")

    fonts = VENDOR / "fonts"
    fonts.mkdir(exist_ok=True)
    found = 0
    for name in WANTED_FONTS:
        src = FONT_DIR / f"{name}.ttf"
        if src.exists():
            shutil.copyfile(src, fonts / src.name)
            found += 1
    print(f"  fonts       {found}/{len(WANTED_FONTS)} faces")

    renders = list((APP / "brand" / "render").glob("*.png"))
    print(f"  artwork     {len(renders)} rendered assets")
    if not renders:
        print("  run render_assets.py first")
        return False

    # Wizard BMPs are generated, so a fresh clone has none. They cost a second
    # to make and need nothing but Pillow, unlike render_assets.py.
    art = APP / "installer"
    if not list(art.glob("wizard-*.bmp")):
        import make_wizard_art
        make_wizard_art.main()
    print(f"  wizard art  {len(list(art.glob('wizard*.bmp')))} images")
    return True


def freeze():
    step("freezing with PyInstaller")
    for path in (APP / "build", DIST / "Nabd"):
        shutil.rmtree(path, ignore_errors=True)
    res = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                          "--clean", "nabd.spec"], cwd=str(APP))
    if res.returncode != 0:
        return False
    exe = DIST / "Nabd" / "Nabd.exe"
    if not exe.exists():
        print("  no exe produced")
        return False
    size = sum(f.stat().st_size for f in (DIST / "Nabd").rglob("*")
               if f.is_file())
    print(f"  {exe}  ({size / 1048576:.0f} MB on disk)")
    return True


def package():
    step("packaging with Inno Setup")
    iscc = find_iscc()
    if not iscc:
        print("  ISCC.exe not found - install Inno Setup")
        return False
    res = subprocess.run([str(iscc), "installer.iss"], cwd=str(APP))
    if res.returncode != 0:
        return False
    made = sorted(DIST.glob("NabdSetup*.exe"))
    for path in made:
        print(f"  {path}  ({path.stat().st_size / 1048576:.0f} MB)")
    return bool(made)


def main():
    if not gather():
        return 1
    if not freeze():
        return 1
    if not package():
        return 1
    step("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
