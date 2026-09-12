"""Report which candidate hotkeys are actually free on this machine.

RegisterHotKey fails outright if another process already owns the combo, which
makes it a reliable conflict test (ShadowPlay, Game Bar, Medal, Discord...).
"""
import ctypes
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

CANDIDATES = [
    "alt+f9", "alt+f10", "alt+f1", "alt+f8",
    "ctrl+alt+f9", "ctrl+alt+f10", "ctrl+alt+f12",
    "ctrl+alt+c", "ctrl+alt+r", "ctrl+alt+s",
    "ctrl+shift+f9", "ctrl+shift+s", "ctrl+f12",
    "win+alt+c", "ctrl+alt+insert", "ctrl+alt+end",
]

results = []


def probe():
    user32 = ctypes.windll.user32
    for i, spec in enumerate(CANDIDATES, start=100):
        try:
            mods, vk = nabd.parse_hotkey(spec)
        except ValueError as exc:
            results.append((spec, False, str(exc)))
            continue
        if user32.RegisterHotKey(None, i, mods, vk):
            user32.UnregisterHotKey(None, i)
            results.append((spec, True, ""))
        else:
            err = ctypes.get_last_error()
            results.append((spec, False, f"taken (err {err})"))


# RegisterHotKey is per-thread, so probe from one dedicated thread.
t = threading.Thread(target=probe)
t.start()
t.join()

free = [s for s, ok, _ in results if ok]
for spec, ok, note in results:
    print(f"  {'FREE ' if ok else 'TAKEN'}  {spec:<18} {note}")

print(f"\n{len(free)}/{len(CANDIDATES)} free")
print("recommended:", free[0] if free else "none available")

