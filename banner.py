"""
Slide-out confirmation banner for Nab'd.

Normally runs as a warm daemon:  pythonw banner.py --daemon
It keeps a hidden Tk root alive and watches a trigger file, so a banner appears
within a frame or two of the hotkey instead of paying ~1s of interpreter and
tkinter startup on every clip.

One-shot mode still works for testing:
    pythonw banner.py "<text>" [ok|fail] [monitor]
"""

import ctypes
import json
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brand  # noqa: E402
import nabd  # noqa: E402

# Take the trigger path from nabd rather than deriving it here. Frozen, this
# module lives inside the bundle, so __file__ points into _internal while the
# app writes the trigger to LOCALAPPDATA - deriving it locally would leave the
# daemon watching a file nobody ever touches.
TRIGGER = nabd.BANNER_TRIGGER

WIDTH, HEIGHT = 372, 66
MARGIN_RIGHT, MARGIN_TOP = 24, 64
# HOLD_MS is how long the underline takes to drain, which is what sets the
# banner's dwell. Frames land a little slower than nominal, so the felt time is
# a shade longer than this.
SLIDE_MS, HOLD_MS, STEPS = 260, 1800, 22
DELAY_MS = 200  # beat between the keypress and the banner moving

BG = brand.INK            # raised surface over the shell
EDGE = "#2D2A35"
TEXT = brand.CREAM
ACCENT = {"ok": brand.PURPLE_LIGHT, "fail": "#E5484D"}
RING = 30                 # the bare mark, drawing itself as the banner lands
RING_X = 16               # left inset of the mark
GUTTER = 16               # logo-to-content gap, mirrored on the right edge
FRAME_MS = 16             # ~60fps for every animation step

# The mark and the underline both build over BUILD_MS, starting only once the
# panel has finished sliding in. Sharing a start and a duration is what makes
# them land on the same beat.
BUILD_MS = 560
UNDRAW_MS = 340           # retracing the mark away before the banner leaves
TEXT_MS = 260             # the text easing into place behind it
SHEEN_MS = 460            # the shimmer that acknowledges the build finishing
SHEEN_HALF = 30           # half-width of the gloss band
SHEEN_SLICES = 14         # solid slices standing in for a gradient
SHEEN_TINT = "#3A3348"    # the highlight it blends toward
KEY = "#010203"  # chroma key for the rounded corners

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


def monitor_rects():
    """Work areas in the same order Nab'd numbers displays (primary first)."""
    found = []

    def cb(hmon, hdc, rect, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            found.append({"left": w.left, "top": w.top, "right": w.right,
                          "bottom": w.bottom, "primary": bool(mi.dwFlags & 1)})
        return 1

    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, proto(cb), 0)
    found.sort(key=lambda m: (not m["primary"], m["left"]))
    return found or [{"left": 0, "top": 0, "right": 1920, "bottom": 1080,
                      "primary": True}]


RING_STEPS = 26
_ring_cache = {}


def ring_frames(size, colour):
    """Antialiased frames of the mark drawing itself.

    The Tk canvas cannot antialias an arc, so the stroke is rendered by PIL
    once per process and swapped as an image. Built lazily and cached: the
    resident helper pays for it on the first banner only.
    """
    key = (size, colour)
    if key in _ring_cache:
        return _ring_cache[key]
    try:
        from PIL import ImageTk
        frames = [ImageTk.PhotoImage(
            brand.ring_image(size, colour, progress=i / RING_STEPS))
            for i in range(RING_STEPS + 1)]
    except Exception:
        frames = None          # fall back to drawing on the canvas
    _ring_cache[key] = frames
    return frames


