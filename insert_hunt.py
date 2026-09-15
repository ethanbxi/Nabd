"""
Find out what claims the Insert hotkey during sign-in.

Runs from a logon scheduled task, polls RegisterHotKey(Insert) hard, and
records which processes appeared in the window where Insert went from free to
taken. That transition is the only observable trace the owner leaves: Windows
offers no way to ask who holds a hotkey.

Writes insert_hunt.log next to nabd.log, then deletes its own task.
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
VK_INSERT, MOD_NOREPEAT = 0x2D, 0x4000
DATA = Path(os.environ["LOCALAPPDATA"]) / "Nabd"
LOG = DATA / "insert_hunt.log"
RUN_FOR = 240.0


def free():
    ok = u32.RegisterHotKey(None, 0x4E41, MOD_NOREPEAT, VK_INSERT)
    if ok:
        u32.UnregisterHotKey(None, 0x4E41)
    return bool(ok)


def snapshot():
    arr = (wintypes.DWORD * 4096)()
    got = wintypes.DWORD()
    psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr),
                        ctypes.byref(got))
    out = {}
    for pid in arr[: got.value // 4]:
        h = k32.OpenProcess(0x1000, False, pid)
        if not h:
            continue
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(32768)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            out[pid] = Path(buf.value).name
        k32.CloseHandle(h)
    return out


def main():
    lines = []
    t0 = time.time()
    seen = snapshot()
    was = free()
    lines.append("t=  0.00  Insert %s  (%d processes already up)"
                 % ("FREE" if was else "TAKEN", len(seen)))
    if not was:
        lines.append("          NOTE: already taken before this started - the "
                     "owner runs earlier than a logon task.")
        lines.append("          up at that moment: "
                     + ", ".join(sorted(set(seen.values()))))

    last_snap = t0
    ended = False
    while time.time() - t0 < RUN_FOR:
        now = free()
        t = time.time() - t0
        if now != was:
            cur = snapshot()
            fresh = sorted({n for p, n in cur.items() if p not in seen})
            lines.append("t=%6.2f  Insert -> %s"
                         % (t, "FREE" if now else "TAKEN"))
            lines.append("          started since last check: "
                         + (", ".join(fresh) or "(none)"))
            seen = cur
            was = now
            if not now:
                lines.append("          (stopping probe so as not to race it)")
                ended = True
                break
        if time.time() - last_snap > 0.4:
            seen.update(snapshot())
            last_snap = time.time()
        time.sleep(0.03)
    if not ended:
        lines.append("t=%.0f  window closed with no further change" % RUN_FOR)

    lines.append("")
    lines.append("Nab'd's own view:")
    try:
        nl = (DATA / "nabd.log").read_text(encoding="utf-8",
                                           errors="replace").splitlines()
        lines += ["  " + x for x in nl
                  if "hotkey" in x or "starting" in x][-8:]
    except OSError as exc:
        lines.append("  (unreadable: %s)" % exc)

    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["schtasks", "/Delete", "/TN", "NabdInsertHunt", "/F"],
                   capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
