# nab'd tray menu — handoff

Replaces the Win32 context menu on the tray icon. Variant **B**: a status block
with a live buffer meter, and six interactive rows instead of seven.

```
nabd_tray_model.py     every decision, pure stdlib, tested   -> repo root
nabd_tray_menu.py      the Tk view + Windows                 -> repo root

verify_tray.py         51 checks over the model              stays in docs/tray/
render_reference.py    rebuilds the PNGs                     stays in docs/tray/

reference/menu-full@1x.png       buffer full
reference/menu-filling@1x.png    22 s in -- the case the current menu gets wrong
reference/menu-paused@1x.png     nothing buffered, primary disabled
reference/menu-hover@1x.png      hover on the primary row
reference/menu-focus@1x.png      keyboard focus -- a ring, not a fill
                                 (each also at @2x for 200% displays)

TRAY.md                the spec
PROMPT.md              what to paste into Claude Code
```

Start with `TRAY.md`. Read §7 before committing to this — a custom menu is
invisible to screen readers, and that is a real cost.

```
python verify_tray.py
python render_reference.py
```

248 × 279 logical px at 100% DPI.
