# nab'd — main window

Handoff spec for Claude Code. Adds a resizable main window for manual launches
and first run. Build exactly what is here.

Reference renders: `reference/1-home.png` … `7-app.png`, drawn at the default
860×640. Every control in them already exists in `settings.py`.

**This spec is written against the code as it is**, not against assumptions —
`nabd.py` `main()`, `wants_panel()`, `claim_single_instance()`, and the
`Panel` class in `settings.py`. Most of the launch logic you need is already
there and is better than a generic design would have guessed. What follows is a
diff, not a rewrite.

---

## 1. What already exists (do not rebuild these)

| Already in the code | Where |
|---|---|
| One binary, several roles, re-invoked with a flag | `nabd.py main()` — `--settings`, `--banner` |
| Autostart stays out of the way | `--autostart` at sign-in; `wants_panel(argv, config_exists)` |
| First run is already detected | `first_run = not CONFIG_PATH.exists()` |
| First run shows the app even under `--autostart` | `wants_panel` returns `not config_exists` |
| Single instance, and a second launch surfaces the first | `claim_single_instance()` on mutex `Nabd.Instance`, then `SETTINGS_TRIGGER.write_text(SETTINGS_SHOW)` + `AllowSetForegroundWindow(-1)` |
| Every group builder already takes a parent | `Panel._build_hero/_build_recent/_build_capture/_build_video/_build_audio(parent)` |
| Row/group grammar | `Panel._make_group(parent, title, trailing)`, `Panel._row(card, label, index, **kw)` |

**The window is a new shell around those same builders.** It is not a second
settings UI, and none of the group code should be copied. If a group needs to
render into two different containers, that is a parent argument, which it
already takes.

---

## 2. What changes

### 2.1 A fourth role

```python
# nabd.py main()
if "--settings" in sys.argv:            # unchanged: the docked drawer, hotkey-invoked
    import settings; return settings.main() or 0
if "--banner" in sys.argv:              # unchanged
    import banner;   return banner.main() or 0
if "--window" in sys.argv:              # NEW: the main window
    import window;   return window.main() or 0
```

### 2.2 A manual launch opens the window, not the drawer

Today `wants_panel()` decides whether a launch shows the **docked panel**. That
was the only UI there was. Now the two are different things:

- **Hotkey** (`open_hotkey`, currently `ctrl+alt+n`) → the docked drawer, as now.
- **Manual launch** — installer "start now", Start Menu, desktop icon, double
  click on the exe → **the window**.
- **`--autostart`** → neither; straight to the tray. Already true.
- **First run** → the window, in its setup state, even under `--autostart`.
  `wants_panel`'s existing `return not config_exists` already does this; only the
  thing being shown changes.

The cleanest edit is to rename the predicate to say what it now decides
(`wants_window`) and leave its body alone. The docstring is already correct about
*why*; only the noun changes.

### 2.3 The already-running case shows the window

`main()` currently writes `SETTINGS_SHOW` to `SETTINGS_TRIGGER` when the mutex is
already held, and the running instance raises the drawer. A manual launch should
now raise the **window**. Add a second token beside the existing one:

```python
SETTINGS_SHOW = "show"          # existing: raise the docked drawer
WINDOW_SHOW   = "window"        # NEW:      raise (or spawn) the main window
```

`settings.py` already polls `SETTINGS_TRIGGER`'s mtime and compares the token
(`settings.py` ~2839–2848), so this is one more branch in code that exists.
Keep `AllowSetForegroundWindow(-1)` — the new launch holds the foreground right
and the running instance does not.

### 2.4 One new config key

```json
"window_geometry": ""
```

Additive with a safe default, so **no `config_version` bump** — the existing
loader path for unknown-but-defaulted keys covers it. Written on close, read on
open. See §5.

---

## 3. Layout

`nabd_window.py` carries these as constants. Do not re-derive them.

```
860 × 640   default        820 × 560   minimum
196         nav rail
664         content  = 860 − 196
624         card     = 664 − 2×20 padding      (the drawer's card is 608)
344         control column — UNCHANGED from nabd_tokens.CONTROL_COL
680         group max-width, so maximising does not stretch cards
60          footer
```

The content column is the drawer's width **on purpose**. The cards, rows, the
344 px control column and the footer are the same widgets at the same numbers;
labels simply get ~76 px more room. That is the whole reason this is cheap.

### Rail

Brand lockup · search (`Ctrl F`) · six items · status + version pinned to the
bottom. Active item: `--surface-raised` background, plus a 2 px `--purple-light`
bar on its left edge. Sections, in order:

**Home · Capture · Video · Audio · Hotkeys · App**

The status line in the rail (`● Buffering` / `● Not started`, amber dot when not
started) is visible from every section. A tray app is invisible by design; the
one place it is visible should never make anyone hunt for whether it is working.

