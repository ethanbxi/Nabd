"""
Dark theme and small custom widgets for Nab'd.

Classic tk widgets are used instead of ttk throughout: ttk themes only expose
whatever the underlying engine chooses to honour, so dark colours land
inconsistently. Plain tk takes explicit colours everywhere, and the few controls
that would normally need ttk are drawn here instead.
"""

import ctypes
import tkinter as tk

import brand

BG = brand.SHELL          # the app itself
SURFACE = brand.INK       # raised surfaces: inputs, cards
SURFACE_2 = "#211F27"     # hover, derived a step above Ink
BORDER = "#2D2A35"
TEXT = brand.CREAM        # body text on near-black
MUTED = "#9A96A1"

# Nabd Purple is 2.7:1 on the shell, below the 3:1 floor for UI shapes. Any
# purple linework or text on dark uses Purple Light; full-strength purple only
# ever appears as a filled field with cream on top, which clears 7.2:1.
ACCENT = brand.PURPLE_LIGHT
FIELD = brand.PURPLE
FIELD_TEXT = brand.CREAM
FIELD_PRESSED = brand.PURPLE_DEEP

OK = brand.PURPLE_LIGHT   # success is on-brand, not green
ERR = "#E5484D"           # reserved for genuine failure

# The guidelines' scale, in pixels. Tk reads a negative size as pixels, so the
# px values transfer directly instead of being converted to points and rounded.
# brand.font() resolves Outfit / JetBrains Mono when installed and otherwise
# follows the documented fallback to system-ui / ui-monospace.
# The published scale, and nothing else. Sizes in px, weights as Outfit
# exposes them - each weight is its own family to Windows, so the weight is
# carried by the family name rather than by Tk's "bold" flag.
#
#   Display  44 / 1.05 / 600   landing headlines only - unused here
#   H1       30 / 1.15 / 500   page and dialog titles
#   H2       20 / 1.30 / 500   section headings
#   Body     15 / 1.55 / 400   everything people read
#   Small    13 / 1.50 / 400   captions, helper text
#   Mono     12 / 1.50 / 400   hotkeys, paths, durations, IDs
SCALE = {"F_DISPLAY": (44, 600), "F_H1": (30, 500), "F_H2": (20, 500),
         "F_BODY": (15, 400), "F_SMALL": (13, 400)}

# Provisional values so the module imports cleanly; init() replaces them with
# the resolved faces once a Tk root exists.
F_DISPLAY = ("Segoe UI", -44)
F_H1 = ("Segoe UI", -30)
F_H2 = ("Segoe UI", -20)
F_BODY = ("Segoe UI", -15)
F_SMALL = ("Segoe UI", -13)
F_MONO = ("Consolas", -12)

# Spacing scale, so rhythm is consistent instead of hand-tuned per section.
PAD = 26          # panel side padding
# H2 headings are 20px, so the section gap does less work than it used to;
# tightened so the whole form still fits a 1440px screen without clipping.
GAP_SECTION = 18
GAP_ROW = 11      # between rows inside a section
GAP_TIGHT = 5     # between a control and its helper line
LABEL_COL = 96    # label column width; every control starts at one edge
ACTION_COL = 96   # reserved to the right of every row, so a row-level button
                  # sits beside its control without narrowing it
FIELD_PAD = 7     # internal vertical padding of inputs
# Every control that reads as a box - select, text field, button - is forced to
# this height. Left to their own devices they size to their own font, so a mono
# field ends up shorter than the select beside it.
FIELD_H = 36


def init():
    """Resolve the type scale. Call once, right after creating the Tk root -
    tkinter.font.families() needs one to report what is installed."""
    g = globals()
    for name, (px, weight) in SCALE.items():
        g[name] = (brand.weight_font(weight), -px)
    g["F_MONO"] = (brand.font("JetBrains Mono"), -12)
    return brand.font("Outfit")


