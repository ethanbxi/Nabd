"""Swap the user-facing wording from clip/clips to nab/nabs.

Strings only: internal identifiers (clip_seconds, Clipper, recent_clips) stay
put, since renaming them would churn the config format and the tests for no
visible gain.
"""
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent

EDITS = {
    "settings.py": [
        ('self._section(body, "Recent clips", trailing=pager)',
         'self._section(body, "Recent nabs", trailing=pager)'),
        ('T.Button(actions, "Open clips folder", self._open_clips)',
         'T.Button(actions, "Open nabs folder", self._open_clips)'),
        ('grid = self._section(body, "Clips")',
         'grid = self._section(body, "Nabs")'),
        ('grid = self._section(body, "Clip length")',
         'grid = self._section(body, "Nab length")'),
        ('self._label(grid, 0, "Save clip")',
         'self._label(grid, 0, "Save nab")'),
        ('f"About {size} per clip, and that much stays buffered on disk."',
         'f"About {size} per nab, and that much stays buffered on disk."'),
        ('grid, "Start a fresh buffer after each clip",',
         'grid, "Start a fresh buffer after each nab",'),
        ('text = ("Each clip picks up where the last ended, so clips never "\n                    "overlap.")',
         'text = ("Each nab picks up where the last ended, so nabs never "\n                    "overlap.")'),
        ('text = ("Always keeps the most recent footage, so clips taken "\n                    "close together overlap.")',
         'text = ("Always keeps the most recent footage, so nabs taken "\n                    "close together overlap.")'),
        ('text=f"No clips yet - press {self._pretty(self.hotkey_value)}"',
         'text=f"No nabs yet - press {self._pretty(self.hotkey_value)}"'),
        ('self._note(grid, 5, "Negative pulls audio earlier. Save a clip, watch "\n                            "it, nudge until it matches.")',
         'self._note(grid, 5, "Negative pulls audio earlier. Save a nab, watch "\n                            "it, nudge until it matches.")'),
        ('title="Choose where clips are saved")',
         'title="Choose where nabs are saved")'),
        ('stamp = clip.stem.replace("clip_", "").replace("_", "  ")',
         'stamp = re.sub(r"^(nab|clip)_", "", clip.stem).replace("_", "  ")'),
        ('import queue\nimport sys', 'import queue\nimport re\nimport sys'),
    ],
}

missing = []
for name, pairs in EDITS.items():
    path = APP / name
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old in text:
            text = text.replace(old, new)
        else:
            missing.append(f"{name}: {old[:64]}")
    path.write_text(text, encoding="utf-8")

if missing:
    print("NOT FOUND:")
    for m in missing:
        print("  " + m)
    sys.exit(1)
print("all settings.py wording replaced")
