"""Save-banner for Nab'd, built to BANNER-MOTION.md.

Normally runs as a warm daemon:  pythonw banner.py --daemon
It keeps a hidden Tk root alive and watches a trigger file, so a banner appears
within a frame or two of the hotkey instead of paying interpreter and tkinter
startup on every nab.

One-shot mode still works for testing:
    pythonw banner.py "<title>" "<detail>" [ok|fail] [monitor]

The motion is not defined here. `nabd_banner.sample(elapsed_ms)` returns every
animated value for an instant and this module only draws it, sampled against a
real clock. That indirection is the point: a dropped frame skips a value rather
than desynchronising the phases, which matters because the one machine this
ever runs on is busy running a game.
"""

import ctypes
import json
import os
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nabd  # noqa: E402
import nabd_banner as M  # noqa: E402
import nabd_sound  # noqa: E402
import nabd_tokens as T  # noqa: E402

# Take the trigger path from nabd rather than deriving it here. Frozen, this
# module lives inside the bundle, so __file__ points into _internal while the
# app writes the trigger to LOCALAPPDATA - deriving it locally would leave the
# daemon watching a file nobody ever touches.
TRIGGER = nabd.BANNER_TRIGGER

KEY = "#010203"            # chroma key, so the rounded corners are cut out
CREAM = "#F3EFE9"          # title
DETAIL_FG = "#E3D8F5"      # figures
RULE = "#F3EFE9"           # dismiss rule, drawn at 75% over the field
RULE_ALPHA = 0.75
FIELD = {"ok": T.PURPLE, "fail": T.DANGER}
FIELD_LINE = {"ok": T.PURPLE_LIGHT, "fail": "#D2665C"}

# Layout inside the 308x76 card, CSS px. The ring and the two text lines share
# a centre line; the rule sits on the bottom edge.
PAD_X, RING, GAP = 20, 30, 16
RING_CY, TITLE_CY, DETAIL_CY = 37, 28, 48
RULE_H = 3
COPY_RISE = 6              # px the mark and copy travel as they fade up

# Where the banner sits. BANNER-MOTION.md assumes bottom-right and says so:
# "the timings and easings below still hold - the geometry needs adjusting".
# Nab'd has always put it top-right, and that is where people look for it.
# The card is anchored by its BOTTOM edge so the motion still reads as the card
# standing up out of the line, which is the whole point of the rise.
MARGIN_RIGHT, MARGIN_TOP = 24, 64
# Where the card sits at rest, fully open. A click on a nab that is still
# assembling pins the timeline here until it lands.
HOLD_MS = 3100
WAITING_TEXT = "Finishing…"
# A clicked banner waits for the nab to finish writing. Assembly is a 3s settle
# plus a concat that ran 9-29s for a five minute nab, so the ordinary guard
# (delay + TOTAL_MS + 1500 = 5.6s) killed the wait before any real nab could
# land: the click did nothing at all. Two minutes is past any plausible concat.
WAIT_GUARD_MS = 120_000

SCALES = (1.0, 1.25, 1.5, 2.0)
FRAME_MS = 8               # sampling cadence; the clock decides the values


class _Timer:
    """Windows' default timer granularity is 15.6ms, so after(8) fires at
    roughly half the rate the banner asks for: measured 262 frames drawn
    across the 4120ms timeline instead of 436, median gap 15.61ms against the
    9.46ms the same run gets with the resolution raised. The panel already
    does this around its own animations; the banner is a separate process and
    was never given the same treatment.

    Refcounted, because one banner can replace another mid-flight, and held
    only while something is actually animating - it is system-wide and costs
    power.
    """

    def __init__(self):
        self.depth = 0

    def begin(self):
        if self.depth == 0:
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        self.depth += 1

    def end(self):
        if self.depth == 0:
            return
        self.depth -= 1
        if self.depth == 0:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


