# Prompt for Claude Code — the tray menu

Drop this folder in at `docs/tray/`, then paste everything below.

---

Read `docs/tray/TRAY.md` in full and look at `docs/tray/reference/*.png` — those
are actual-size targets at 1× and 2×. Then read what it replaces: wherever
`nabd.py` builds and shows the tray icon's context menu, plus `nabd_tokens.py`,
`brand.py` and `nabd_ui.py` for the palette, the mark and the existing widget
conventions.

This replaces the Win32 context menu with a drawn one. The rules that matter:

1. **The split is the design.** `nabd_tray_model.py` is pure stdlib and holds
   every decision — rows, labels, enabled state, keyboard order, metrics,
   placement. `nabd_tray_menu.py` draws them. If you write an `if` about what a
   row should say in the Tk file, move it to the model and add a test.
2. **Do not re-type the palette.** Pass `nabd_tokens` in as `tokens=`; the
   literals in the model are a standalone fallback.
3. **Take the artwork as given.** The status block's mark comes from
   `brand.mark_image()`. If the overhaul has not landed it falls back to the old
   ring — do not paper over that, tell me.
4. **Every Win32 call is optional and wrapped.** A missing DWM attribute on
   Windows 10 must degrade to a square menu, never to no menu.
5. **The menu window is built once at startup**, withdrawn, and only shown and
   moved afterwards.

Work in this order and stop after each step so I can run it:

1. Copy in `nabd_tray_model.py` and `nabd_tray_menu.py`. Run
   `python docs/tray/verify_tray.py` and paste me the output — 51 checks, all
   passing.
2. Find where the current tray menu is built and show me that code before
   changing it, with how you plan to wire `toggle()` and `state_fn` into it.
   **Do not change it yet.** If the surrounding code makes this awkward, say so
   rather than forcing it.
3. Wire it up, keeping the old menu reachable behind a flag or an easy revert.
   Run it and send me a screenshot of the menu open at 100% DPI.
4. Check the things I cannot check from here: does it open instantly, does it
   close when you click elsewhere, does it land above the taskbar, does the
   meter move while it is open, and does Escape close it.
5. Then the awkward ones: a second monitor at a different scale, and the
   taskbar moved to the top or left.

Do not change capture behaviour, the config schema, the hotkey handling or the
settings panel. If a spec instruction conflicts with what the code actually
does, tell me rather than guessing — the spec was written without access to the
repo, so §8's wiring is the part most likely to need your judgement.
