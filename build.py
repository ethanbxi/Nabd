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

    # The save banner is drawn entirely from pre-rendered frames. Rendering
    # them at launch would cost exactly what onedir was chosen to save, so they
    # are built here. Regenerated only when missing - the assertion that frame
    # 16 is the logo runs with them.
    frames = APP / "assets" / "banner"
    if not list(frames.glob("*/ring_16.png")):
        import make_banner_assets
        make_banner_assets.main(str(frames))
    print(f"  banner art  {len(list(frames.glob('*/*.png')))} frames")

    # The capture sound, checked rather than merely counted. Its length has to
    # equal the banner's TOTAL_MS to the sample - async playback dies with the
    # banner process, so a longer file loses its tail and a shorter one leaves
    # the exit unscored - and winsound has no volume control, so the mastering
    # level IS the playback level. Both are cheap to break by re-rendering and
    # neither shows up until someone hears it.
    import nabd_banner
    import nabd_sound
    if nabd_sound.DURATION_MS != nabd_banner.TOTAL_MS:
        print(f"  sound       FAILED: nabd_sound.DURATION_MS is "
              f"{nabd_sound.DURATION_MS}ms but the banner runs "
              f"{nabd_banner.TOTAL_MS}ms - regenerate with synth5.py")
        return False
    wavs = sorted((APP / "assets" / "sound").glob("*.wav"))
    for wav in wavs:
        try:
            nabd_sound.verify(wav)
        except AssertionError as exc:
            print(f"  sound       FAILED: {wav.name}: {exc}")
            return False
    print(f"  sound       {len(wavs)} verified at {nabd_sound.DURATION_MS}ms")
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