TIMER = _Timer()

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend two #rrggbb colours. The canvas has no per-item alpha, so every
    fade here is a colour computed against the field it sits on."""
    t = max(0.0, min(1.0, t))
    ca, cb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(
        int(round(x + (y - x) * t)) for x, y in zip(ca, cb))


def pick_scale(dpi):
    want = dpi / 96.0
    return min(SCALES, key=lambda s: abs(s - want))


def asset_dir(scale, kind):
    root = Path(nabd.ASSET_DIR) / "assets" / "banner"
    name = f"{scale:g}x" if kind == "ok" else f"{scale:g}x-fail"
    return root / name


class Assets:
    """The pre-rendered card and ring frames for one scale and field colour.

    Generated at build time (nabd_banner_frames.py). Rendering rounded
    rectangles in Pillow at launch would hand back exactly what onedir bought.
    """

    def __init__(self, scale, kind):
        self.scale = scale
        self.kind = kind
        self.dir = asset_dir(scale, kind)
        self.field = FIELD[kind]
        self._rings = {}
        self._cards = {}
        self._photo = {}

    def ring(self, index, opacity):
        """Frame `index` of 16, faded toward the field it sits on."""
        step = round(max(0.0, min(1.0, opacity)) * 8)
        key = ("ring", index, step)
        if key not in self._photo:
            img = self._rings.get(index)
            if img is None:
                img = Image.open(self.dir / f"ring_{index:02d}.png").convert("RGB")
                self._rings[index] = img
            if step < 8:
                flat = Image.new("RGB", img.size, _rgb(self.field))
                img = Image.blend(flat, img, step / 8.0)
            self._photo[key] = ImageTk.PhotoImage(img)
        return self._photo[key]

    def card(self, h, w):
        """The card at the nearest even height, stretched to `w`.

        Stretching only ever happens while the card is the 4px line - the
        slides move w, the rise moves h, and never both - so the 2px corner
        radius is all that is ever distorted.
        """
        even = max(4, min(76, int(round(h / 2.0)) * 2))
        key = ("card", even, w)
        if key not in self._photo:
            src = self._cards.get(even)
            if src is None:
                src = Image.open(self.dir / f"card_h{even:02d}.png").convert("RGBA")
                self._cards[even] = src
            img = src if src.width == w else src.resize(
                (max(1, w), src.height), Image.BILINEAR)
            self._photo[key] = ImageTk.PhotoImage(self._cut(img))
        return self._photo[key]

    def rule(self, width, colour):
        """The dismiss rule, masked to the card's own bottom edge.

        Drawn as a plain rectangle it overran the 12px bottom-left radius and
        sat outside the card. The mask is taken from the full-height card's
        alpha, so the left end curves exactly as the card does; cropping to
        `width` leaves the draining right end square, which is correct - that
        edge is the drain, not the card.
        """
        w = max(1, int(width))
        key = ("rule", w, colour)
        if key not in self._photo:
            base = self._rule_base(colour)
            self._photo[key] = ImageTk.PhotoImage(
                base.crop((0, 0, min(w, base.width), base.height)))
        return self._photo[key]

    def _rule_base(self, colour):
        key = ("rulebase", colour)
        if key not in self._cards:
            card = self._cards.get(76)
            if card is None:
                card = Image.open(self.dir / "card_h76.png").convert("RGBA")
                self._cards[76] = card
            h = max(1, int(round(RULE_H * self.scale)))
            strip = card.crop((0, card.height - h, card.width, card.height))
            out = Image.new("RGB", strip.size, _rgb(KEY))
            alpha = strip.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
            out.paste(Image.new("RGB", strip.size, _rgb(colour)), (0, 0), alpha)
            self._cards[key] = out
        return self._cards[key]

    @staticmethod
    def _cut(img):
        """Flatten onto the chroma key with a hard alpha edge.

        Tk has no per-pixel alpha window, so the corners are cut with a colour
        key. Keeping the antialiased edge would leave every partly transparent
        pixel blended toward near-black - a dark fringe around the radius on
        whatever is behind. A hard edge is the honest trade.
        """
        out = Image.new("RGB", img.size, _rgb(KEY))
        alpha = img.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        out.paste(img.convert("RGB"), (0, 0), alpha)
        return out


class Banner:
    """One 4,120 ms run. Replaces any banner already on screen."""

    def __init__(self, root, title, detail="", kind="ok", monitor=0,
                 delay=0.0, on_close=None, assets=None, path=None,
                 ready=False, token="", sound=None):
        self.root = root
        self.sound = sound
        self.on_close = on_close
        self.done = False
        self.token = token        # which nab this banner belongs to
        self._timing = False      # holds the 1ms timer while it animates
        self.path = path
        self.ready = ready
        self._waiting = False       # clicked, but the nab is still assembling
        self.kind = kind if kind in FIELD else "ok"
        self.field = FIELD[self.kind]
        self.title = title
        self.detail = detail

        mon = self._monitor(monitor)
        self.mx, self.my, self.mw, self.mh = mon
        dpi = self._dpi_for(self.mx, self.my)
        self.scale = pick_scale(dpi)
        self.px = lambda v: int(round(v * self.scale))
        self.assets = assets or Assets(self.scale, self.kind)

        self.win = win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=KEY)
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)

        self.canvas = tk.Canvas(win, bg=KEY, highlightthickness=0, bd=0,
                                width=self.px(M.CARD_W),
                                height=self.px(M.CARD_H))
        self.canvas.pack()
        # WS_EX_NOACTIVATE stops the banner taking focus; it does not stop it
        # receiving clicks. Opening the nab is the one thing anyone would want
        # to do with this, so it is worth the one binding.
        self.canvas.bind("<Button-1>", self._click)
        self._set_cursor()

        # Anchored to the BOTTOM edge, which is the one the motion pins. The
        # asset is only baked at even heights (round(h/2)*2), so on an odd
        # frame it is a pixel taller or shorter than the window; anchored at
        # the top that pixel landed on the fixed bottom edge and the card
        # wobbled for ~6 frames of every rise and collapse.
        self.card_item = self.canvas.create_image(0, 0, anchor="sw")
        self.ring_item = self.canvas.create_image(0, 0, anchor="nw", state="hidden")
        self.title_item = self.canvas.create_text(
            0, 0, anchor="w", text=title, fill=self.field,
            font=(T.FONT_UI_MEDIUM, -self.px(15)))
        self.detail_item = self.canvas.create_text(
            0, 0, anchor="w", text=detail, fill=self.field,
            font=(T.FONT_MONO, -self.px(12)))
        self.rule_item = self.canvas.create_image(0, 0, anchor="nw",
                                                  state="hidden")

        self.start = None
        self._delay = max(0.0, float(delay))
        # The sound has to LEAVE before the animation starts, because the
        # output device does not make it audible for another LEAD_MS. Both are
        # scheduled off this one construction, so the gap between them is the
        # lead and nothing else.
        #
        # The banner does not move: the existing pre-roll absorbs the lead, so
        # play lands at (delay - lead) and the picture still starts at delay.
        # Only when the pre-roll is shorter than the lead does the picture wait
        # - it is the one case where there is nowhere else to take it from.
        lead = nabd_sound.LEAD_MS / 1000.0
        # A device that has gone quiet charges to wake up, and it charges
        # whichever sound is played first. Asked BEFORE priming, since priming
        # is what stops it being cold.
        warm_up = 0.0
        if self.sound and self.sound != "off":
            if nabd_sound.cold():
                warm_up = nabd_sound.COLD_EXTRA_MS / 1000.0
            nabd_sound.prime()
        start_at = self._delay + warm_up
        self.root.after(int(max(0.0, start_at - lead) * 1000),
                        self._play_sound)
        self.root.after(int(max(start_at, lead) * 1000), self._begin)
        # Hard stop, in case a frame callback is ever lost: the banner must not
        # be able to sit on screen forever.
        self._guard = self.root.after(
            int(start_at * 1000) + M.TOTAL_MS + 1500, self.finish)

    # -- placement ---------------------------------------------------------

    @staticmethod
    def _monitor(index):
        try:
            mons = nabd.list_monitors()
            if 0 <= index < len(mons):
                m = mons[index]
                return m["x"], m["y"], m["width"], m["height"]
        except Exception:
            pass
        u = ctypes.windll.user32
        return 0, 0, u.GetSystemMetrics(0), u.GetSystemMetrics(1)

    @staticmethod
    def _dpi_for(x, y):
        try:
            pt = wintypes.POINT(x + 8, y + 8)
            mon = ctypes.windll.user32.MonitorFromPoint(pt, 2)   # NEAREST
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            if ctypes.windll.shcore.GetDpiForMonitor(
                    mon, 0, ctypes.byref(dx), ctypes.byref(dy)) == 0:
                return dx.value
        except Exception:
            pass
        return 96

    def _no_activate(self):
        try:
            hwnd = (ctypes.windll.user32.GetParent(self.win.winfo_id())
                    or self.win.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        except Exception:
            pass

    # -- run ---------------------------------------------------------------

    def _begin(self):
        if self.done:
            return
        self.win.deiconify()
        self._no_activate()
        TIMER.begin()
        self._timing = True
        self.start = time.perf_counter()
        self._tick()

    def _play_sound(self):
        """LEAD_MS before the clock starts - see __init__.

        The file is TOTAL_MS long with its own beats baked in, so once it is
        away there is nothing left to schedule and nothing that can drift.
        Returns at once and never raises.
        """
        if self.done:
            return                  # replaced or dismissed before it began
        nabd_sound.play(self.sound)

    def _tick(self):
        """Sampled off the wall clock, not a tick counter and not chained
        callbacks - a slow frame skips a value instead of stretching a phase."""
        if self.done:
            return
        t = (time.perf_counter() - self.start) * 1000.0
        if self._waiting:
            # Someone clicked while the nab was still being written. Pinned at
            # rest until it lands, then the exit plays from there as normal.
            # Clamped rather than frozen where it stood, so a click during the
            # exit brings the card back up instead of leaving it half folded.
            t = min(t, HOLD_MS)
            self.start = time.perf_counter() - t / 1000.0
        if t >= M.TOTAL_MS:
            self.finish()
            return
        try:
            self.draw(M.sample(t))
        except tk.TclError:
            self.finish()
            return
        self.root.after(FRAME_MS, self._tick)

    def draw(self, f):
        px, canvas = self.px, self.canvas
        w, h = max(1, px(f.w)), max(1, px(f.h))

        self.win.attributes("-alpha", f.alpha)
        # The slides move w and x, the rise and collapse move h and y, and the
        # two never land in the same geometry() call. Together they would read
        # as one diagonal expansion out of the corner.
        x = self.mx + self.mw - px(MARGIN_RIGHT) - w
        y = self.my + px(MARGIN_TOP) + px(M.CARD_H) - h
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        canvas.configure(width=w, height=h)

        canvas.itemconfigure(self.card_item, image=self.assets.card(f.h, w))
        canvas.coords(self.card_item, 0, h)

        if f.copy <= 0.001:
            canvas.itemconfigure(self.ring_item, state="hidden")
            canvas.itemconfigure(self.title_item, text="")
            canvas.itemconfigure(self.detail_item, text="")
        else:
            rise = px(COPY_RISE) * (1.0 - f.copy)
            index = int(round(f.ring * 16))
            if index > 0:
                canvas.itemconfigure(self.ring_item, state="normal",
                                     image=self.assets.ring(index, f.copy))
                canvas.coords(self.ring_item, px(PAD_X),
                              px(RING_CY - RING / 2) + rise)
            else:
                canvas.itemconfigure(self.ring_item, state="hidden")
            tx = px(PAD_X + RING + GAP)
            canvas.itemconfigure(self.title_item, text=self.title,
                                 fill=mix(self.field, CREAM, f.copy))
            canvas.coords(self.title_item, tx, px(TITLE_CY) + rise)
            canvas.itemconfigure(self.detail_item, text=self.detail,
                                 fill=mix(self.field, DETAIL_FG, f.copy))
            canvas.coords(self.detail_item, tx, px(DETAIL_CY) + rise)

        # The rule fades in as the purple-light line baked into the short cards
        # fades out, then drains. Quantised to 2px and 8 opacity steps so the
        # cache stays small across the 2.6s drain.
        shown = 1.0 - f.line
        rule_w = int(w * f.drain) // 2 * 2
        if rule_w <= 0 or f.h < M.CARD_H - 1:
            canvas.itemconfigure(self.rule_item, state="hidden")
        else:
            colour = mix(self.field,
                         mix(self.field, RULE, RULE_ALPHA),
                         round(shown * 8) / 8.0)
            canvas.itemconfigure(self.rule_item, state="normal",
                                 image=self.assets.rule(rule_w, colour))
            canvas.coords(self.rule_item, 0, h - px(RULE_H))

    def _set_cursor(self):
        try:
            self.canvas.configure(cursor="hand2" if self.path else "")
        except tk.TclError:
            pass

    def _click(self, _event=None):
        """Open the nab - or wait for it, if it is still being assembled.

        A five minute nab takes tens of seconds to concatenate, far longer
        than this banner lives, so a click almost always lands while the file
        is still open. Opening it then would hand a half written mp4 to the
        player; holding instead costs nothing and does what was asked.
        """
        if not self.path or self.done:
            return
        if not self.ready:
            if not self._waiting:
                self._waiting = True
                # The timeline pins at HOLD_MS from here, but the sound cannot
                # be paused - it would play its exit while the card is still
                # standing. Cut it instead. HOLD_MS falls inside the file's
                # two and a half seconds of silence, so the cut is inaudible.
                nabd_sound.stop()
                self.set_detail(WAITING_TEXT)
                # The hold outlives the timeline, so the hard stop has to move
                # with it or it fires mid-wait and the click is lost.
                try:
                    self.root.after_cancel(self._guard)
                except Exception:
                    pass
                self._guard = self.root.after(WAIT_GUARD_MS, self._expire)
            return
        self._open()

    def _expire(self):
        """Waited long enough. Give up rather than sit on screen forever."""
        self._waiting = False
        self.finish()

    def _open(self):
        try:
            os.startfile(self.path)
        except OSError:
            pass
        self.finish()

    def set_path(self, path):
        self.path = path
        self._set_cursor()

    def set_ready(self, ready=True):
        """The nab is closed and safe to open."""
        self.ready = bool(ready)
        if self.ready and self._waiting:
            self._open()

    def set_detail(self, detail):
        """Fill in a figure that was not known when the banner opened, without
        restarting the timeline."""
        self.detail = detail
        try:
            self.canvas.itemconfigure(self.detail_item, text=detail)
        except tk.TclError:
            pass

    def finish(self):
        if self.done:
            return
        self.done = True
        if self._timing:
            self._timing = False
            TIMER.end()
        try:
            self.root.after_cancel(self._guard)
        except Exception:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# daemon
# --------------------------------------------------------------------------

def _stamp():
    try:
        return TRIGGER.stat().st_mtime_ns
    except OSError:
        return None


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
    state = {"stamp": stamp, "current": None, "assets": {}}

    def assets_for(scale, kind):
        key = (scale, kind)
        if key not in state["assets"]:
            state["assets"][key] = Assets(scale, kind)
        return state["assets"][key]

    def poll():
        stamp = _stamp()
        if stamp and stamp != state["stamp"]:
            state["stamp"] = stamp
            try:
                data = json.loads(TRIGGER.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if data:
                _apply(data)
        root.after(40, poll)

    def _apply(data):
        # An update only fills in a figure on the banner already running; it
        # must not restart the timeline underneath it.
        if data.get("update"):
            cur = state["current"]
            # Only onto the banner these figures were measured from. Assembly
            # takes tens of seconds and anything can raise a banner meanwhile;
            # without the token a "Capture Lost" card inherited the nab's
            # size, path and hand cursor and showed "5:00 - 1.2 GB".
            #
            # The token only protects a banner that is still on screen. Asking
            # it first meant a finished banner from the last nab - which
            # state["current"] holds for ever - matched nothing and threw the
            # payload away, so from the second nab on nothing was raised at
            # all.
            if cur and not cur.done:
                if cur.token != data.get("token", ""):
                    return
                if data.get("detail") and not cur._waiting:
                    cur.set_detail(data["detail"])
                if data.get("path"):
                    cur.set_path(data["path"])
                if data.get("ready"):
                    cur.set_ready(True)
                return
            # No live banner to update. The figures follow the banner within
            # milliseconds and the poll is 40ms, so both writes can land
            # between two polls - an update that carries the whole payload
            # raises it rather than the banner being lost entirely.
            if not data.get("title") or data.get("ready"):
                return          # a completion with nothing left to show
        if not data.get("title"):
            return
        if state["current"]:
            state["current"].finish()
        kind = data.get("kind", "ok")
        mon = int(data.get("monitor", 0))
        scale = pick_scale(Banner._dpi_for(*Banner._monitor(mon)[:2]))
        state["current"] = Banner(
            root, data["title"], data.get("detail", ""), kind, mon,
            float(data.get("delay", 0.0)),
            assets=assets_for(scale, kind), path=data.get("path"),
            ready=bool(data.get("ready")), token=data.get("token", ""),
            sound=data.get("sound"))

    root.after(40, poll)
    root.mainloop()


def run_once(title, detail, kind, monitor):
    set_dpi_aware()
    root = tk.Tk()
    root.withdraw()

    def quit_root():
        try:
            root.destroy()
        except tk.TclError:
            pass

    Banner(root, title, detail, kind, monitor, on_close=quit_root)
    root.mainloop()


def main():
    if "--daemon" in sys.argv:
        run_daemon()
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    title = args[0] if args else "Nabbed"
    detail = args[1] if len(args) > 1 else "5:00 · 1.2 GB"
    kind = args[2] if len(args) > 2 else "ok"
    monitor = int(args[3]) if len(args) > 3 else 0
    run_once(title, detail, kind, monitor)


if __name__ == "__main__":
    main()
