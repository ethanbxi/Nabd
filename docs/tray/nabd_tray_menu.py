# -*- coding: utf-8 -*-
"""nab'd tray menu -- the Tk view.

All the decisions live in nabd_tray_model.py, which is pure stdlib and tested.
This file draws them and deals with Windows. Keep it that way: if you find
yourself writing an `if` about what a row should say, it belongs in the model.

    menu = TrayMenu(root, on_action=handle)      # once, at startup
    ...
    menu.popup(State(recording=True, buffered_s=60, capacity_s=60))

Drawn on ONE Canvas rather than a tree of Frames. Three reasons, all of which
bit the first attempt:

  * Frames are rectangles. A rounded hover pill is not possible with a Frame
    background, and a square one next to Windows 11's rounded menus looks wrong.
  * <Enter>/<Leave> on a Frame fires again for every child Label, so hover
    flickers as the pointer crosses the accelerator text. One widget has one
    pointer.
  * Hit testing becomes model.row_at(y) -- the same function the tests cover.
"""
from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont

from nabd_tray_model import (Menu, State, place, C, PAD, ROW_PAD_X, ROW_RADIUS,
                             GAP, MARK, METER_H, TICK_W, ITEM, SEP, STATUS)

_IS_WIN = sys.platform.startswith("win")


