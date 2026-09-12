"""Repair characters mangled by a PowerShell encoding round-trip.

Non-ASCII glyphs in source are fragile: a read/write through the wrong codepage
turns them into mojibake silently. Repairs the damage and rewrites the glyphs
as escapes so it cannot happen again.
"""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

# mangled -> intended, as a Python escape
REPAIRS = {
    "â€¹": "\\u2039",   # single left angle quote
    "â€º": "\\u203a",   # single right angle quote
    "â€°": "\\u203a",   # right angle, mangled differently
    "‹": "\\u2039",
    "›": "\\u203a",
    "✕": "\\u2715",               # the close glyph
    "âœ•": "\\u2715",
}

changed = []
for name in ("settings.py", "theme.py", "banner.py", "nabd.py", "brand.py"):
    path = APP / name
    text = path.read_text(encoding="utf-8", errors="replace")
    original = text
    for bad, good in REPAIRS.items():
        if bad in text:
            text = text.replace(f'"{bad}"', f'"{good}"')
            text = text.replace(f"'{bad}'", f"'{good}'")
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed.append(name)

print("repaired:", ", ".join(changed) or "nothing")

# Report anything non-ASCII left in source, so it can be judged.
for name in ("settings.py", "theme.py", "banner.py", "nabd.py", "brand.py"):
    path = APP / name
    for i, line in enumerate(path.read_text(encoding="utf-8",
                                            errors="replace").splitlines(), 1):
        odd = [c for c in line if ord(c) > 127]
        if odd:
            print(f"  {name}:{i}  {odd}  {line.strip()[:70]}")
sys.exit(0)
