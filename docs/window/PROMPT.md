# Prompt for Claude Code

Paste this into Claude Code with the repo open. It assumes `docs/window/` exists
(the handoff is already there) and that `nabd_window.py` is in the repo root.

---

Read `docs/window/WINDOW.md` in full before writing anything, and look at the
seven renders in `docs/window/reference/`. Then read these parts of the existing
code, because the spec is written as a diff against them and most of what it
needs already exists:

- `nabd.py`: `main()`, `wants_panel()`, `claim_single_instance()`, the
  `SETTINGS_TRIGGER` / `SETTINGS_SHOW` constants
- `settings.py`: the `Panel` class — specifically `_make_group`, `_row`,
  `_build_hero`, `_build_recent`, `_build_capture`, `_build_video`,
  `_build_audio`, `_build_footer`
- `nabd_tokens.py` and `nabd_window.py` for every colour and measurement

Build a new `window.py` that adds a resizable main window, following WINDOW.md
exactly. The rules that matter most:

1. **Reuse, do not copy.** The group builders already take a `parent`. The window
   calls the same `Panel._build_*` methods into its own content pane. If a
   builder currently hardcodes something drawer-specific, lift that into a
   parameter rather than forking the method. There must not end up being two
   implementations of the Capture group.

2. **Take every number from `nabd_window.py`** — 860×640, 820×560 minimum, 196 px
   rail, 680 px group cap, 60 px footer. `CONTROL_COL` stays 344, unchanged from
   `nabd_tokens.py`. Do not re-derive or round these.

3. **Native title bar**, dark via `nabd_window.apply_dark_titlebar`. Not
   `overrideredirect` — that is the banner's job, not this window's.

4. **Geometry persistence** through `nabd_window.save_geometry` /
   `restore_geometry`, stored in a new `window_geometry` config key with an
   empty-string default. `clamp_to_visible` is required, not optional; pass the
   display **work areas** from the enumeration the frame-rate helper already
   does.

5. **First run** reuses the existing `first_run = not CONFIG_PATH.exists()`
   signal. Do not add a `setup_complete` key. Render the setup card in place of
   the hero on Home; hide the monitor row when there is only one display.

6. **The launch diff in `nabd.py`** is §2 of the spec: a `--window` role, a
   manual launch opening the window instead of the drawer, a `WINDOW_SHOW` token
   beside `SETTINGS_SHOW` for the already-running case. `--autostart` behaviour
   does not change.

Work in this order, and stop after each step so I can run it:

1. `window.py` with the shell only — native chrome, rail, empty content pane,
   footer, geometry persistence. Nothing wired up.
2. The five settings sections, calling the existing `Panel._build_*` builders.
3. Home — hero, recent nabs, the tray notice.
4. The App group, which is the only genuinely new group.
5. First run.
6. The `nabd.py` launch diff.

Do not change capture behaviour, the config schema beyond the one additive key,
or anything in `banner.py`. If a spec instruction conflicts with what the code
actually does, tell me instead of guessing — the spec was written by reading the
code, but it was read at one point in time.