# ── Windows ──────────────────────────────────────────────────────────────
class _Win32:
    """Everything that needs ctypes, in one place and every call optional.

    Nothing in here may raise: a menu that fails to open because a DWM call
    is missing on Windows 10 is worse than a square menu.
    """

    def __init__(self):
        self.ok = _IS_WIN
        if not self.ok:
            return
        import ctypes
        from ctypes import wintypes
        self.c = ctypes
        self.wt = wintypes
        self.user32 = ctypes.windll.user32
        self.dwm = ctypes.windll.dwmapi
        try:
            # so the menu opens once, not once per right-click, on the first show
            self.user32.AllowSetForegroundWindow(-1)      # ASFW_ANY
        except Exception:
            pass

    def hwnd(self, widget):
        """The TOP-LEVEL window handle, not Tk's inner one.

        winfo_id() hands back a 'TkChild' window sitting inside the real
        'TkTopLevel' frame, and that distinction is invisible until something
        refuses: measured here, DwmSetWindowAttribute on the child returns
        0x80070002 (ERROR_FILE_NOT_FOUND) and does nothing at all, while the
        same call on its parent returns S_OK and rounds the corners. The menu
        was square for that reason alone - the call was being made, correctly,
        against a window DWM does not manage.

        SetForegroundWindow has the same requirement, so every caller here
        wants the parent. banner.py already goes through GetParent for this.
        """
        if not self.ok:
            return None
        try:
            h = int(widget.winfo_id())
            return self.user32.GetParent(h) or h
        except Exception:
            return None

    def work_area(self, x, y, fallback):
        """The WORK area of the monitor under (x, y) -- not the screen.

        Screen height opens the menu underneath the taskbar. SPI_GETWORKAREA
        would fix that only on the primary monitor; the tray can be on a
        second one, so go through MonitorFromPoint.
        """
        if not self.ok:
            return fallback
        try:
            class RECT(self.c.Structure):
                _fields_ = [("left", self.wt.LONG), ("top", self.wt.LONG),
                            ("right", self.wt.LONG), ("bottom", self.wt.LONG)]

            class MONITORINFO(self.c.Structure):
                _fields_ = [("cbSize", self.wt.DWORD), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", self.wt.DWORD)]

            class POINT(self.c.Structure):
                _fields_ = [("x", self.wt.LONG), ("y", self.wt.LONG)]

            mon = self.user32.MonitorFromPoint(POINT(int(x), int(y)), 2)  # NEAREST
            mi = MONITORINFO()
            mi.cbSize = self.c.sizeof(MONITORINFO)
            if not self.user32.GetMonitorInfoW(mon, self.c.byref(mi)):
                return fallback
            r = mi.rcWork
            return (r.left, r.top, r.right, r.bottom)
        except Exception:
            return fallback

    def scale(self, widget, fallback=1.0):
        """Per-monitor DPI. The tray can sit on a different monitor, at a
        different scale, than the settings window."""
        if not self.ok:
            return fallback
        try:
            h = self.hwnd(widget)
            dpi = self.user32.GetDpiForWindow(h) if h else 0
            return (dpi / 96.0) if dpi else fallback
        except Exception:
            return fallback

    def foreground(self, widget):
        """Take the foreground, or the window will not receive the FocusOut
        that closes it. This is the Tk equivalent of the SetForegroundWindow
        call every Win32 tray menu has to make before TrackPopupMenu."""
        if not self.ok:
            return
        try:
            h = self.hwnd(widget)
            if h:
                self.user32.SetForegroundWindow(h)
        except Exception:
            pass

    def round_corners(self, widget):
        """DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2.

        Windows 11 only; the call fails harmlessly on 10, where menus are
        square anyway. Same API already used for the dark title bar.
        """
        if not self.ok:
            return
        try:
            h = self.hwnd(widget)
            if h:
                v = self.c.c_int(2)
                self.dwm.DwmSetWindowAttribute(h, 33, self.c.byref(v),
                                               self.c.sizeof(v))
        except Exception:
            pass


# ── the view ─────────────────────────────────────────────────────────────
class TrayMenu:
    REFRESH_MS = 250          # the buffer is live while the menu is open

    def __init__(self, root, on_action, brand=None, tokens=None):
        """Builds the window ONCE. Do this at startup, not on right-click.

        Creating a Toplevel takes long enough to be visible next to a native
        menu, and 'the menu is laggy' is the one review a custom menu cannot
        survive. Here it is created withdrawn and only ever moved and shown.
        """
        self.root = root
        self.on_action = on_action
        self.brand = brand
        self.C = dict(C)
        if tokens is not None:                 # prefer the app's own palette
            for k, attr in (("menu", "RAISED"), ("border", "LINE_STRONG"),
                            ("rule", "LINE_STRONG"), ("hover", "LINE"),
                            ("text", "TEXT"), ("muted", "MUTED"),
                            ("faint", "FAINT"), ("lit", "PURPLE_LIGHT"),
                            ("deep", "PURPLE_DEEP")):
                if hasattr(tokens, attr):
                    self.C[k] = getattr(tokens, attr)

        self.w32 = _Win32()
        self.menu = Menu.build(State())
        self.focus_i = None
        self.hover_i = None
        self._after = None
        self._state_fn = None
        self._images = []                      # Tk drops un-referenced PhotoImages
        self.scale = 1.0

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0,
                                bg=self.C["menu"])
        self.canvas.pack(fill="both", expand=True)
        self._fonts()
        self._bind()

    # ── type ─────────────────────────────────────────────────────────────
    def _fonts(self):
        def fam(role):
            if self.brand is None:
                return {"mono": "Consolas"}.get(role, "Segoe UI")
            return (self.brand.font("JetBrains Mono") if role == "mono"
                    else self.brand.weight_font(500 if role == "ui-medium" else 400))
        px = lambda n: -max(1, int(round(n * self.scale)))   # negative = pixels
        self.f_row = tkfont.Font(family=fam("ui"), size=px(13))
        self.f_row_b = tkfont.Font(family=fam("ui-medium"), size=px(13))
        self.f_status = tkfont.Font(family=fam("ui-medium"), size=px(13))
        self.f_mono = tkfont.Font(family=fam("mono"), size=px(11))
        self.f_key = tkfont.Font(family=fam("mono"), size=px(10.5))

    # ── events ───────────────────────────────────────────────────────────
    def _bind(self):
        c, w = self.canvas, self.win
        c.bind("<Motion>", self._motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        c.bind("<Button-1>", self._click)
        w.bind("<FocusOut>", lambda e: self.hide())
        for seq in ("<Escape>",):
            w.bind(seq, lambda e: self.hide())
        w.bind("<Down>", lambda e: self._move(+1))
        w.bind("<Up>", lambda e: self._move(-1))
        w.bind("<Home>", lambda e: self._focus(self.menu.first()))
        w.bind("<End>", lambda e: self._focus(self.menu.last()))
        w.bind("<Return>", lambda e: self._activate(self.focus_i))
        w.bind("<KP_Enter>", lambda e: self._activate(self.focus_i))
        w.bind("<space>", lambda e: self._activate(self.focus_i))
        w.bind("<Key>", self._typed)

    def _motion(self, ev):
        self._set_hover(self.menu.row_at(int(ev.y / self.scale)))

    def _set_hover(self, i):
        if i != self.hover_i:
            self.hover_i = i
            self._draw()

    def _click(self, ev):
        self._activate(self.menu.row_at(int(ev.y / self.scale)))

    def _move(self, step):
        self._focus(self.menu.move(self.focus_i, step))
        return "break"

    def _focus(self, i):
        self.focus_i = i
        self._draw()
        return "break"

    def _typed(self, ev):
        if len(ev.char) == 1:
            i = self.menu.type_ahead(self.focus_i, ev.char)
            if i is not None:
                return self._focus(i)

    def _activate(self, i):
        if i is None:
            return
        row = self.menu.rows[i]
        if not row.focusable:
            return
        self.hide()
        self.on_action(row.key)

    # ── show / hide ──────────────────────────────────────────────────────
    def popup(self, state, state_fn=None):
        """Show at the cursor. `state_fn` is called every REFRESH_MS while the
        menu is open so the buffer meter stays live -- pass the same callable
        that produced `state`."""
        self._state_fn = state_fn
        self.menu = Menu.build(state)
        self.focus_i = None
        self.hover_i = None

        sc = self.w32.scale(self.win, self.root.winfo_fpixels("1i") / 96.0)
        if abs(sc - self.scale) > 1e-6:
            self.scale = sc
            self._fonts()                       # DPI can differ per monitor

        w = int(round(self.menu.width * self.scale))
        h = int(round(self.menu.height * self.scale))
        cx = self.root.winfo_pointerx()
        cy = self.root.winfo_pointery()
        work = self.w32.work_area(cx, cy, (0, 0, self.root.winfo_screenwidth(),
                                           self.root.winfo_screenheight()))
        x, y = place(cx, cy, w, h, work)

        self.canvas.configure(width=w, height=h)
        self.win.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self._draw()
        self.win.deiconify()
        self.win.lift()
        self.w32.round_corners(self.win)        # after the window exists
        self.w32.foreground(self.win)
        self.win.focus_force()
        self._tick()

    def hide(self):
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
        self.win.withdraw()

    def is_open(self):
        return self.win.state() != "withdrawn"

    def toggle(self, state, state_fn=None):
        """Right-clicking the icon again should close it, not stack a second."""
        if self.is_open():
            self.hide()
        else:
            self.popup(state, state_fn)

    def _tick(self):
        if self._state_fn and self.is_open():
            try:
                s = self._state_fn()
            except Exception:
                s = None
            if s is not None:
                keep_focus, keep_hover = self.focus_i, self.hover_i
                self.menu = Menu.build(s)
                self.focus_i, self.hover_i = keep_focus, keep_hover
                self._draw()
        self._after = self.root.after(self.REFRESH_MS, self._tick)

    # ── drawing ──────────────────────────────────────────────────────────
    def _rr(self, x0, y0, x1, y1, r, fill):
        """Rounded rectangle. Tk canvas has no such primitive; a smoothed
        polygon through the corner points is the same trick brand.draw_tile
        uses, so the two stay consistent."""
        if r <= 0:
            return self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill,
                                                outline=fill)
        p = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
             x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(p, smooth=True, fill=fill, outline=fill)

    def _draw(self):
        c, s = self.canvas, self.scale
        S = lambda v: int(round(v * s))
        c.delete("all")
        self._images.clear()
        W = S(self.menu.width)
        H = S(self.menu.height)
        c.create_rectangle(0, 0, W, H, fill=self.C["menu"], outline=self.C["menu"])
        c.create_rectangle(0, 0, W - 1, H - 1, outline=self.C["border"])

        for i, row in enumerate(self.menu.rows):
            y0, y1 = S(row.y), S(row.y + row.height)
            if row.kind == SEP:
                mid = (y0 + y1) // 2
                c.create_line(S(9), mid, W - S(9), mid, fill=self.C["rule"])
                continue
            if row.kind == STATUS:
                self._status(y0, y1, W)
                continue

            focused = (i == self.focus_i)
            hovered = (i == self.hover_i) and row.enabled
            if hovered or focused:
                fill = self.C["deep"] if (row.primary and hovered) else self.C["hover"]
                self._rr(S(2), y0 + S(1), W - S(2), y1 - S(1),
                         S(ROW_RADIUS), fill)
            if focused:
                # focus is a RING, hover is a fill -- they are different states
                # and must not look the same.
                c.create_rectangle(S(2), y0 + S(1), W - S(2), y1 - S(1),
                                   outline=self.C["lit"])

            if row.enabled:
                colour = self.C["text"]
            else:
                colour = self.C["faint"]
            font = self.f_row_b if (row.primary or row.default) else self.f_row
            c.create_text(S(ROW_PAD_X) + S(TICK_W), (y0 + y1) // 2,
                          text=row.label, anchor="w", fill=colour, font=font)
            if row.accel:
                key = self.C["key"] if (row.primary and hovered) else self.C["faint"]
                if not row.enabled:
                    key = self.C["faint"]
                c.create_text(W - S(ROW_PAD_X), (y0 + y1) // 2, text=row.accel,
                              anchor="e", fill=key, font=self.f_key)

    def _status(self, y0, y1, W):
        c, s = self.canvas, self.scale
        S = lambda v: int(round(v * s))
        label, buf, fill = self.menu.status_text()
        on = self.menu.state.recording
        top = y0 + S(11)
        x = S(ROW_PAD_X)

        img = self._mark(S(MARK), self.C["lit"] if on else self.C["mark_off"])
        if img is not None:
            self._images.append(img)
            c.create_image(x, top + S(MARK) // 2, image=img, anchor="w")
        x += S(MARK) + S(GAP)
        c.create_text(x, top + S(MARK) // 2, text=label, anchor="w",
                      fill=self.C["text"] if on else self.C["muted"],
                      font=self.f_status)
        c.create_text(W - S(ROW_PAD_X), top + S(MARK) // 2, text=buf, anchor="e",
                      fill=self.C["muted"], font=self.f_mono)

        my = top + S(MARK) + S(10)
        x0, x1 = S(ROW_PAD_X), W - S(ROW_PAD_X)
        c.create_rectangle(x0, my, x1, my + S(METER_H),
                           fill=self.C["meter_bg"], outline=self.C["meter_bg"])
        if fill > 0:
            c.create_rectangle(x0, my, x0 + int((x1 - x0) * fill), my + S(METER_H),
                               fill=self.C["lit"] if on else self.C["meter_off"],
                               outline="")

    def _mark(self, px, colour):
        """The mark, from brand.py. Needs mark_image() from the overhaul's 4a;
        falls back to the old ring_image so this module still runs on a repo
        where the overhaul has not landed -- you will see the old silhouette,
        which is the signal to land it."""
        if self.brand is None:
            return None
        try:
            from PIL import ImageTk
            fn = getattr(self.brand, "mark_image", None) or self.brand.ring_image
            return ImageTk.PhotoImage(fn(px, colour))
        except Exception:
            return None
