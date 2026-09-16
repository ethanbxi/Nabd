"""Updates: what gets installed, and what must never be.

    python _test/update_test.py

Handing a downloaded file to the shell with /SILENT is the most dangerous
thing nab'd does, so most of this is about what does NOT reach that call: the
wrong name, a truncated download, something that is not a Windows executable.

The rest is the shape of the thing. A screen recorder that stops the buffer
because a release happened is worse than one a version behind, so new builds
are downloaded in the background and installed at the next launch, in the one
moment where the interruption costs nothing.
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import nabd                          # noqa: E402
import nabd_update as UP             # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def versions():
    print("-- comparing versions --")
    for a, b, want in (("2.2.0", "2.1.0", True), ("2.1.0", "2.1.0", False),
                       ("2.0.9", "2.1.0", False), ("2.10.0", "2.9.0", True),
                       ("3.0", "2.1.0", True), ("2.1", "2.1.0", False),
                       ("v2.2.0".lstrip("v"), "2.1.0", True)):
        check("%s newer than %s is %s" % (a, b, want), UP.newer(a, b) == want)
    check("10 beats 9 rather than losing on a string compare",
          UP.newer("2.10.0", "2.9.0") and not UP.newer("2.9.0", "2.10.0"))


def guards(tmp):
    print("\n-- what must never reach a silent installer --")
    # The real floor is tens of megabytes. Writing that repeatedly just to
    # prove a size check is a waste of a disk this app already fills for a
    # living - so the floor is lowered for the cases below and asserted here.
    check("the real floor is big enough to mean something",
          UP.MIN_BYTES >= 1024 * 1024, "%d bytes" % UP.MIN_BYTES)
    UP.MIN_BYTES = 2048
    real = tmp / "NabdSetup-9.9.9.exe"
    real.write_bytes(b"MZ" + b"\0" * (UP.MIN_BYTES + 10))
    check("a plausible installer passes", UP._plausible(real))

    short = tmp / "short.exe"
    short.write_bytes(b"MZ" + b"\0" * 10)
    check("a truncated download is refused", not UP._plausible(short))

    notexe = tmp / "NabdSetup-9.9.9-bad.exe"
    notexe.write_bytes(b"<!DOCTYPE html>" + b"\0" * (UP.MIN_BYTES + 10))
    check("an error page dressed as an exe is refused",
          not UP._plausible(notexe))

    check("a missing file is refused", not UP._plausible(tmp / "nope.exe"))

    # stage() refuses a name that is not the release's own, before any request
    # is made at all.
    for bad in ("evil.exe", "NabdSetup-1.0.0.zip", "setup.exe",
                "..\\\\Nabd.exe"):
        check("stage refuses the asset name %r" % bad,
              UP.stage(tmp, "http://127.0.0.1:1/x", bad, "1.0.0") is None)

    check("apply refuses anything implausible",
          not UP.apply(short, relaunch=False))


def staging(tmp):
    print("\n-- staging, and when it gets installed --")
    UP.clear(tmp)
    check("nothing staged to begin with", UP.staged(tmp, "2.1.0") is None)

    newer = UP.staged_dir(tmp) / "NabdSetup-2.2.0.exe"
    newer.write_bytes(b"MZ" + b"\0" * (UP.MIN_BYTES + 10))
    found = UP.staged(tmp, "2.1.0")
    check("a newer staged build is found", found == newer, str(found))
    check("...and is ignored once it is what is running",
          UP.staged(tmp, "2.2.0") is None)

    older = UP.staged_dir(tmp) / "NabdSetup-1.0.0.exe"
    older.write_bytes(b"MZ" + b"\0" * (UP.MIN_BYTES + 10))
    check("an older staged build is never installed",
          UP.staged(tmp, "2.2.0") is None)

    junk = UP.staged_dir(tmp) / "NabdSetup-3.0.0.exe"
    junk.write_bytes(b"nope")
    check("a half-downloaded build is not offered",
          UP.staged(tmp, "2.2.0") is None)
    UP.clear(tmp)


def wiring():
    print("\n-- how it is wired in --")
    check("auto_update is a config key, on by default",
          nabd.DEFAULTS.get("auto_update") is True)
    # Inside main(), not across the file: the App class is DEFINED hundreds
    # of lines before main() ever calls it, so a whole-file position compare
    # proves nothing.
    import inspect
    body = inspect.getsource(nabd.main)
    check("a staged build is applied before the app is built",
          "nabd_update.staged" in body
          and body.index("nabd_update.staged") < body.index("App(cfg, ffmpeg)"),
          "apply at %d, App at %d" % (body.index("nabd_update.staged"),
                                      body.index("App(cfg, ffmpeg)")))
    check("and it returns rather than carrying on into a restart",
          "return 0" in body.split("nabd_update.apply")[1][:120])
    check("the setting gates the request, not the result",
          'cfg.get("auto_update"' in body
          or 'cfg.get("auto_update"' in inspect.getsource(nabd.App))
    iss = (APP / "installer.iss").read_text(encoding="utf-8")
    check("the installer relaunches after a silent update",
          "Relaunching" in iss and "relaunch|0" in iss)
    check("...and only when asked to", "Check: Relaunching" in iss)
    check("the normal postinstall entry is still skipifsilent",
          "skipifsilent" in iss)


def live():
    print("\n-- against the real repository --")
    found = UP.check("0.0.1")
    if found is None:
        print("  SKIP  no network, or no release published")
        return
    version, url, name = found
    check("a release is found", bool(version), version)
    check("the asset is an installer",
          name.startswith(UP.ASSET_PREFIX) and name.endswith(".exe"), name)
    check("the download url is GitHub's",
          url.startswith("https://github.com/") or
          url.startswith("https://objects.githubusercontent.com/"), url[:48])
    check("nothing is offered when we are current",
          UP.check("999.0.0") is None)


def main():
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    versions()
    guards(tmp)
    staging(tmp)
    wiring()
    live()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
