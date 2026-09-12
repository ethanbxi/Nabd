"""Exercise the device discovery the settings UI depends on."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

ok = True

print("--- speakers (WASAPI loopback capable) ---")
speakers = nabd.list_speakers()
for s in speakers:
    print(f"  {'* ' if s['default'] else '  '}{s['name']}")
if not speakers:
    print("  FAIL: none found")
    ok = False

print("\n--- microphones (DirectShow) ---")
mics = nabd.list_microphones()
for m in mics:
    print(f"    {m}")
if not mics:
    print("  (none - desktop audio only)")

print("\n--- monitors ---")
monitors = nabd.list_monitors()
for i, m in enumerate(monitors):
    tag = " (Primary)" if m["primary"] else ""
    print(f"    Monitor {i+1}: {m['width']}x{m['height']} at x={m['x']}{tag}")
if not monitors:
    print("  FAIL: none found")
    ok = False

print("\n--- hotkey availability ---")
for spec in ("ctrl+alt+f9", "ctrl+alt+c", "alt+f9"):
    print(f"    {spec:<14} {'free' if nabd.hotkey_available(spec) else 'TAKEN'}")

print("\n--- monitor preview capture ---")
for i in range(len(monitors)):
    dest = Path(tempfile.gettempdir()) / f"nabd_preview_test_{i}.png"
    got = nabd.grab_preview(i, dest)
    size = dest.stat().st_size if dest.exists() else 0
    print(f"    Monitor {i+1}: {'OK' if got else 'FAILED'}  {size/1024:.0f} KB")
    if not got:
        ok = False

print("\n--- config round-trip ---")
cfg = nabd.load_config()
missing = [k for k in nabd.DEFAULTS if k not in cfg]
print(f"    keys present : {len(cfg)}  missing: {missing or 'none'}")
print(f"    output_dir   : {cfg['output_dir']}")
print(f"    clip_seconds : {cfg['clip_seconds']}")
if missing:
    ok = False

print("\nPASS" if ok else "\nFAIL")
sys.exit(0 if ok else 1)
