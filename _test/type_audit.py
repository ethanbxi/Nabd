"""Compare the UI's type scale against the published one."""
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand  # noqa: E402
import theme as T  # noqa: E402

# From the guidelines: role -> (face, px, line-height, weight, use)
PUBLISHED = {
    "Display": ("Outfit", 44, 1.05, 600, "Landing headlines only"),
    "H1": ("Outfit", 30, 1.15, 500, "Page and dialog titles"),
    "H2": ("Outfit", 20, 1.30, 500, "Section headings"),
    "Body": ("Outfit", 15, 1.55, 400, "Everything people read"),
    "Small": ("Outfit", 13, 1.50, 400, "Captions, helper text"),
    "Mono": ("JetBrains Mono", 12, 1.50, 400, "Hotkeys, paths, durations, IDs"),
}

root = tk.Tk()
root.withdraw()
T.init()

WEIGHT_FAMILY = {400: brand.font("Outfit"), 500: brand.font("Outfit Medium"),
                 600: brand.font("Outfit SemiBold")}

print(f"{'role':<9} {'published':<34} {'in theme.py':<34} match")
print("-" * 92)

mapping = {"Display": "F_DISPLAY", "H1": "F_H1", "H2": "F_H2",
           "Body": "F_BODY", "Small": "F_SMALL", "Mono": "F_MONO"}
problems = []
for role, (face, px, lh, weight, _) in PUBLISHED.items():
    name = mapping.get(role)
    if not name:
        print(f"{role:<9} {face} {px}px/{weight:<24} {'(not used)':<34} -")
        continue
    have = getattr(T, name)
    want_family = (WEIGHT_FAMILY[weight] if face == "Outfit"
                   else brand.font("JetBrains Mono"))
    ok = have[0] == want_family and have[1] == -px
    if not ok:
        problems.append(f"{name}: have {have}, want ({want_family!r}, {-px})")
    print(f"{role:<9} {face} {px}px w{weight:<20} "
          f"{have[0]} {abs(have[1])}px{'':<12} {'OK' if ok else 'MISMATCH'}")

print("\nExtra styles in theme.py that the guidelines do not define:")
for name in dir(T):
    if name.startswith("F_") and name not in mapping.values():
        print(f"  {name} = {getattr(T, name)}")

print("\nInstalled faces:")
families = set(tkfont.families())
for weight, fam in WEIGHT_FAMILY.items():
    print(f"  {weight}: {fam}{'' if fam in families else '  (MISSING)'}")
mono = brand.font("JetBrains Mono")
print(f"  mono: {mono}{'' if mono in families else '  (MISSING)'}")

if problems:
    print("\nMismatches:")
    for p in problems:
        print("  " + p)
root.destroy()
sys.exit(1 if problems else 0)
