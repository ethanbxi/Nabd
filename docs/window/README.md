# nab'd main window — handoff

Stack: Python 3.10 / classic tkinter. Same system as the settings panel, banner
and sound handoffs. **No new dependency.**

Read order:

1. **`WINDOW.md`** — the spec. Written as a diff against `nabd.py` and
   `settings.py` as they actually are, not against assumptions.
2. **`reference/`** — the seven screens at the default 860×640.
3. **`nabd_window.py`** — metrics, native dark chrome, geometry persistence with
   monitor clamping. Drops in the repo root. Run it directly for a self-test.
4. **`PROMPT.md`** — what to paste into Claude Code.

## The short version

The window is a **new shell around the widgets that already exist**. Its content
column is the drawer's width on purpose:

```
860 = 196 rail + 664 content       624 card vs the drawer's 608
CONTROL_COL stays 344 — unchanged
```

So `Panel._build_capture(parent)` and friends render into it unmodified. There
must never be two implementations of a settings group.

Most of the launch logic already exists and is better than a generic design would
have guessed — `--autostart`, `wants_panel()`, `first_run = not
CONFIG_PATH.exists()`, the mutex plus `.settings_trigger` handshake. §2 of the
spec is a short diff, not a rewrite.

Three things carry it:

- **Reuse, don't copy.** The group builders already take a parent.
- **`clamp_to_visible` is required.** A window remembered on an unplugged monitor
  opens where nobody can reach it, and reads as "the app stopped opening".
- **No `setup_complete` key.** `config.json`'s existence already is that flag;
  a new one would default false for existing users and show them first run after
  an update.

## Decided in review

- Autostart goes straight to the tray. Already true in the code.
- Native title bar with immersive dark mode. The banner stays `overrideredirect`.

## Still open

FFmpeg licensing — not a design question, but the *App* section has the licence
row ready for it. See WINDOW.md §7.
