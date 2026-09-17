# nab'd tray menu — spec

Replaces the Win32 context menu on the tray icon with a drawn one. This is
variant **B** from the concept: the status line becomes a block that carries a
live buffer meter, and the items are re-cut.

**248 × 279 logical pixels** at 100% DPI. Everything scales from there.

---

## 1. The shape of the code

Two files, and the split is the point.

**`nabd_tray_model.py`** — pure stdlib, no toolkit. Which rows exist, what they
say, which are disabled, where the keyboard goes next, how big the window is,
and where on screen it opens. Runs anywhere, so `verify_tray.py` covers it on
any machine, including one with no display and no Windows.

**`nabd_tray_menu.py`** — Tk widgets and Win32 calls. No decisions.

If you find yourself writing an `if` about what a row should *say* in the Tk
file, it belongs in the model. A tray menu is awkward to test by hand and easy
to regress quietly; this is what makes it testable at all.

| File | What it is | Ships? |
|---|---|---|
| `nabd_tray_model.py` | every decision, pure stdlib | **yes** |
| `nabd_tray_menu.py` | the Tk view + Windows | **yes** |
| `verify_tray.py` | 51 checks over the model | no — dev tool |
| `render_reference.py` | rebuilds the PNGs below | no — dev tool |
| `reference/menu-*@1x.png`, `@2x.png` | what it has to look like | no |

---

## 2. Drawn on one Canvas, not a tree of Frames

Three reasons, all of which bit the first attempt:

- **Frames are rectangles.** A rounded hover pill is not possible as a Frame
  background, and a square one next to Windows 11's rounded menus looks wrong.
- **`<Enter>`/`<Leave>` on a Frame fires again for every child Label**, so
  hover flickers as the pointer crosses the accelerator text. One widget has
  one pointer.
- **Hit testing becomes `model.row_at(y)`** — the same function the tests
  cover, rather than a second implementation living in event bindings.

Tk canvas has no rounded-rectangle primitive; `_rr()` smooths a polygon through
the corner points, which is the trick `brand.draw_tile` already uses. It is not
antialiased. If a 5 px radius looks rough on your display, set `ROW_RADIUS = 0`
in the model — the metrics are shared, so the references regenerate to match.

---

## 3. What changed from the current menu, and why

Six interactive rows instead of seven.

| Today | Now | Why |
|---|---|---|
| `Recording - 1 min buffered` | **Status block** — mark, state, meter | It was never a menu item; it is state. As a block it can show how full the ring buffer actually is, which is the one number you want before pressing the hotkey. |
| `✓ Recording` | **Pause recording** | A tick beside a noun does not say what clicking does. The verb does, and it flips to **Resume recording**. Removing it also ends the duplication with the line above. |
| `Nab last 1 min (alt+insert)` | **Nab last minute** · `Alt+Ins` | The reason the app exists, given weight and a right-aligned accelerator in the mono face. |
| `Open nabs folder` | unchanged | |
| `Settings...` | `Settings…` | Stays the default item — it is what a double-click on the icon opens, since the settings panel *is* nab'd's window. Real ellipsis. |
| `View log` | unchanged | |
| `Quit` | `Quit nab'd` | A tray menu sits among other apps' tray menus; "Quit" alone is ambiguous at a glance. |

### The one that is a bug, not a restyle

**The label follows what is actually buffered.** Twenty-two seconds in, the
current menu offers "Nab last 1 min" — a minute that does not exist yet. The
model says `Nab last 22 seconds`, and the meter reads 37%.

With **nothing** buffered it falls back to the configured length and disables
the row: `Nab last minute`, greyed. A disabled row names the *action*.
"Nab last 0 seconds" is not a thing anyone should read, and it is asserted
against.

The row is disabled rather than hidden. A row that disappears moves everything
under it, and people click tray menus from muscle memory.

---

## 4. Metrics

All logical px at 100% DPI, all from `nabd_tray_model`:

```
WIDTH 248      PAD 5          ROW_H 30      SEP_H 11      STATUS_H 56
RADIUS 8       ROW_RADIUS 5   ROW_PAD_X 11  GAP 10        METER_H 4
MARK 19        TICK_W 13
```

Height is `PAD*2 + STATUS_H + 3*SEP_H + 6*ROW_H` = **279**. The 1 px border is
drawn *inside* that, so 279 is the outer window height — the references are
pinned to the same number, and a metric change shows up as a differently sized
PNG rather than as a drawing that quietly drifts.

Type: rows 13 px, status 13 px medium, buffer 11 px mono, accelerators 10.5 px
mono. In Tk a **negative** font size means pixels; pass `-13`, not `13`.

Colour comes from `nabd_tokens.py` when you pass it in — `TrayMenu(...,
tokens=T)` maps the app's names onto the model's. The literals in the model are
a fallback so it can run standalone.

---

## 5. The Windows work

This is most of the risk. Every call is wrapped and optional: a menu that fails
to open because a DWM call is missing on Windows 10 is worse than a square menu.

