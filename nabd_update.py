"""nab'd updates -- check, stage, apply.

Stdlib only; no new dependency. Three deliberate choices:

**It never installs while you are using it.** Updating replaces the exe, which
means stopping the recorder - and a screen recorder that stops the buffer
because a release happened is worse than one that is a version behind. So a new
build is *downloaded* in the background and *applied at the next launch*, in
the moment before the recorder starts, where the interruption costs nothing.
`Update now` exists for when you would rather not wait.

**It only looks when it is allowed to.** Off means no request is made at all -
not a request whose answer is ignored. This is a local screen recorder; the
whole point is that nothing leaves the machine unless it was asked for.

**It cannot install anything but a nab'd installer.** The asset name has to
match the release's own, the file has to be a Windows executable, and it has to
be big enough to be real. A silent installer is the most dangerous thing this
app can run, so what reaches it is narrow on purpose.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "ethanbxi/Nabd"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES = "https://github.com/%s/releases/latest" % REPO

ASSET_PREFIX = "NabdSetup-"
ASSET_SUFFIX = ".exe"
MIN_BYTES = 10 * 1024 * 1024        # a real installer is ~70MB
TIMEOUT = 15


def parts(v):
    out = []
    for chunk in str(v).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        out.append(int(digits) if digits else 0)
    return out


def newer(a, b):
    """Is a newer than b? Numeric, so 2.10 beats 2.9 rather than losing to it."""
    pa, pb = parts(a), parts(b)
    pa += [0] * (len(pb) - len(pa))
    pb += [0] * (len(pa) - len(pb))
    return pa > pb


def check(current):
    """-> (version, url, name) for a newer release, or None.

    None also covers "no network", "rate limited" and "no releases yet". None
    of those is worth interrupting anyone over.
    """
    try:
        req = urllib.request.Request(
            API, headers={"Accept": "application/vnd.github+json",
                          "User-Agent": "nabd/%s" % current})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
    except Exception:
        return None
    tag = str(data.get("tag_name", "")).lstrip("vV")
    if not tag or not newer(tag, current):
        return None
    for asset in data.get("assets") or []:
        name = asset.get("name", "")
        if (name.startswith(ASSET_PREFIX) and name.endswith(ASSET_SUFFIX)
                and asset.get("browser_download_url")):
            return tag, asset["browser_download_url"], name
    return None


def staged_dir(data_dir):
    d = Path(data_dir) / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def staged(data_dir, current):
    """A downloaded installer newer than what is running, or None."""
    try:
        for p in sorted(staged_dir(data_dir).glob(ASSET_PREFIX + "*.exe")):
            v = p.stem[len(ASSET_PREFIX):]
            if newer(v, current) and _plausible(p):
                return p
    except OSError:
        pass
    return None


def _plausible(path):
    """A Windows executable, and big enough to be the real thing.

    What this guards is the only genuinely dangerous thing here: handing a
    downloaded file to the shell with /SILENT. A truncated download is the
    likely case; a substituted one is the one worth being narrow about.
    """
    try:
        if path.stat().st_size < MIN_BYTES:
            return False
        with open(path, "rb") as fh:
            return fh.read(2) == b"MZ"
    except OSError:
        return False


def stage(data_dir, url, name, current):
    """Download to <data>/updates/, atomically. -> path or None."""
    if not (name.startswith(ASSET_PREFIX) and name.endswith(ASSET_SUFFIX)):
        return None
    out = staged_dir(data_dir) / name
    if out.exists() and _plausible(out):
        return out
    tmp = out.with_suffix(".part")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "nabd/%s" % current})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r, \
                open(tmp, "wb") as fh:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        return None
    if not _plausible(tmp):
        try:
            tmp.unlink()
        except OSError:
            pass
        return None
    try:
        os.replace(tmp, out)
    except OSError:
        return None
    return out


def clear(data_dir):
    for p in staged_dir(data_dir).glob(ASSET_PREFIX + "*"):
        try:
            p.unlink()
        except OSError:
            pass


def apply(installer, relaunch=True):
    """Hand off to the installer and get out of its way.

    Per-user install, so no UAC prompt. /relaunch=1 is read by installer.iss,
    which starts nab'd again afterwards - Inno's own postinstall entry is
    skipifsilent and would not.
    """
    if not _plausible(Path(installer)):
        return False
    args = [str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    if relaunch:
        args.append("/relaunch=1")
    try:
        subprocess.Popen(args, close_fds=True)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    import nabd
    print("running  :", nabd.VERSION)
    found = check(nabd.VERSION)
    print("latest   :", found or "nothing newer")
    print("staged   :", staged(nabd.DATA_DIR, nabd.VERSION))
    sys.exit(0)
