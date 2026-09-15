"""Render every new settings widget and shoot it.

    python _test/ui_probe.py

Step 3 of TKINTER-BUILD.md's build order: one card per control family so the
grid geometry and each widget can be checked against settings-reference.html
before the panel is built on top of them.
"""
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk

import nabd_tokens as T
import nabd_ui as U

ctypes.windll.shcore.SetProcessDpiAwareness(2)

root = tk.Tk()
root.title("nabd ui probe")
T.set_scale(ctypes.windll.user32.GetDpiForWindow(root.winfo_id()))
root.configure(bg=T.PANEL)
root.geometry(f"{T.px(T.PANEL_W)}x{T.px(760)}+120+60")
root.attributes("-topmost", True)
root.lift()

body = tk.Frame(root, bg=T.PANEL)
body.pack(fill="both", expand=True, padx=T.px(T.PANEL_PAD),
          pady=T.px(T.PANEL_PAD))

# ── CAPTURE ────────────────────────────────────────────────────────────────
U.eyebrow(body, "capture").pack(fill="x", pady=(0, T.px(10)))
card = U.card(body)
card.pack(fill="x")

r = 0
row = U.Row(card, "Nab length", r, first=True)
seg = U.Segmented(row.line, ["1 min", "3 min", "5 min"], index=2)
seg.pack(side="right")
sub = row.sub()
U.Meter(sub, T.CONTROL_COL, 0.12, "ok").pack(fill="x")
l2 = tk.Frame(sub, bg=T.SURFACE)
l2.pack(fill="x", pady=(T.px(7), 0))
tk.Label(l2, text="1.2 GB per nab", bg=T.SURFACE, fg=T.TEXT_MUTED,
         font=T.font("mono_xs")).pack(side="left")
tk.Label(l2, text="12% of 9.2 GB free", bg=T.SURFACE, fg=T.TEXT_FAINT,
         font=T.font("mono_xs")).pack(side="right")

r += 1
U.separator(card, r)
r += 1
row = U.Row(card, "Buffer", r)
U.Toggle(row.line, False).pack(side="right")
tk.Label(row.line, text="Start fresh after each nab", bg=T.SURFACE, fg=T.TEXT,
         font=T.font("value")).pack(side="right", padx=(0, T.px(9)))
row.helper("Off always keeps the most recent footage, so nabs taken close "
           "together overlap.")

r += 1
U.separator(card, r)
r += 1
row = U.Row(card, "Save nabs to", r, last=True)
U.Button(row.line, "Browse", variant="ghost").pack(side="right")
U.Field(row.line, r"C:\Users\ethan\Videos\Nabd",
        width=232).pack(side="right", padx=(0, T.px(9)))

# ── VIDEO ──────────────────────────────────────────────────────────────────
U.eyebrow(body, "video").pack(fill="x", pady=(T.px(T.GROUP_GAP), T.px(10)))
card2 = U.card(body)
card2.pack(fill="x")

r = 0
row = U.Row(card2, "Monitor", r, first=True)
U.Button(row.line, "Identify", variant="ghost").pack(side="right")
U.Select(row.line, ["Monitor 1 \u2014 2560\u00d71440 \u00b7 240 Hz",
                    "Monitor 2 \u2014 2560\u00d71440 \u00b7 240 Hz"],
         width=232).pack(side="right", padx=(0, T.px(9)))

r += 1
U.separator(card2, r)
r += 1
row = U.Row(card2, "Frame rate", r, last=True)
U.Select(row.line, ["240 fps", "120 fps", "60 fps", "30 fps"], index=2,
         width=T.CONTROL_COL).pack(side="right")
row.helper("Monitor 1 runs at 240 Hz. 60 fps divides evenly, so motion paces "
           "cleanly.")

# ── AUDIO ──────────────────────────────────────────────────────────────────
U.eyebrow(body, "audio").pack(fill="x", pady=(T.px(T.GROUP_GAP), T.px(10)))
card3 = U.card(body)
card3.pack(fill="x")

r = 0
row = U.Row(card3, "Microphone", r, first=True)
U.Select(row.line, ["Microphone (HyperX Cloud III Wireless)"],
         width=T.CONTROL_COL).pack(side="right")
sub = row.sub()
tk.Label(sub, text="100%", bg=T.SURFACE, fg=T.TEXT_MUTED,
         font=T.font("mono_sm"), width=6, anchor="e").pack(side="right")
U.Slider(sub, 0, 100, 100, width=270).pack(side="right", fill="x", expand=True)

r += 1
U.separator(card3, r)
r += 1
row = U.Row(card3, "A/V sync", r, last=True)
U.Button(row.line, "Test", variant="ghost", small=True).pack(side="right")
tk.Label(row.line, text="\u2212150 ms", bg=T.SURFACE, fg=T.TEXT_MUTED,
         font=T.font("mono_sm"), width=8, anchor="e").pack(side="right",
                                                           padx=(T.px(9), T.px(9)))
U.Slider(row.line, -500, 500, -150, step=10,
         width=200).pack(side="right", fill="x", expand=True)

# ── HOTKEYS ────────────────────────────────────────────────────────────────
U.eyebrow(body, "hotkeys").pack(fill="x", pady=(T.px(T.GROUP_GAP), T.px(10)))
card4 = U.card(body)
card4.pack(fill="x")
r = 0
row = U.Row(card4, "Save nab", r, first=True)
U.HotkeyField(row.line, "Insert", width=110).pack(side="right")
r += 1
U.separator(card4, r)
r += 1
row = U.Row(card4, "Open Nab'd", r, last=True)
hk = U.HotkeyField(row.line, "Ctrl + Alt + N", width=150)
hk.pack(side="right")
row.helper("Click a field, then press the combination you want. Esc cancels.")

# footer bar
bar = tk.Frame(body, bg=T.PANEL)
bar.pack(fill="x", pady=(T.px(18), 0))
tk.Label(bar, text="3 unsaved changes", bg=T.PANEL, fg=T.PURPLE_LIGHT,
         font=T.font("mono_sm")).pack(side="left")
U.Button(bar, "Save", variant="primary", bg=T.PANEL, width=80).pack(side="right")
U.Button(bar, "Cancel", variant="quiet", bg=T.PANEL).pack(side="right",
                                                          padx=(0, T.px(9)))

root.update_idletasks()
root.deiconify()
root.lift()
root.focus_force()
for _ in range(80):
    root.update()
import time; time.sleep(0.6)
for _ in range(20):
    root.update()

from PIL import ImageGrab  # noqa: E402
x, y = root.winfo_rootx(), root.winfo_rooty()
w, h = root.winfo_width(), root.winfo_height()
ImageGrab.grab(all_screens=False).crop((x, y, x + w, y + h)).save(
    Path(__file__).resolve().parent / "ui_probe.png")
print(f"shot {w}x{h}")
root.destroy()