**It has to be instant.** The window is built **once at startup**, withdrawn,
and only ever moved and shown. Creating a Toplevel on right-click is visibly
slower than the native menu, and "the menu is laggy" is the one review a custom
menu cannot survive.

**Clamp to the work area of the monitor under the cursor.** `MonitorFromPoint`
+ `GetMonitorInfoW` → `rcWork`. Not screen height, which opens the menu under
the taskbar; and not `SPI_GETWORKAREA`, which only knows about the primary
monitor — the tray can be on a second one. `place()` grows **up and left**,
flips when there is no room, and clamps to the work area; it is tested against
a taskbar on top, a tray on the left, a negative-origin second monitor, and a
work area smaller than the menu.

**Take the foreground or it will not close.** `SetForegroundWindow` before
showing, then `focus_force()`, and `<FocusOut>` hides. This is the Tk
equivalent of the call every Win32 tray menu makes before `TrackPopupMenu`.
`AllowSetForegroundWindow(ASFW_ANY)` is called once at construction —
`nabd.py` already makes that call for the settings panel.

**Per-monitor DPI.** `GetDpiForWindow` on each popup, fonts rebuilt when it
changes. The tray can be on a different monitor at a different scale than the
settings window.

**Rounded corners.** `DwmSetWindowAttribute(hwnd, 33, DWMWCP_ROUND)` —
attribute 33, value 2. Windows 11 only; fails harmlessly on 10, where menus are
square anyway. Same API as the dark title bar.

**No drop shadow.** A borderless Tk window gets none, and DWM will not add one
to an `overrideredirect` window. The 1 px border is what stands in. If you want
a real shadow it means `CS_DROPSHADOW` on the window class via
`SetClassLongPtrW`, which is a bigger change than it looks in Tk — leave it
until someone complains.

**Tk has no widget alpha**, only whole-window `-alpha`. So there are no fades:
hover and focus are solid colour swaps. That is why the palette uses flat fills
and a focus **ring** rather than a glow.

---

## 6. Keyboard

Up/Down (wrapping), Home/End, Enter/Space, Escape, and first-letter type-ahead
— which native menus do and people use without noticing. Separators, the status
block and disabled rows are never focusable.

**Focus is a ring, hover is a fill.** They are different states and must not
look alike; both references are in `reference/`.

**Mnemonics (underlined letters) are not implemented.** Native menus give them
free; drawing them means measuring and underlining a character per row. If you
want them, the model is where the letter assignment goes, not the view.

---

## 7. What this costs

A custom window is **invisible to screen readers** and **ignores high-contrast
themes**. The native menu is not prettier, but it is reachable. That is a real
regression and it is the honest argument for leaving the native menu alone or
shipping variant A instead. Ship this knowing it.

---

## 8. Wiring it up

```python
# once, at startup
from nabd_tray_model import State
from nabd_tray_menu import TrayMenu
import brand, nabd_tokens as T

menu = TrayMenu(root, on_action=self._tray_action, brand=brand, tokens=T)

def tray_state():
    return State(recording=self.recording,
                 buffered_s=int(self.buffer.seconds),
                 capacity_s=int(self.config["buffer_seconds"]),
                 hotkey=self.config["hotkey_label"])

# on right-click of the tray icon
menu.toggle(tray_state(), state_fn=tray_state)
```

`toggle` so a second right-click closes it rather than stacking another.
`state_fn` is polled every 250 ms while the menu is open, so the meter and the
"Nab last N seconds" label stay live — which is the whole reason the status
block exists.

`on_action` receives a stable key: `nab`, `toggle`, `folder`, `settings`,
`log`, `quit`. Dispatch on those, never on the label text.

**I could not read the repo while writing this** — the bridge to the machine
was down — so the exact place the current menu is constructed is yours to find.
Look for wherever the existing menu items are built and shown on right-click,
and replace that with the two calls above. Tell me if the surrounding code
makes this awkward rather than forcing it.

### The mark

`_mark()` asks `brand.mark_image(px, colour)` — the function from the overhaul's
§4a. If the overhaul has not landed it falls back to `brand.ring_image`, and you
will see the **old ring silhouette** in the status block. That is the signal to
land the overhaul, not something to work around here.

---

## 9. Proving it

```
python verify_tray.py        # 51 checks over the model
python render_reference.py   # redraws the PNGs, fails if they drift from the metrics
```

`render_reference.py` asserts every PNG's pixel size equals the model's
metrics × scale, so the spec, the references and the code cannot disagree
silently.

---

## 10. What will break it

1. Building the Toplevel on right-click instead of at startup.
2. Using screen height, or `SPI_GETWORKAREA`, instead of the cursor's monitor's
   `rcWork`.
3. Skipping `SetForegroundWindow` — the menu then will not close on an outside
   click.
4. Putting label or enablement logic in the Tk file.
5. Dispatching on label text instead of `row.key`.
6. Letting the primary row say "Nab last 0 seconds", or hiding it when disabled.
7. Forgetting that Tk garbage-collects `PhotoImage`; `self._images` exists for
   that reason.
8. Positive font sizes — in Tk that means points, and the menu grows on
   high-DPI displays.