def blend(base, tint, f):
    """Mix two #rrggbb colours; the canvas cannot do alpha, so do it here."""
    f = max(0.0, min(1.0, f))
    a = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(tint[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * f) for x, y in zip(a, b))


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def ease_out(t):
    return 1 - (1 - t) ** 3


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class Banner:
    """One slide-in/slide-out run. Replaces any banner already on screen."""

    def __init__(self, root, text, kind="ok", monitor=0, delay=DELAY_MS / 1000,
                 on_close=None):
        self.root = root
        self.done = False
        # Owned rather than monkeypatched: callbacks scheduled in here capture
        # the bound method immediately, so a later reassignment would be
        # invisible to the hard-stop timer and leave the caller hanging.
        self.on_close = on_close
        self.accent = ACCENT.get(kind, ACCENT["ok"])
        mons = monitor_rects()
        mon = mons[monitor] if 0 <= monitor < len(mons) else mons[0]

        self.win = win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=KEY)
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass

        self.canvas = canvas = tk.Canvas(win, width=WIDTH, height=HEIGHT, bg=KEY,
                                         highlightthickness=0, bd=0)
        canvas.pack()
        round_rect(canvas, 1, 1, WIDTH - 1, HEIGHT - 1, 14, fill=BG, outline=EDGE)

        # The bare ring, turning while the clip is written. Purple Light, not
        # Nabd Purple: full-strength purple linework on this surface would sit
        # at 2.7:1, under the contrast floor.
        self.ring_x = RING_X
        self.ring_y = (HEIGHT - RING) / 2
        self.trace = 0.0
        self.frames = ring_frames(RING, self.accent)
        self.ring_item = canvas.create_image(
            self.ring_x, self.ring_y, anchor="nw", tags="ring") \
            if self.frames else None
        self._paint_ring()

        # Outfit SemiBold at 17px - the heaviest weight in the guidelines'
        # scale, so the message carries at a glance mid-game.
        self.text_x = self.ring_x + RING + GUTTER
        self.text_id = canvas.create_text(
            self.text_x + 10, HEIGHT / 2 - 5, text=text, anchor="w",
            fill=TEXT, font=(brand.weight_font(600), -17))
        canvas.bind("<Button-1>", lambda _e: self.finish())

        self.y = mon["top"] + MARGIN_TOP
        self.x_off = mon["right"]
        self.x_on = mon["right"] - WIDTH - MARGIN_RIGHT
        win.geometry(f"{WIDTH}x{HEIGHT}+{self.x_off}+{self.y}")
        win.update_idletasks()

        # Never take focus - a banner stealing input mid-fight would be worse
        # than no banner at all.
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        except Exception:
            pass

        # A beat before it moves. Appearing on the same frame as the keypress
        # reads as a glitch rather than a response.
        win.after(max(0, int(delay * 1000)), self._enter)
        # Hard stop, so a stuck animation can never leave a banner on screen.
        # Sized from the whole sequence plus slack: set too tight it fires
        # first, truncating the exit instead of guarding it.
        budget = (int(delay * 1000) + SLIDE_MS * 2 + BUILD_MS + SHEEN_MS
                  + HOLD_MS + UNDRAW_MS + 2500)
        win.after(budget, self.finish)

    def _paint_ring(self):
        if self.frames:
            step = max(0, min(RING_STEPS, round(self.trace * RING_STEPS)))
            self.canvas.itemconfigure(self.ring_item, image=self.frames[step])
            return
        self.canvas.delete("ring")
        brand.draw_mark(self.canvas, self.ring_x, self.ring_y, RING,
                        self.accent, progress=self.trace, tags=("ring",))

    def _animate(self, duration, step, done=None, ease=None):
        """Run `step(t)` with t moving 0 -> 1 over `duration` ms."""
        frames = max(1, duration // FRAME_MS)
        ease = ease or ease_out

        def tick(i=0):
            if self.done:
                return
            try:
                step(ease(i / frames))
            except tk.TclError:
                return
            if i < frames:
                self.win.after(FRAME_MS, tick, i + 1)
            elif done:
                done()

        tick()

    def _enter(self):
        if self.done:
            return
        self._built = 0
        self._slide(0, True, self._arrived)

    def _set_trace(self, t):
        self.trace = t
        self._paint_ring()

    def _arrived(self):
        """Everything builds once the panel has landed, not during the slide.

        The mark and the underline share a start and a duration, so they finish
        on the same beat without any timing arithmetic.
        """
        self._animate(BUILD_MS, self._set_trace, self._stage_done)
        self._animate(BUILD_MS, self._draw_rule, self._stage_done)
        self._animate(TEXT_MS, self._settle_text)

    def _stage_done(self):
        """Both build animations have to land before the shimmer fires.

        Counted rather than timed: frames drift, and triggering off whichever
        was nominally longer would sometimes fire early.
        """
        self._built += 1
        if self._built >= 2 and not self.done:
            self._animate(SHEEN_MS, self._shimmer, self._start_drain,
                          ease=lambda t: t)

    def _shimmer(self, t):
        """A soft band crossing the panel once the build completes.

        Drawn as a handful of solid slices blended toward a highlight rather
        than a stippled rectangle: the Tk canvas has no per-item alpha, and
        stipple reads as a dotted block instead of a gloss.
        """
        self.canvas.delete("sheen")
        if t >= 1.0:
            return
        # Kept inside the content area so square slices never overhang the
        # panel's rounded corners.
        left, right = self.ring_x - 6, WIDTH - GUTTER + 6
        centre = left - SHEEN_HALF + (right - left + SHEEN_HALF * 2) * t

        for i in range(SHEEN_SLICES):
            a = centre - SHEEN_HALF + (SHEEN_HALF * 2) * i / SHEEN_SLICES
            b = centre - SHEEN_HALF + (SHEEN_HALF * 2) * (i + 1) / SHEEN_SLICES
            if b < left or a > right:
                continue
            # Bell across the band, so it has a soft head and tail.
            strength = 1 - abs((i + 0.5) / SHEEN_SLICES - 0.5) * 2
            self.canvas.create_rectangle(
                max(a, left), 4, min(b, right), HEIGHT - 4,
                fill=blend(BG, SHEEN_TINT, strength * 0.9), outline="",
                tags="sheen")

        # The panel's content rides above the gloss.
        for tag in ("ring", "rule"):
            self.canvas.tag_raise(tag)
        self.canvas.tag_raise(self.text_id)

    def _settle_text(self, t):
        self.canvas.coords(self.text_id, self.text_x + 10 * (1 - t),
                           HEIGHT / 2 - 5)

    def _rule_span(self):
        """Full width of the content area: it starts where the text starts and
        ends a matching gutter in from the right edge."""
        return self.text_x, WIDTH - GUTTER

    def _draw_rule(self, t):
        x0, x1 = self._rule_span()
        self.canvas.delete("rule")
        if t > 0.01:
            self.canvas.create_line(x0, HEIGHT / 2 + 13,
                                    x0 + (x1 - x0) * t, HEIGHT / 2 + 13,
                                    fill=self.accent, width=2,
                                    capstyle="round", tags="rule")

    def _start_drain(self):
        """The underline empties over the hold, so the bar is still moving
        right up to the moment the banner leaves."""
        # Linear: it is a clock, and easing would make the wait read as uneven.
        self._animate(HOLD_MS, self._drain_rule, self._leave, ease=lambda t: t)

    def _drain_rule(self, t):
        x0, x1 = self._rule_span()
        self.canvas.delete("rule")
        left = x0 + (x1 - x0) * t
        if x1 - left > 1:
            self.canvas.create_line(left, HEIGHT / 2 + 13, x1, HEIGHT / 2 + 13,
                                    fill=self.accent, width=2,
                                    capstyle="round", tags="rule")

    def _leave(self):
        """Retrace the mark away, then go.

        The stroke unwinds the way it arrived, so the banner closes on the same
        gesture it opened with instead of just vanishing.
        """
        self._animate(UNDRAW_MS, lambda t: self._set_trace(1 - t),
                      lambda: self._slide(0, False, self.finish),
                      ease=lambda t: t * t)

    def _slide(self, step, forward, then):
        if self.done:
            return
        t = step / STEPS
        f = ease_out(t) if forward else ease_out(1 - t)
        x = int(self.x_off + (self.x_on - self.x_off) * f)
        try:
            self.win.geometry(f"{WIDTH}x{HEIGHT}+{x}+{self.y}")
            # Repaint synchronously. Moving the window invalidates it, and
            # Windows erases with the system class brush - white - if Tk has
            # not painted by the time the frame is composed.
            self.win.update_idletasks()
        except tk.TclError:
            return
        if step < STEPS:
            self.win.after(SLIDE_MS // STEPS, self._slide, step + 1, forward, then)
        else:
            then()

    def finish(self):
        if self.done:
            return
        self.done = True
        # Unmap before teardown, so no half-destroyed frame is ever composed.
        for step in ("withdraw", "destroy"):
            try:
                getattr(self.win, step)()
            except tk.TclError:
                pass
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass


def run_daemon():
    """Hold a hidden root open and show a banner whenever the trigger changes."""
    set_dpi_aware()
    root = tk.Tk()
    root.withdraw()

    # If the app wrote a trigger moments ago it was probably starting us for
    # that very banner, so honour it instead of swallowing it.
    stamp = _stamp()
    try:
        if time.time() - TRIGGER.stat().st_mtime < 3.0:
            stamp = None
    except OSError:
        pass
    state = {"stamp": stamp, "current": None}

    def poll():
        stamp = _stamp()
        if stamp and stamp != state["stamp"]:
            state["stamp"] = stamp
            try:
                data = json.loads(TRIGGER.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if data and data.get("text"):
                if state["current"]:
                    state["current"].finish()
                state["current"] = Banner(
                    root, data["text"], data.get("kind", "ok"),
                    int(data.get("monitor", 0)),
                    float(data.get("delay", DELAY_MS / 1000)))
        root.after(40, poll)

    root.after(40, poll)
    root.mainloop()


def _stamp():
    try:
        return TRIGGER.stat().st_mtime_ns
    except OSError:
        return None


def run_once(text, kind, monitor):
    set_dpi_aware()
    root = tk.Tk()
    root.withdraw()

    def quit_root():
        try:
            root.destroy()
        except tk.TclError:
            pass

    Banner(root, text, kind, monitor, on_close=quit_root)
    root.mainloop()


def main():
    if "--daemon" in sys.argv:
        run_daemon()
        return
    text = sys.argv[1] if len(sys.argv) > 1 else "Nab'd!"
    kind = sys.argv[2] if len(sys.argv) > 2 else "ok"
    monitor = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    run_once(text, kind, monitor)


if __name__ == "__main__":
    main()