def dark_titlebar(win):
    """Windows 11 honours DWMWA_USE_IMMERSIVE_DARK_MODE; without it the title
    bar stays light and the window looks half-themed."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        for attr in (20, 19):  # 20 on current builds, 19 on older ones
            val = ctypes.c_int(1)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


def label(parent, text, fg=TEXT, font=None, **kw):
    # Resolved at call time: a default argument would bind the provisional
    # face at import, before init() has run.
    return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=fg,
                    font=font or F_BODY, anchor="w", **kw)


class Button(tk.Label):
    """Flat, hover-aware button. tk.Button on Windows keeps a native border
    that cannot be themed away."""

    def __init__(self, parent, text, command=None, accent=False, width=None,
                 bg=None, font=None, **kw):
        self.accent = accent
        # Primary actions are a purple *field* with cream on it; purple as
        # linework on this shell would fall under the contrast floor.
        self.base = bg or (FIELD if accent else SURFACE_2)
        self.hover = FIELD_PRESSED if accent else BORDER
        self.command = command
        self._enabled = True
        super().__init__(parent, text=text, bg=self.base,
                         fg=FIELD_TEXT if accent else TEXT,
                         font=font or F_BODY, padx=14, pady=7, cursor="hand2",
                         width=width, **kw)
        self.bind("<Enter>", lambda _e: self._enabled and self.config(bg=self.hover))
        self.bind("<Leave>", lambda _e: self.config(bg=self.base))
        self.bind("<Button-1>", self._click)

    def _click(self, _e):
        if self._enabled and self.command:
            self.command()

    def set_text(self, text):
        self.config(text=text)

    def set_enabled(self, on):
        self._enabled = on
        self.config(fg=TEXT if on else MUTED, cursor="hand2" if on else "arrow")


class CloseButton(tk.Label):
    """The only window control a docked panel needs."""

    def __init__(self, parent, command):
        super().__init__(parent, text="\u2715", bg=BG, fg=MUTED,
                         font=F_H2, padx=11, pady=1, cursor="hand2")
        self.bind("<Enter>", lambda _e: self.config(fg=FIELD_TEXT, bg=FIELD))
        self.bind("<Leave>", lambda _e: self.config(fg=MUTED, bg=BG))
        self.bind("<Button-1>", lambda _e: command())


class Dropdown(tk.Frame):
    """A select field: value on the left, chevron on the right, list below.

    Built by hand rather than from Menubutton + Menu because a Tk menu cannot
    be sized to match the field it belongs to, and its popup will not take the
    panel's colours.
    """

    ARROW_W = 26

    def __init__(self, parent, values=None, width=None, on_change=None):
        super().__init__(parent, bg=SURFACE, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=BORDER,
                         cursor="hand2", height=FIELD_H)
        self.pack_propagate(False)   # hold FIELD_H regardless of the font
        self.on_change = on_change
        self._values = []
        self._index = -1
        self._popup = None

        self.value = tk.Label(self, text="", bg=SURFACE, fg=TEXT, font=F_BODY,
                              anchor="w", padx=11, pady=FIELD_PAD,
                              cursor="hand2")
        self.value.pack(side="left", fill="x", expand=True)
        self.chevron = tk.Canvas(self, width=self.ARROW_W, height=18,
                                 bg=SURFACE, highlightthickness=0, bd=0,
                                 cursor="hand2")
        self.chevron.pack(side="right")
        self._draw_chevron(False)

        for widget in (self, self.value, self.chevron):
            widget.bind("<Button-1>", lambda _e: self.toggle())
            widget.bind("<Enter>", lambda _e: self._hover(True))
            widget.bind("<Leave>", lambda _e: self._hover(False))
        self.set_values(values or [])

    # -- appearance ---------------------------------------------------------

    def _hover(self, on):
        if self._popup:
            return
        shade = SURFACE_2 if on else SURFACE
        self.config(bg=shade)
        self.value.config(bg=shade)
        self.chevron.config(bg=shade)

    def _draw_chevron(self, open_):
        c = self.chevron
        c.delete("all")
        cx, cy, r = self.ARROW_W / 2, 9, 4
        # Points down when closed, up when open, so the field states its mode.
        if open_:
            c.create_line(cx - r, cy + r / 2, cx, cy - r / 2, fill=MUTED,
                          width=2, capstyle="round")
            c.create_line(cx, cy - r / 2, cx + r, cy + r / 2, fill=MUTED,
                          width=2, capstyle="round")
        else:
            c.create_line(cx - r, cy - r / 2, cx, cy + r / 2, fill=MUTED,
                          width=2, capstyle="round")
            c.create_line(cx, cy + r / 2, cx + r, cy - r / 2, fill=MUTED,
                          width=2, capstyle="round")

    # -- values -------------------------------------------------------------

    def set_values(self, values, index=0):
        self._values = list(values)
        if self._values:
            self.current(min(index, len(self._values) - 1))
        else:
            self._index = -1
            self.value.config(text="")

    def current(self, index=None):
        if index is None:
            return self._index
        if 0 <= index < len(self._values):
            self._index = index
            self.value.config(text=self._values[index])
        return self._index

    def get(self):
        return self._values[self._index] if 0 <= self._index < len(
            self._values) else ""

    # -- the list -----------------------------------------------------------

    def toggle(self):
        self.close() if self._popup else self.open()

    def open(self):
        if self._popup or not self._values:
            return
        self.update_idletasks()
        width = self.winfo_width()
        x, below = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()

        pop = tk.Toplevel(self)
        self._popup = pop
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        pop.configure(bg=BORDER)
        inner = tk.Frame(pop, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        for i, text in enumerate(self._values):
            chosen = i == self._index
            row = tk.Label(inner, text=text, bg=FIELD if chosen else SURFACE,
                           fg=FIELD_TEXT if chosen else TEXT, font=F_BODY,
                           anchor="w", padx=11, pady=6, cursor="hand2")
            row.pack(fill="x")
            row.bind("<Button-1>", lambda _e, i=i: self._choose(i))
            row.bind("<Enter>", lambda _e, w=row, c=chosen:
                     w.config(bg=FIELD if c else SURFACE_2))
            row.bind("<Leave>", lambda _e, w=row, c=chosen:
                     w.config(bg=FIELD if c else SURFACE))

        pop.update_idletasks()
        height = pop.winfo_reqheight()
        screen_h = self.winfo_screenheight()
        # Flip above the field when there is no room beneath it.
        y = below if below + height <= screen_h else self.winfo_rooty() - height
        pop.geometry(f"{width}x{height}+{x}+{max(0, y)}")

        self._draw_chevron(True)
        self._hover(True)
        # A grab routes every click in the app here, so a click anywhere else
        # lands on the popup itself and closes it.
        pop.grab_set()
        pop.bind("<Button-1>", self._maybe_close)
        pop.bind("<Escape>", lambda _e: self.close())
        pop.focus_set()

    def _maybe_close(self, event):
        if event.widget is self._popup:
            self.close()

    def close(self):
        pop, self._popup = self._popup, None
        if pop:
            try:
                pop.grab_release()
                pop.destroy()
            except tk.TclError:
                pass
        self._draw_chevron(False)
        self._hover(False)

    def _choose(self, index):
        self.close()
        self.current(index)
        if self.on_change:
            self.on_change(index)


class Segmented(tk.Frame):
    """Row of mutually exclusive pills - clearer than radio circles."""

    def __init__(self, parent, options, value, on_change=None):
        super().__init__(parent, bg=BG)
        self.options = options            # [(value, label), ...]
        self.value = value
        self.on_change = on_change
        self.cells = []
        for val, text in options:
            cell = tk.Label(self, text=text, bg=SURFACE, fg=MUTED, font=F_BODY,
                            padx=18, pady=7, cursor="hand2")
            cell.pack(side="left", padx=(0, 6))
            cell.bind("<Button-1>", lambda _e, v=val: self.set(v))
            cell.bind("<Enter>", lambda _e, c=cell: self._hover(c, True))
            cell.bind("<Leave>", lambda _e, c=cell: self._hover(c, False))
            self.cells.append((val, cell))
        self._paint()

    def _hover(self, cell, on):
        for val, c in self.cells:
            if c is cell and val != self.value:
                c.config(bg=SURFACE_2 if on else SURFACE)

    def _paint(self):
        for val, cell in self.cells:
            active = val == self.value
            cell.config(bg=FIELD if active else SURFACE,
                        fg=FIELD_TEXT if active else MUTED)

    def set(self, value):
        self.value = value
        self._paint()
        if self.on_change:
            self.on_change(value)

    def get(self):
        return self.value


class Check(tk.Frame):
    """Checkbox drawn by hand; tk.Checkbutton keeps a native look on Windows."""

    BOX = 17

    def __init__(self, parent, text, value=False, on_change=None):
        super().__init__(parent, bg=BG)
        self.value = bool(value)
        self.on_change = on_change
        self.box = tk.Canvas(self, width=self.BOX, height=self.BOX, bg=BG,
                             highlightthickness=0, bd=0, cursor="hand2")
        self.box.pack(side="left")
        self.label = tk.Label(self, text=text, bg=BG, fg=TEXT, font=F_BODY,
                              cursor="hand2")
        self.label.pack(side="left", padx=(8, 0))
        for w in (self.box, self.label):
            w.bind("<Button-1>", lambda _e: self.toggle())
        self._paint()

    def _paint(self):
        c, s = self.box, self.BOX
        c.delete("all")
        fill = FIELD if self.value else SURFACE
        edge = FIELD if self.value else BORDER
        c.create_rectangle(1, 1, s - 1, s - 1, fill=fill, outline=edge, width=1)
        if self.value:
            c.create_line(4, s / 2, s / 2 - 1, s - 5, fill=FIELD_TEXT, width=2)
            c.create_line(s / 2 - 1, s - 5, s - 4, 4, fill=FIELD_TEXT, width=2)

    def toggle(self):
        self.set(not self.value)

    def set(self, value):
        self.value = bool(value)
        self._paint()
        if self.on_change:
            self.on_change(self.value)

    def get(self):
        return self.value


class Slider(tk.Canvas):
    """Volume control drawn by hand so the track and knob stay on-theme."""

    H = 26
    KNOB = 7

    def __init__(self, parent, value=1.0, maximum=2.0, width=210,
                 minimum=0.0, centred=False, on_change=None):
        # Height matches a field so a row of sliders and a row of selects share
        # the same rhythm; width follows the cell it is placed in.
        super().__init__(parent, width=width, height=FIELD_H, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.min = minimum
        self.max = maximum
        self.centred = centred  # fill outward from the middle, not the left
        self.value = value
        self.on_change = on_change
        self.width = width
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Configure>", self._resized)
        self._paint()

    def _resized(self, event):
        """Track the cell: the slider is sized by its column, not by a
        hard-coded width, so it matches the selects above it."""
        self.width = event.width
        self._paint()

    def _x_for(self, value):
        pad = self.KNOB + 2
        span = self.width - pad * 2
        frac = (value - self.min) / (self.max - self.min)
        return pad + span * frac

    def _drag(self, event):
        pad = self.KNOB + 2
        span = max(1, self.width - pad * 2)
        frac = min(1.0, max(0.0, (event.x - pad) / span))
        self.value = round(self.min + frac * (self.max - self.min), 2)
        self._paint()
        if self.on_change:
            self.on_change(self.value)

    def _paint(self):
        self.delete("all")
        mid = FIELD_H / 2
        pad = self.KNOB + 2
        self.create_line(pad, mid, self.width - pad, mid,
                         fill=SURFACE_2, width=4, capstyle="round")
        x = self._x_for(self.value)
        origin = self._x_for(0.0) if self.centred else pad
        if abs(x - origin) > 1:
            self.create_line(origin, mid, x, mid, fill=ACCENT, width=4,
                             capstyle="round")
        r = self.KNOB
        self.create_oval(x - r, mid - r, x + r, mid + r,
                         fill=TEXT, outline=BORDER)

    def get(self):
        return self.value

    def set(self, value):
        self.value = max(self.min, min(self.max, value))
        self._paint()


class Entry(tk.Frame):
    """Text field in a fixed-height shell.

    A bare tk.Entry sizes to its own font, so a mono path field comes out
    shorter than the selects beside it; the shell pins every box to FIELD_H.
    """

    def __init__(self, parent, textvariable=None, font=None, **kw):
        super().__init__(parent, bg=SURFACE, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT,
                         height=FIELD_H)
        self.pack_propagate(False)
        self.entry = tk.Entry(self, textvariable=textvariable, bg=SURFACE,
                              fg=TEXT, insertbackground=TEXT, relief="flat",
                              bd=0, font=font or F_BODY, highlightthickness=0,
                              disabledbackground=SURFACE,
                              disabledforeground=MUTED, **kw)
        self.entry.config(insertwidth=1)
        self.entry.pack(fill="both", expand=True, padx=10)

    def get(self):
        return self.entry.get()