### Panes

Each section is one pane, and **at the default size nothing scrolls**. Keep it
that way — if a group grows past the pane, that is a signal the group is doing
too much, not a reason to add a scrollbar. The footer (unsaved count left,
Close + Save right) spans the content column only, not the rail.

### Section contents

| Section | Content |
|---|---|
| **Home** | `_build_hero` status card, `_build_recent`, then the tray notice + `Quit nab'd`, pinned to the bottom of the pane |
| **Capture** | `_build_capture` — folder, nab length + disk meter, fresh buffer, capture sound |
| **Video** | `_build_video` — monitor + Identify, quality, frame rate + the even-division note |
| **Audio** | `_build_audio` — speakers, mic, A/V sync + Test |
| **Hotkeys** | Save nab, Open nab'd |
| **App** | Start with Windows, version, licences — **the only new group** |

Home is not a settings group. It answers what someone actually opened the window
to ask — is it running, what has it got, where did my nabs go — and it is where
the tray behaviour gets explained, because "I closed it and it kept recording"
is the single most surprising thing about this app.

---

## 4. First run

No wizard. `first_run` is already computed in `main()`; pass it through to the
window, which renders the setup card **instead of** the hero on Home.

Three questions, because three are the ones that cannot be defaulted:

1. **Where nabs go** — path field + Browse, prefilled with the existing default
2. **Key to save a nab** — the hotkey field, prefilled `Insert`
3. **Screen to capture** — monitor select + Identify. **Skip this row entirely
   when there is only one display.**

Then one primary button, **Start buffering**, and a quiet line: *everything else
is already set sensibly, change any of it from the left.*

- Quality, frame rate, devices and length all have defensible defaults. Asking
  about them up front turns a 20-second setup into a form.
- The one-sentence explanation is about the concept, not the controls: *nab'd
  keeps the last few minutes in memory; when something good happens you press a
  key and it writes the part that already went past.* Nobody has used a ring
  buffer before; everybody understands that sentence.
- The tray note is pinned to the bottom of the pane on first run, because the
  first time someone closes this window they will assume they closed the app.
- **Start buffering** writes `config.json` — which is what makes `first_run`
  false forever after, with no new flag and no migration. That is the existing
  design and it is the right one.
- The rail stays enabled during setup. Let people look around.

---

## 5. Window chrome and geometry

`nabd_window.py` has all of this; it is a no-op off Windows so it imports and
tests anywhere.

**Native title bar**, tinted with the immersive dark-mode attribute you already
set via ctypes (`apply_dark_titlebar`). One call buys the dark bar while snap
layouts, Aero Peek, the system menu, eight-edge resize and mixed-DPI behaviour
all keep working. The banner stays `overrideredirect` — it is non-interactive and
should not read as a window at all. The two being chromed differently is a
decision, not an inconsistency.

**Geometry persistence.** `save_geometry(root)` on close, `restore_geometry(root,
saved, monitors)` on open, into the `window_geometry` config key.

- Never save a maximised or iconified size — `save_geometry` returns `None` for
  those, and `None` means "use the default", centred on the primary display.
- `clamp_to_visible()` pulls a saved rect back onto a monitor that still exists.
  **This is not optional.** A window remembered on a monitor that has since been
  unplugged opens at coordinates nobody can reach, and it reads to the user as
  "the app stopped opening". It is the most common bug in windowed apps that
  remember their position. You already enumerate displays for the frame-rate
  helper — pass those **work areas**, not full bounds, so a taskbar is not
  covered.

---

## 6. What will break it

1. **Copying the group builders instead of passing a parent.** Two settings UIs
   that drift apart is the failure mode this whole approach exists to avoid.
2. Changing `CONTROL_COL` for the window. The 344 px column is what makes the
   cards identical; widen it and you have forked the row grammar.
3. Skipping `clamp_to_visible`. See §5.
4. Letting a pane scroll at the default size. Fix the group, not the container.
5. Making `--autostart` show anything on a non-first run. The existing
   `wants_panel` logic is correct; only the noun changes.
6. Adding a `setup_complete` key. `config.json`'s existence already is that flag,
   and a new key would default to false for every existing user and show them a
   first-run screen after an update.

---

## 7. Open, and not a design question

**FFmpeg licensing.** The Gyan full build you bundle includes GPL components
(libx264 among them), and shipping it inside the installer is redistribution —
which means carrying the licence text and a corresponding-source offer. You
already have `THIRD-PARTY-NOTICES.md`; the *App* section's licence row is where
it should surface in the UI. Whether the GPL reaches nab'd's own code is the part
worth a qualified answer rather than a guess: you invoke `ffmpeg.exe` as a
separate process over a pipe and never link its libraries, which is the usual
basis for saying no, but that is not advice I am able to give properly.
