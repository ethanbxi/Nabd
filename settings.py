"""Settings panel for Nab'd - rebuild against SETTINGS-REDESIGN.md.

Runs as its own process (tkinter and the tray icon cannot share a main thread).
Saving writes config.json; the running app notices the change within a few
seconds and rebuilds the capture pipeline without a restart.

The layout is one grammar repeated: every row is a flexing label on the left and
a fixed 344px control column on the right, and anything secondary - a meter, a
volume slider, helper text - stacks *inside* that column so it stays attached to
its control and every control's left edge lines up down the panel.

One thing the spec asks for is deliberately absent: the sticky group eyebrows.
In CSS that is one line; in Tk it is a floating overlay whose text and position
must be recomputed on every scroll event, for a navigation aid on six groups.
The build guide's own advice was to ship without it.

Group order departs from the spec on purpose - Hotkeys sits directly under
Capture rather than last, because those two carry the settings people actually
come here to change.
"""
import ctypes
import datetime
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import winsound
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog

from PIL import Image

import brand
import nabd
import nabd_avtest as AV
import nabd_sound
import nabd_paint as P
import nabd_panel_open as M
import nabd_tokens as T
import nabd_ui as U

QUALITY = [("Highest", 18), ("High", 23), ("Medium", 28), ("Low", 33)]

# Bits per pixel per frame, used only while the ring buffer is too cold to
# measure. See SETTINGS-REDESIGN.md 4.3; the measured path in _bytes_per_sec
# supersedes it the moment there are three segments on disk.
BPP = {18: 0.19, 23: 0.15, 28: 0.10, 33: 0.06}
AUDIO_BPS = 320_000          # two 160 kbps AAC tracks
CONTAINER = 1.02             # muxing overhead
BITRATE_CAP = 250_000_000

MOD_KEYSYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L",
               "Shift_R", "Super_L", "Super_R", "Win_L", "Win_R"}
# Tk state bits on Windows. NumLock is 0x0008 and ScrollLock 0x0020 - neither is
# a modifier, and treating them as one silently injects Alt into every captured
# combo whenever NumLock happens to be on.
STATE_SHIFT, STATE_CTRL, STATE_ALT = 0x0001, 0x0004, 0x20000
NAMED_KEYS = {"Insert": "insert", "Delete": "delete", "Home": "home",
              "End": "end", "Prior": "pageup", "Next": "pagedown",
              "space": "space", "Tab": "tab", "Pause": "pause",
              "Scroll_Lock": "scrolllock", "Print": "print"}

PER_PAGE = 3
MAX_RECENT = 15


# ---------------------------------------------------------------------------
# win32 helpers
# ---------------------------------------------------------------------------

def screen_rect():
    """Full primary display, taskbar included - the panel runs its whole
    height and sits topmost to stay visible over the taskbar."""
    r = wintypes.RECT()
    r.left, r.top = 0, 0
    r.right = ctypes.windll.user32.GetSystemMetrics(0)
    r.bottom = ctypes.windll.user32.GetSystemMetrics(1)
    return r


def force_foreground(hwnd):
    """Actually bring a window to the front.

    SetForegroundWindow alone is refused unless the calling thread owns the
    current foreground window, which a tray-launched process does not.
    """
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.GetForegroundWindow() == hwnd:
        return True
    foreign = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    ours = kernel32.GetCurrentThreadId()
    attached = bool(foreign and foreign != ours
                    and user32.AttachThreadInput(ours, foreign, True))
    try:
        user32.ShowWindow(hwnd, 5)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(ours, foreign, False)


class _Timer:
    """Windows' default timer granularity is 15.6ms, so an after(8) loop fires
    at roughly half the rate it asks for and the slide reads as a judder.
    timeBeginPeriod raises the resolution; it is system-wide and costs power,
    so it is held only for the length of an animation.
    """

    def __init__(self):
        self.depth = 0

    def __enter__(self):
        if self.depth == 0:
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        self.depth += 1
        return self

    def __exit__(self, *_exc):
        self.depth -= 1
        if self.depth == 0:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        return False

    def begin(self):
        self.__enter__()

    def end(self):
        if self.depth:
            self.__exit__()


TIMER = _Timer()


def ease(t):
    """Cubic in-out.

    A pure ease-out covers a third of a 640px travel in its first two frames
    and then creeps a pixel at a time - which reads as a lurch followed by a
    crawl rather than as motion. This starts and ends gently instead.
    """
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def focus_existing():
    hwnd = ctypes.windll.user32.FindWindowW(
        None, f"{nabd.DISPLAY_NAME} Settings")
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, 9)
    force_foreground(hwnd)
    return True


# Only the built-ins that actually ship, plus the user's own file. resolve()
# reads "off" as silence, a .wav as a path, and anything else as a built-in
# name, so these labels only have to map onto those three shapes.
SOUND_LABELS = ("Off", "Pip", "Custom\u2026")

AV_HELP = ("Negative pulls audio earlier. Test records a timing pattern and "
           "opens it.")

# How much to ask the daemon for. The card runs TOTAL_MS and the save is
# triggered at the end of it, after which the clipper settles for save_delay
# before it picks segments - so the window has to reach back over the card AND
# that settle. The extra is not rounding slack: the newest segment is the one
# ffmpeg still has open, and it is routinely skipped as unreadable, so the
# reach that actually arrives is one segment shorter than the arithmetic says.
AV_CLIP_SECONDS = int(AV.TOTAL_MS / 1000.0) + 6


# ---------------------------------------------------------------------------
# size estimate
# ---------------------------------------------------------------------------

def measured_bytes_per_sec(sample=15):
    """True byte rate straight off the ring buffer, or None if it is cold.

    This is the whole reason the panel does not need the bits-per-pixel model:
    there are 2-second segments sitting on disk written by the encoder that
    actually won the probe, so the rate is one stat call away and it tracks
    scene complexity live.
    """
    try:
        segs = sorted(Path(nabd.BUFFER_DIR).glob("*.ts"),
                      key=lambda p: p.stat().st_mtime)[-sample:]
    except OSError:
        return None
    if len(segs) < 3:
        return None
    try:
        if time.time() - segs[-1].stat().st_mtime > 60:
            return None      # recorder stopped; these segments are history
        total = sum(s.stat().st_size for s in segs)
    except OSError:
        return None
    seconds = len(segs) * 2.0
    return total / seconds if seconds else None


def modelled_bytes_per_sec(w, h, fps, cq):
    video = min(w * h * fps * BPP.get(cq, 0.15), BITRATE_CAP)
    return (video + AUDIO_BPS) * CONTAINER / 8.0


def human_bytes(n):
    """1024-based, to match what Explorer shows."""
    for unit, size in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20)):
        if n >= size:
            return f"{n / size:.1f} {unit}"
    return f"{n / 1024:.0f} KB"


# Somewhere no monitor reaches, for the one forced layout pass at startup.
PARK_X = -32000

_RDW_INVALIDATE = 0x0001
_RDW_ALLCHILDREN = 0x0080
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000
_SRCCOPY = 0x00CC0020
# INVALIDATE | ERASE | ALLCHILDREN | UPDATENOW
_RDW_PAINT_NOW = 0x0001 | 0x0004 | 0x0080 | 0x0100


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def window_pixels(hwnd, x, y, w, h):
    """A rect of a window's own surface, client-relative, as a PIL image.

    Reads the redirection surface rather than the screen, so it works on a
    window nobody can see - alpha 0, or covered by another window. It does
    NOT work on a window Windows has never painted; see _photograph_hidden.
    """
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    dc = u32.GetDC(hwnd)
    if not dc:
        return None
    mdc = bmp = None
    try:
        mdc = g32.CreateCompatibleDC(dc)
        bmp = g32.CreateCompatibleBitmap(dc, w, h)
        old = g32.SelectObject(mdc, bmp)
        g32.BitBlt(mdc, 0, 0, w, h, dc, x, y, _SRCCOPY)
        hdr = _BITMAPINFOHEADER()
        hdr.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        hdr.biWidth, hdr.biHeight = w, -h      # negative: top-down
        hdr.biPlanes, hdr.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        got = g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(hdr), 0)
        g32.SelectObject(mdc, old)
        if not got:
            return None
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        if bmp:
            g32.DeleteObject(bmp)
        if mdc:
            g32.DeleteDC(mdc)
        u32.ReleaseDC(hwnd, dc)
# NOSIZE | NOZORDER | NOACTIVATE | NOOWNERZORDER
_SWP_MOVE = 0x0001 | 0x0004 | 0x0010 | 0x0200
# the same without NOSIZE, for the one place the window legitimately resizes
_SWP_SIZE = 0x0004 | 0x0010 | 0x0200


def repaint(widget):
    """Mark a widget and its children dirty.

    Moving a Tk window makes Windows blit its pixels to the new position, but
    Tk also repaints part of it from its own display list, and the two disagree
    across the strip the window vacated - which showed up as every label in a
    slipping block being drawn twice, 30px apart. Invalidating after the move
    makes the whole block repaint from one source.
    """
    try:
        ctypes.windll.user32.RedrawWindow(
            widget.winfo_id(), None, None,
            _RDW_INVALIDATE | _RDW_ALLCHILDREN)
    except Exception:
        pass


def device_name(dev):
    """A device's name, whichever shape the enumerator returned.

    list_speakers yields {"name", "default"}; list_microphones yields names.
    Everything downstream - the config, AudioMixer, the dropdown - wants a
    name.
    """
    return dev.get("name", "") if isinstance(dev, dict) else str(dev)


def cover(im, w, h):
    """Scale to fill w x h and crop the overflow off the middle.

    The plate is far wider than it is tall and the source is the monitor's own
    aspect, so resizing to fit squashed every face in the strip. Filling and
    losing the top and bottom keeps the frame looking like what was on screen.
    """
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * scale)),
                    max(h, round(im.height * scale))), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------

class Panel:

    def __init__(self, daemon=False):
        self.daemon = daemon
        self.cfg = nabd.load_config()
        self.start = dict(self.cfg)
        try:
            self.ffmpeg = nabd.find_ffmpeg()
        except RuntimeError:
            self.ffmpeg = None

        self.root = tk.Tk()
        self.root.title(f"{nabd.DISPLAY_NAME} Settings")
        T.set_scale(ctypes.windll.user32.GetDpiForWindow(self.root.winfo_id()))
        self.root.configure(bg=T.PANEL)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self._tool_window()
        self.root.resizable(False, False)
        self.root.bind("<Escape>", self._on_escape)
        # Focus leaving the panel is the event the dismiss is really waiting
        # for; the 100ms pump is only a backstop for focus changes Tk never
        # sees. _check_dismiss still decides - it fires for internal focus
        # moves too, and those belong to this process.
        self.root.bind("<FocusOut>", self._focus_left)

        self._results = queue.Queue()
        self._pump_id = None
        self._shown = False
        self._closing = False
        self._had_focus = False
        self._away_since = None
        self.auto_dismiss = True
        self.capturing = None
        self.dirty = set()
        self.clips = []
        self.page = 0
        self._thumbs = []
        self.speakers, self.mics, self.monitors = [], [], []
        self.free_bytes = 0
        self.per_nab = 0
        self._poster_labels = {}
        self.rows = []          # every Row, so tests can assert the grid
        self._scroll_to = 0.0
        self._gliding = False
        self._loaded = False    # real content has replaced the skeleton
        # Prewarm: a resident panel refreshes itself between opens, so an open
        # is nothing but the slide. See _prewarm.
        self._warm = False          # content current AND the still is up
        self._warm_at = 0.0
        self._sig = None            # what the current content was built from
        self._hydrating = False
        self._settled = False       # the hydrate worker has finished
        self._needs_hydrate = True
        self._sliding = False
        self._relayout_id = None
        self._block_y = [0] * M.N
        self._block_h = [1] * M.N
        self._block_w = T.px(T.PANEL_W) - 2 * T.px(T.PANEL_PAD)
        self._block_on = [False] * M.N
        self._alpha = None      # last values actually sent to the window
        self._x = None
        self._pending = False   # a hotkey press that arrived mid-animation
        self._clip_off = None
        self._shots = []        # one Label per block; see _capture_blocks
        self._shot_img = [None] * M.N
        self._shot_sig = None   # what the photographs were taken of
        self._shot_geom = None
        self._capturing = False    # photographing the hidden window right now
        self._dismiss_id = None    # save()'s deferred close, cancellable
        self._modal = False        # a dialog owns the panel; ignore the hotkey
        self._devices_at = None    # when the device lists were last enumerated
        self._poster_cache = {}    # (path, size) -> decoded poster
        self._capture_id = None
        self._armed = False     # window shown-but-invisible, ready to move
        self.groups = []        # eyebrow + card + rows, for search
        self._group = None
        # Geometry up front, so the still can be cut before the first open.
        rect = screen_rect()
        self._w, self._h = T.px(T.PANEL_W), rect.bottom - rect.top
        self._y, self._dock_x = rect.top, rect.left
        self._overlay = None
        self._avtest = None     # the A/V sync card, while it is running
        self._click = None      # the click, rendered once and kept

        self.root.withdraw()
        self._build()
        self._refresh_disk()
        self._estimate()
        self._draw_hero()          # needs the disk figures the estimate found
        # Deliberately nothing async here. Enumerating devices and building
        # posters costs CPU and the GIL, and doing it underneath the slide
        # dragged frames from 8ms to 14ms. The panel animates as a static
        # skeleton and hydrates once it has landed.
        if not daemon:
            self._present()

    def _row(self, card, label, index, **kw):
        """A Row, remembered. The control column's edges are the thing the
        whole layout rests on, so they are worth being able to assert - and
        search needs to know which rows belong to which group."""
        row = U.Row(card, label, index, **kw)
        self.rows.append(row)
        if self._group is not None:
            self._group["rows"].append(row)
        return row

    def _sep(self, card, index):
        bar = U.separator(card, index)
        if self._group is not None:
            self._group["seps"].append(bar)
        return bar

    def _make_group(self, parent, title, trailing=None):
        """An eyebrow and its card, recorded so search can unmount the pair."""
        eye = U.eyebrow(parent, title, trailing)
        eye.pack(fill="x", pady=(T.px(T.GROUP_GAP), T.px(10)))
        card = U.card(parent)
        card.pack(fill="x")
        self._group = {"title": title, "eyebrow": eye, "card": card,
                       "rows": [], "seps": [],
                       "eye_pack": {"fill": "x",
                                    "pady": (T.px(T.GROUP_GAP), T.px(10))},
                       "card_pack": {"fill": "x"}}
        self.groups.append(self._group)
        return card

    # -- shell --------------------------------------------------------------

    def _build(self):
        self.shell = tk.Frame(self.root, bg=T.PANEL)
        self.shell.pack(fill="both", expand=True)

        self._build_header()
        self._build_footer()

        # body between them; only the canvas expands
        holder = tk.Frame(self.shell, bg=T.PANEL)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, bg=T.PANEL, highlightthickness=0,
                                bd=0)
        self.canvas.pack(fill="both", expand=True)
        # Overlaid in the right gutter rather than packed beside the canvas:
        # packing it took its 10px out of the content, leaving a 16px margin on
        # the left and 26px on the right.
        self.vbar = U.Scrollbar(holder, self.canvas, bg=T.PANEL)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.body = tk.Frame(self.canvas, bg=T.PANEL)
        self._win = self.canvas.create_window(0, 0, window=self.body,
                                              anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)

        pad = T.px(T.PANEL_PAD)
        self.inner = inner = tk.Frame(self.body, bg=T.PANEL)
        inner.pack(fill="both", expand=True, padx=pad, pady=(pad, T.px(20)))

        # One clip frame per block, each holding its group at a FIXED width.
        # The clip absorbs the wipe; the group never re-lays-out, which is the
        # whole point of the two levels (PANEL-OPEN.md section 6). They are
        # placed, not packed, because place is what can be given a width.
        # Named apart from self.clips, which is the list of recent nabs.
        self._clip_frames, self._block_frames, self._covers = [], [], []
        self._shots = []
        builders = (self._build_hero, self._build_recent, self._build_capture,
                    self._build_hotkeys, self._build_video, self._build_audio)
        assert len(builders) == M.N, "block list is out of step with the motion"
        for name, build in zip(M.BLOCKS, builders):
            clip = tk.Frame(inner, bg=T.PANEL, highlightthickness=0, bd=0)
            block = tk.Frame(clip, bg=T.PANEL, highlightthickness=0, bd=0)
            block._name = name
            # The wipe's hard edge. Resizing the clip every frame is the obvious
            # way to do it and is what the spec describes, but a Tk frame
            # invalidates its whole client area when it is resized, so every
            # frame repainted all ~80 widgets in the block - 15 to 36 ms each,
            # four blocks in flight. Sliding an opaque cover off them instead
            # only ever invalidates the strip it uncovers, and reads
            # identically: a hard edge sweeping left to right.
            # A sibling of the clip, not a child of it: the slip moves the
            # clip, and a cover riding along inside would have to be moved
            # back again every frame.
            cover = tk.Frame(inner, bg=T.PANEL, highlightthickness=0, bd=0)
            # A photograph of the block, shown only while it is being dealt.
            # See _capture_blocks.
            shot = tk.Label(clip, bd=0, highlightthickness=0, bg=T.PANEL)
            self._clip_frames.append(clip)
            self._block_frames.append(block)
            self._covers.append(cover)
            self._shots.append(shot)
            build(block)
            # Any change of height inside a block restacks the column.
            block.bind("<Configure>", self._queue_relayout, add="+")
        inner.bind("<Configure>", self._queue_relayout, add="+")
        self._relayout_blocks()

    # -- block column -------------------------------------------------------

    def _queue_relayout(self, _e=None):
        """Coalesce the burst of Configures a rebuild produces into one pass.

        Never during the animation. Every frame of the wipe resizes a clip and
        moves a block, and each of those is itself a <Configure> - so this was
        re-stacking the whole column on every idle cycle while it ran, which is
        exactly the work section 6 says must not happen mid-motion.
        """
        if self._relayout_id or self._sliding:
            return
        try:
            self._relayout_id = self.root.after_idle(self._relayout_blocks)
        except tk.TclError:
            self._relayout_id = None

    def _relayout_blocks(self):
        """Stack the blocks and size the column they sit in.

        Placed children contribute nothing to a frame's requested size, so the
        scroll height has to be set here - it is what the canvas scrolls and
        what the scrollbar measures itself against.
        """
        self._relayout_id = None
        before = (self._block_w, list(self._block_y), list(self._block_h))
        try:
            width = self.inner.winfo_width()
            if width <= 1:
                width = T.px(T.PANEL_W) - 2 * T.px(T.PANEL_PAD)
            self._block_w = width
            y = 0
            for i, (clip, block, cover) in enumerate(
                    zip(self._clip_frames, self._block_frames, self._covers)):
                h = max(1, block.winfo_reqheight())
                self._block_y[i] = y
                self._block_h[i] = h
                # Neither ever changes size after this. The clip slips; the
                # cover sweeps across it. Moving whole windows means Windows
                # blits them, which is what keeps the frame cost down.
                clip.place(x=clip.winfo_x(), y=y, width=width, height=h)
                block.place(x=0, y=0, width=width, height=h)
                cover.place(x=width if self._block_on[i] else 0, y=y,
                            width=width, height=h)
                cover.lift()
                y += h
            self.inner.configure(height=max(1, y))
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            return
        # Nothing to invalidate here: _shots_valid compares the column
        # against the one the photographs were taken of, so a relayout that
        # lands back where it started - which is every prewarm - leaves them
        # usable. Clearing them here threw away every photograph on the
        # relayout _present runs immediately before raising them.

    def _on_scroll(self, first, last):
        """Show the scrollbar only when there is something to scroll."""
        self.vbar.set(first, last)
        if not self._gliding:      # keep the wheel target with the thumb
            try:
                self._scroll_to = self.canvas.canvasy(0)
            except tk.TclError:
                pass
        if self.vbar.needed():
            if not self.vbar.winfo_ismapped():
                self.vbar.place(relx=1.0, x=-T.px(U.Scrollbar.W), y=0,
                                relheight=1.0, anchor="nw")
        elif self.vbar.winfo_ismapped():
            self.vbar.place_forget()

    def _wheel(self, e):
        """Ease toward a target offset instead of jumping a line at a time.

        yview_scroll(n, "units") moves by one text line per notch, which on a
        panel made of cards lands as a stutter. This accumulates a pixel target
        and lets _glide close on it.
        """
        limit = self._scroll_limit()
        if limit <= 0:
            return
        self._scroll_to = max(0.0, min(float(limit),
                                       self._scroll_to
                                       - (e.delta / 120.0) * T.px(96)))
        if not self._gliding:
            self._gliding = True
            TIMER.begin()
            self._glide()

    # Seconds. Long enough that cycling the panel costs nothing, short enough
    # that a headset plugged in a moment ago is in the list by the time anyone
    # opens the panel to pick it. Nothing enumerates while the daemon is idle:
    # a hydrate only runs on a content change or after a close.
    DEVICE_TTL = 60.0

    def _hydrate(self):
        """Load the real content, once the animation is out of the way.

        One worker, staged cheapest-first rather than two racing threads:
        devices are a ~1.5s enumeration, clip metadata is a handful of stat
        calls, and posters are an ffmpeg run each. Run in parallel the slow one
        starves the others, so the panel filled in all at once and late.
        """
        if self._hydrating:
            return              # the prewarm is already on it
        self._hydrating = True
        threading.Thread(target=self._hydrate_worker, daemon=True).start()

    def _hydrate_worker(self):
        try:
            self._hydrate_work()
        finally:
            # The prewarm cycle waits on this. Losing it to an exception would
            # leave the daemon believing it was still loading, for good.
            self._results.put(("done", None))

    def _hydrate_work(self):
        # The prewarm runs after EVERY close, and this used to re-enumerate the
        # audio devices each time - list_microphones spawns ffmpeg, so closing
        # the panel cost a subprocess and about 1.5s of a daemon that is meant
        # to be idle. PANEL-OPEN.md section 6 says cache these and refresh on a
        # slow timer; devices change when hardware is plugged in, not when a
        # panel closes.
        now = time.perf_counter()
        fresh = (self._devices_at is not None
                 and now - self._devices_at < self.DEVICE_TTL)
        if fresh and self.speakers:
            spk, mics, mons = self.speakers, self.mics, self.monitors
        else:
            try:
                spk = nabd.list_speakers()
                mics = nabd.list_microphones(self.ffmpeg)
                mons = nabd.list_monitors()
                self._devices_at = now
            except Exception:
                spk, mics, mons = [], [], []
        self._results.put(("devices", (spk, mics, mons)))


        try:
            found = nabd.recent_clips(self.cfg["output_dir"], MAX_RECENT)
        except Exception:
            found = []
        meta = []
        for c in found:
            try:
                st = Path(c).stat()
            except OSError:
                continue
            when = datetime.datetime.fromtimestamp(st.st_mtime)
            meta.append({"path": str(c), "thumb": None,
                         "time": when.strftime("%H:%M:%S"),
                         "date": when.strftime("%Y-%m-%d"),
                         "size": st.st_size})
        self._results.put(("clips", meta))

        # Slowest last, and one at a time, so each card fills in as it is ready
        # instead of the strip waiting on the whole batch.
        cache = nabd.DATA_DIR / "posters"
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        for m in meta:
            # Decoded posters are kept by path and size: the same 15 nabs were
            # re-read and LANCZOS-resized on every prewarm, which is every
            # close, for a strip that had not changed.
            key = (m["path"], m["size"])
            img = self._poster_cache.get(key)
            if img is None:
                img = self._poster(Path(m["path"]), cache)
                if img is not None:
                    if len(self._poster_cache) > 3 * MAX_RECENT:
                        self._poster_cache.clear()
                    self._poster_cache[key] = img
            if img is not None:
                self._results.put(("poster", (m["path"], img)))

    def _poster(self, clip, cache):
        w, _gaps = self._tile_metrics()
        h = T.px(T.THUMB_POSTER_H)
        dest = cache / (clip.stem + ".jpg")
        try:
            im = None
            if dest.exists():
                im = Image.open(dest).convert("RGB")
                if im.width < w or im.height < h:
                    im = None       # cached before the strip got this wide
            if im is None:
                nabd.clip_thumbnail(clip, dest, max(w, T.px(T.THUMB_SRC_W)),
                                    self.ffmpeg)
                if not dest.exists():
                    return None
                im = Image.open(dest).convert("RGB")
            return cover(im, w, h)
        except Exception:
            return None

    def _apply_poster(self, path, img):
        """Swap one card's plate in place, rather than rebuilding the strip."""
        for c in self.clips:
            if c["path"] == path:
                c["thumb"] = img
                break
        label = self._poster_labels.get(path)
        if label is not None:
            try:
                P.photo(label, img)
                label.configure(image=label._img)
            except tk.TclError:
                pass

    def _scroll_limit(self):
        return max(0, self.body.winfo_reqheight() - self.canvas.winfo_height())

    def _glide(self):
        """One step of the eased scroll. Stops once it is within a pixel."""
        total = max(1, self.body.winfo_reqheight())
        try:
            cur = self.canvas.canvasy(0)
            diff = self._scroll_to - cur
            if abs(diff) < 1.0:
                self.canvas.yview_moveto(self._scroll_to / total)
                self._gliding = False
                TIMER.end()
                return
            self.canvas.yview_moveto((cur + diff * 0.30) / total)
            self.root.after(10, self._glide)
        except tk.TclError:
            self._gliding = False
            TIMER.end()

    def _build_header(self):
        head = tk.Frame(self.shell, bg="#0E0E11")
        head.pack(fill="x", side="top")
        tk.Frame(self.shell, bg=T.LINE, height=T.px(1)).pack(fill="x",
                                                             side="top")
        outer = tk.Frame(head, bg="#0E0E11")
        outer.pack(fill="x", padx=T.px(16), pady=(T.px(14), T.px(13)))
        inner = tk.Frame(outer, bg="#0E0E11")
        inner.pack(fill="x")

        # The tile + wordmark is artwork, rendered by Pillow: the Tk canvas has
        # no antialiasing and the mark's curves show it at this size.
        lock = tk.Label(inner, bg="#0E0E11", bd=0)
        P.photo(lock, brand.tile_lockup_image(T.px(T.LOGO_TILE),
                                              field=T.PURPLE, ring=T.TEXT,
                                              word=T.TEXT))
        lock.configure(image=lock._img)
        lock.pack(side="left")
        tk.Label(inner, text="Settings", bg="#0E0E11", fg=T.TEXT_FAINT,
                 font=T.font("value")).pack(side="left", padx=(T.px(10), 0))

        close = tk.Label(inner, text="\u2715", bg="#0E0E11", fg=T.TEXT_FAINT,
                         font=(T.FONT_UI, -T.px(17)), cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda _e: self.dismiss())
        close.bind("<Enter>", lambda _e: close.configure(fg=T.TEXT))
        close.bind("<Leave>", lambda _e: close.configure(T.TEXT_FAINT))


    def _build_footer(self):
        tk.Frame(self.shell, bg=T.LINE, height=T.px(1)).pack(fill="x",
                                                             side="bottom")
        foot = tk.Frame(self.shell, bg="#0E0E11", height=T.px(T.FOOTER_H))
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        self.dirty_label = tk.Label(foot, text="No changes", bg="#0E0E11",
                                    fg=T.TEXT_FAINT, font=T.font("mono_sm"))
        self.dirty_label.pack(side="left", padx=T.px(16))
        self.save_btn = U.Button(foot, "Save", self.save, variant="primary",
                                 bg="#0E0E11", width=78)
        self.save_btn.pack(side="right", padx=(0, T.px(16)))
        self.cancel_btn = U.Button(foot, "Close", self.dismiss, variant="quiet",
                                   bg="#0E0E11")
        self.cancel_btn.pack(side="right", padx=(0, T.px(9)))
        self.save_btn.set_enabled(False)

    # -- hero ---------------------------------------------------------------

    def _build_hero(self, parent):
        """Drawn on a Canvas rather than built from widgets: the card has a
        gradient, and a Tk widget on top of it would need an opaque background
        that the gradient does not have."""
        # 16 top + 19 status + 14 + 34 bar + 9 + 13 ends + 14 + 34 keycap
        # + 17 bottom = 170.
        self.hero_h = T.px(170)
        self.hero = tk.Canvas(parent, height=self.hero_h, bg=T.PANEL,
                              highlightthickness=0, bd=0)
        self._hero_pack = {"fill": "x"}
        self.hero.pack(**self._hero_pack)
        # Width comes from the layout, not from the panel constant: the
        # scrollbar takes 10px when present, and a hardcoded width left the
        # card's right border and corners outside the viewport.
        self.hero.bind("<Configure>", lambda _e: self._draw_hero())

    def _draw_hero(self):
        c = self.hero
        w, h = c.winfo_width(), self.hero_h
        if w < T.px(100):
            return          # not laid out yet; <Configure> will call back
        c.delete("all")
        P.photo(c, P.hero_bg(w, h, T.PANEL), "_hero")
        c.create_image(0, 0, image=c._hero, anchor="nw")

        pad = T.px(17)
        mins = max(1, int(self.cfg["clip_seconds"]) // 60)
        # status row, centred on the 19px line that starts at 16px padding
        cy = T.px(26)
        c.create_oval(pad, cy - T.px(4), pad + T.px(7), cy + T.px(3),
                      fill=T.PURPLE_LIGHT, outline="")
        c.create_text(pad + T.px(16), cy, anchor="w", text="Buffering",
                      fill=T.TEXT, font=T.font("label", T.FONT_UI_MEDIUM))
        c.create_text(pad + T.px(16)
                      + U.text_width(T.font("label", T.FONT_UI_MEDIUM),
                                     "Buffering") + T.px(9), cy, anchor="w",
                      text=f"last {mins} minute" + ("s" if mins != 1 else ""),
                      fill=T.TEXT_MUTED, font=T.font("mono_sm"))
        c.create_text(w - pad, cy, anchor="e",
                      text=f"{human_bytes(self.per_nab)} \u00b7 "
                           f"{human_bytes(self.free_bytes)} free",
                      fill=T.TEXT_MUTED, font=T.font("mono_sm"))

        # timeline. Deliberately not the ring mark: the brand guidelines forbid
        # reusing the logo as a progress indicator, and a buffer is exactly the
        # temptation they had in mind.
        ty, th = T.px(49), T.px(34)
        P.photo(c, P.timeline(w - pad * 2, th), "_timeline")
        c.create_image(pad, ty, image=c._timeline, anchor="nw")

        ey = ty + th + T.px(16)               # 9px gap, then half the line
        c.create_text(pad, ey, anchor="w",
                      text=f"\u2212{mins}:00", fill=T.TEXT_FAINT,
                      font=T.font("mono_xs"))
        c.create_text(w - pad, ey, anchor="e", text="NOW",
                      fill=T.PURPLE_LIGHT, font=T.font("mono_xs"))

        # hotkey + hint
        hy = T.px(119)
        spec = self.cfg.get("hotkey") or "\u2014"
        label = self._pretty(spec)
        kw = U.text_width(T.font("mono"), label) + T.px(32)
        kh = T.px(T.KBD_H)
        P.photo(c, P.rounded_rect(kw, kh, T.px(T.R_CONTROL), T.RAISED,
                                  T.LINE_STRONG, T.px(1), T.SURFACE), "_kbd")
        c.create_image(pad, hy, image=c._kbd, anchor="nw")
        c.create_text(pad + kw / 2, hy + kh / 2, text=label, fill=T.TEXT,
                      font=T.font("mono"))
        c.create_text(pad + kw + T.px(13), hy + kh / 2, anchor="w",
                      text="Press any time to keep what just happened.",
                      fill=T.TEXT_MUTED, font=T.font("helper"))

    # -- recent -------------------------------------------------------------

    def _build_recent(self, parent):
        def trailing(head):
                # Counts and totals that follow the folder, not the layout.
            self.recent_count = tk.Label(head, text="", bg=T.PANEL,
                                         fg=T.TEXT_FAINT,
                                         font=T.font("mono_xs"))
            self.recent_count._dynamic = True
            self.recent_count.pack(side="left", padx=(0, T.px(10)))
            for glyph, delta in (("\u2039", -1), ("\u203a", 1)):
                b = tk.Label(head, text=glyph, bg=T.PANEL, fg=T.TEXT_FAINT,
                             font=(T.FONT_UI, -T.px(15)), cursor="hand2")
                b.pack(side="left", padx=T.px(3))
                b.bind("<Button-1>", lambda _e, d=delta: self._page(d))

        self.recent_head = U.eyebrow(parent, "recent nabs", trailing)
        self._recent_head_pack = {"fill": "x",
                                  "pady": (T.px(T.GROUP_GAP), T.px(10))}
        self.recent_head.pack(**self._recent_head_pack)
        # Drawn as tile blocks in the still; its own labels are nab metadata.
        self.thumb_row = tk.Frame(parent, bg=T.PANEL)
        self.thumb_row._dynamic = True
        self._thumb_pack = {"fill": "x"}
        self.thumb_row.pack(**self._thumb_pack)
        bar = self.recent_bar = tk.Frame(parent, bg=T.PANEL)
        self._recent_bar_pack = {"fill": "x", "pady": (T.px(10), 0)}
        bar.pack(**self._recent_bar_pack)
        U.IconButton(bar, "Open nabs folder",
                     P.folder_icon(T.px(15), T.TEXT, T.RAISED),
                     self._open_folder, bg=T.PANEL).pack(side="left")
        # Draw the placeholder strip now, so the panel animates at its final
        # height and hydrating swaps cards rather than inserting them.
        self._render_clips()

    def _tile_metrics(self):
        """Three tiles and the gaps between them, flush with the cards.

        Derived rather than a fixed width: a constant rounds independently of
        the panel's own padding at fractional DPI and left dead space against
        the right gutter. Any remainder goes into the gaps, so all three
        posters stay one size and the cache holds across pages.
        """
        total = T.px(T.PANEL_W) - 2 * T.px(T.PANEL_PAD)
        gap = T.px(T.THUMB_GAP)
        w = (total - gap * (PER_PAGE - 1)) // PER_PAGE
        spare = total - w * PER_PAGE - gap * (PER_PAGE - 1)
        gaps = [gap + (1 if i < spare else 0) for i in range(PER_PAGE - 1)]
        return w, gaps + [0]

    def _page(self, delta):
        pages = max(1, (len(self.clips) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(pages - 1, self.page + delta))
        self._render_clips()

    def _render_clips(self):
        for w in self.thumb_row.winfo_children():
            w.destroy()
        self._thumbs = []
        self._poster_labels = {}
        if not self._loaded:
            # Placeholder cards at the real metrics, so hydrating does not
            # shift anything below them.
            w, gaps = self._tile_metrics()
            for i in range(PER_PAGE):
                self._thumb(self.thumb_row, None, i, w, gaps[i])
            if hasattr(self, "recent_count"):
                self.recent_count.configure(text="")
            return
        if not self.clips:
            empty = U.RoundedFrame(self.thumb_row, fill=T.PANEL,
                                   outline=T.LINE_STRONG, bg=T.PANEL)
            empty.pack(fill="x")
            tk.Label(empty, text="Your nabs will show up here.", bg=T.PANEL,
                     fg=T.TEXT_MUTED, font=T.font("label")).pack(
                pady=(T.px(26), T.px(11)))
            line = tk.Frame(empty, bg=T.PANEL)
            line.pack(pady=(0, T.px(26)))
            U.HotkeyField(line, self._pretty(self.cfg.get("hotkey", "")),
                          bg=T.PANEL).pack(side="left")
            tk.Label(line, text="saves the last five minutes.", bg=T.PANEL,
                     fg=T.TEXT_MUTED, font=T.font("value")).pack(
                side="left", padx=(T.px(10), 0))
            if hasattr(self, "recent_count"):
                self.recent_count.configure(text="")
            return

        start = self.page * PER_PAGE
        shown = self.clips[start:start + PER_PAGE]
        total = sum(c.get("size", 0) for c in self.clips)
        self.recent_count.configure(
            text=f"{len(self.clips)} \u00b7 {human_bytes(total)}")
        w, gaps = self._tile_metrics()
        for i, clip in enumerate(shown):
            self._thumb(self.thumb_row, clip, i, w, gaps[i])

    def _thumb(self, parent, clip, i, w, gap):
        """A nab card, or a blank one at identical metrics when clip is None."""
        skeleton = clip is None
        if skeleton:
            clip = {"time": "", "date": "", "size": None, "thumb": None,
                    "path": None}
        card = U.RoundedFrame(parent, radius=8, fill=T.SURFACE, outline=T.LINE,
                              bg=T.PANEL)
        # No trailing gap on the last tile: padding every one of them is what
        # stopped the strip short of the cards' right edge.
        card.pack(side="left", padx=(0, gap))
        poster = tk.Label(card, bd=0, highlightthickness=0, bg="#20202A",
                          cursor="hand2")
        img = clip.get("thumb")
        if img is not None and img.width != w:
            img = cover(img, w, T.px(T.THUMB_POSTER_H))
        if img is None:      # no poster yet: a play glyph on an empty plate
            plate = (0x1B, 0x1B, 0x21) if skeleton else (0x20, 0x20, 0x2A)
            img = Image.new("RGB", (w, T.px(T.THUMB_POSTER_H)), plate)
            if not skeleton:
                glyph = P.play_glyph(T.px(22), T.TEXT, "#20202A", 0.4)
                img.paste(glyph, ((img.width - glyph.width) // 2,
                                  (img.height - glyph.height) // 2))
        P.photo(poster, img)
        poster.configure(image=poster._img)
        poster.pack()
        # The poster reaches the card's top corners, so those two arcs have to
        # be cut from the frame rather than from the card colour - otherwise
        # each nab loses a square bite out of its top corners.
        r = card.radius
        if img.width > 2 * r and img.height > r:
            card.set_corner_patch(0, img.crop((0, 0, r, r)))
            card.set_corner_patch(1, img.crop((img.width - r, 0,
                                               img.width, r)))
        if not skeleton and clip.get("path"):
            self._poster_labels[clip["path"]] = poster
        meta = tk.Frame(card, bg=T.SURFACE)
        meta.pack(fill="x", padx=T.px(10), pady=(T.px(8), T.px(9)))
        tk.Label(meta, text=clip["time"], bg=T.SURFACE, fg=T.TEXT,
                 font=T.font("mono_xs"), anchor="w").pack(fill="x")
        sub = tk.Frame(meta, bg=T.SURFACE)
        sub.pack(fill="x", pady=(T.px(3), 0))
        tk.Label(sub, text=clip["date"], bg=T.SURFACE, fg=T.TEXT_FAINT,
                 font=T.font("mono_xs")).pack(side="left")
        tk.Label(sub, text="" if skeleton else human_bytes(clip["size"]),
                 bg=T.SURFACE, font=T.font("mono_xs"),
                 fg=T.TEXT_FAINT).pack(side="right")
        if not skeleton:
            for w in (card, poster, meta):
                w.bind("<Button-1>", lambda _e, p=clip["path"]: self._open(p))

    # -- capture ------------------------------------------------------------

    def _build_capture(self, parent):
        card = self._make_group(parent, "capture")
        r = 0

        row = self._row(card, "Nab length", r, first=True)
        lengths = [60, 180, 300]
        try:
            idx = lengths.index(int(self.cfg["clip_seconds"]))
        except ValueError:
            idx = 2
        self.length = U.Segmented(row.line, ["1 min", "3 min", "5 min"], idx,
                                  command=lambda _i: self._on_length())
        self.length.pack(side="right")
        self._lengths = lengths
        sub = row.sub()
        self.meter = U.Meter(sub, T.CONTROL_COL, 0.0, "ok")
        self.meter.pack(fill="x")
        figs = tk.Frame(sub, bg=T.SURFACE)
        figs.pack(fill="x", pady=(T.px(7), 0))
        self.size_label = tk.Label(figs, text="", bg=T.SURFACE,
                                   fg=T.TEXT_MUTED, font=T.font("mono_xs"))
        self.size_label._dynamic = True
        self.size_label.pack(side="left")
        self.free_label = tk.Label(figs, text="", bg=T.SURFACE,
                                   fg=T.TEXT_FAINT, font=T.font("mono_xs"))
        self.free_label._dynamic = True
        self.free_label.pack(side="right")
        self.disk_warn = None
        self.disk_row = row

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Buffer", r)
        self.reset_toggle = U.Toggle(row.line,
                                     bool(self.cfg.get("reset_after_clip")),
                                     command=lambda _v: self._on_reset())
        self.reset_toggle.pack(side="right")
        tk.Label(row.line, text="Start fresh after each nab", bg=T.SURFACE,
                 fg=T.TEXT, font=T.font("value")).pack(side="right",
                                                       padx=(0, T.px(9)))
        self.reset_hint = row.helper("")
        self.reset_hint._dynamic = True
        self._on_reset(update_only=True)

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Nab sound", r)
        # Preview, because nobody wants to nab something to audition a sound.
        U.Button(row.line, "Preview", self._preview_sound, variant="ghost",
                 small=True).pack(side="right")
        # No width: a Select asked for the full control column, next to a
        # button, makes the row 426px and drags that row's left edge out of
        # line with every other one. Packed to fill what the button leaves,
        # the same way the folder field is.
        self.sound = U.Select(
            row.line, list(SOUND_LABELS),
            self._sound_index(self.cfg.get("capture_sound")),
            command=self._on_sound)
        self.sound.pack(side="right", fill="x", expand=True,
                        padx=(0, T.px(9)))
        self.sound_help = row.helper("")
        self.sound_help._dynamic = True
        self._show_sound_file()

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Save nabs to", r, last=True)
        U.Button(row.line, "Browse", self._browse,
                 variant="ghost").pack(side="right")
        # width:100% in the reference: it takes the column minus its button.
        # Hardcoding a width left ~30px of dead space to its left.
        self.folder = U.Field(row.line, self.cfg["output_dir"])
        self.folder.pack(side="right", fill="x", expand=True,
                         padx=(0, T.px(9)))

    def _on_length(self):
        self._mark("clip_seconds", self._lengths[self.length.current()])
        self._estimate()
        self._draw_hero()

    @staticmethod
    def _sound_index(value):
        v = (value or "").strip()
        if not v or v.lower() == "off":
            return 0
        return 2 if v.lower().endswith(".wav") else 1

    def _on_sound(self, i):
        if i == 0:
            self._mark("capture_sound", "off")
        elif i == 1:
            self._mark("capture_sound", "pip")
        else:
            self._pick_sound()
        self._show_sound_file()

    def _pick_sound(self):
        """A .wav of the user's own - what resolve() already accepts."""
        was = self.cfg.get("capture_sound", "pip")
        # Same guard as _browse: the dialog runs a nested loop, so without
        # _modal the hotkey can close the panel out from under it.
        self.auto_dismiss = False
        self._modal = True
        try:
            path = filedialog.askopenfilename(
                parent=self.root, title="Choose a nab sound",
                filetypes=[("WAV audio", "*.wav")])
        finally:
            self._modal = False
            self.root.after(400, lambda: setattr(self, "auto_dismiss", True))
        if path and path.lower().endswith(".wav"):
            self._mark("capture_sound", os.path.normpath(path))
            return
        # Cancelled. set_values, not _choose - _choose would call straight
        # back into here and reopen the dialog.
        self.sound.set_values(self.sound.values, self._sound_index(was))

    def _show_sound_file(self):
        v = self.cfg.get("capture_sound", "")
        self.sound_help.set(os.path.basename(v)
                            if isinstance(v, str) and v.lower().endswith(".wav")
                            else "")

    def _preview_sound(self):
        choice = self.cfg.get("capture_sound", "pip")
        if not choice or choice == "off":
            return
        if not nabd_sound.play(choice):
            # play() swallows everything, which is right in the banner and
            # wrong here: this is the one place the user is asking whether the
            # sound works.
            self.sound_help.set("That file could not be played.", T.WARN)
            self.root.after(4000, self._show_sound_file)

    def _on_reset(self, update_only=False):
        on = self.reset_toggle.get()
        self.reset_hint.set(("Each nab picks up where the last ended, so nabs never "
                  "overlap.") if on else
                 ("Always keeps the most recent footage, so nabs taken close "
                  "together overlap."))
        if not update_only:
            self._mark("reset_after_clip", on)

    # -- video --------------------------------------------------------------

    def _build_video(self, parent):
        card = self._make_group(parent, "video")
        r = 0

        row = self._row(card, "Monitor", r, first=True)
        U.Button(row.line, "Identify", self._identify,
                 variant="ghost").pack(side="right")
        self.monitor = U.Select(row.line, ["Loading\u2026"], 0,
                                command=lambda _i: self._on_monitor())
        self.monitor.pack(side="right", fill="x", expand=True,
                          padx=(0, T.px(9)))

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Quality", r)
        cq = int(self.cfg.get("cq", 23))
        qidx = next((i for i, q in enumerate(QUALITY) if q[1] == cq), 1)
        self.quality = U.Select(row.line, self._quality_labels(), qidx,
                                command=lambda _i: self._on_quality(),
                                width=T.CONTROL_COL)
        self.quality.pack(side="right")

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Frame rate", r, last=True)
        self.fps = U.Select(row.line, ["60 fps"], 0,
                            command=lambda _i: self._on_fps(),
                            width=T.CONTROL_COL)
        self.fps.pack(side="right")
        self.fps_hint = row.helper("")
        self.fps_hint._dynamic = True
        self.fps_values = [60]

    def _quality_labels(self):
        """Preset names with what each one costs on disk.

        Quality is the encoder's CQ, not a scale factor: every preset records
        at the display's native resolution. Putting that resolution beside each
        name therefore printed the same figure four times and read as though
        the preset set the picture size, which is the one thing it does not do.
        What it changes is the byte rate, so that is what it says.
        """
        i = self.monitor.current() if self.monitors else -1
        if not (0 <= i < len(self.monitors)):
            return [name for name, _ in QUALITY]
        mon = self.monitors[i]
        fps = self.fps_values[self.fps.current()] if self.fps_values else 60
        rates = [modelled_bytes_per_sec(mon["width"], mon["height"], fps, cq)
                 for _name, cq in QUALITY]
        # The ring buffer knows the true rate for the preset actually running.
        # Scale the others by it so the figures track the encoder that won the
        # probe and the footage being captured, not a table of constants.
        measured = measured_bytes_per_sec()
        cur = int(self.cfg.get("cq", 23))
        base = next((r for (_n, cq), r in zip(QUALITY, rates) if cq == cur),
                    None)
        if measured and base:
            rates = [r * measured / base for r in rates]
        return [f"{name} (~{human_bytes(r * 60)}/min)"
                for (name, _cq), r in zip(QUALITY, rates)]

    def _refresh_quality_labels(self):
        if hasattr(self, "quality"):
            self.quality.set_values(self._quality_labels(),
                                    self.quality.current())

    def _fps_options(self, hz):
        """Derived from the display, not fixed: you cannot capture more
        distinct frames than it presents, and a rate that is not an even
        division paces unevenly."""
        cands = {30, 60}
        if hz:
            for n in (1, 2, 3):
                if hz % n == 0:
                    cands.add(hz // n)
        return sorted(c for c in cands if 24 <= c <= (hz or 60))

    def _on_monitor(self):
        i = self.monitor.current()
        self._mark("monitor", i)
        self._rebuild_fps()
        self._refresh_quality_labels()
        self._estimate()

    def _rebuild_fps(self):
        i = self.monitor.current()
        hz = 0
        if 0 <= i < len(self.monitors):
            hz = nabd.monitor_refresh(self.monitors[i]["device"])
        opts = self._fps_options(hz)
        self.fps_values = opts
        want = int(self.cfg.get("fps", 60))
        if want > (opts[-1] if opts else 60):
            want = opts[-1]
            self._mark("fps", want)
            self.fps_hint.set(f"Lowered to {want} fps \u2014 this display runs at "
                     f"{hz} Hz.", T.PURPLE_LIGHT)
        idx = opts.index(want) if want in opts else len(opts) - 1
        self.fps.set_values([f"{o} fps" for o in opts], idx)
        self._fps_note(hz)

    def _fps_note(self, hz):
        if not hz or not self.fps_values:
            return
        fps = self.fps_values[self.fps.current()]
        if hz % fps:
            even = max((o for o in self.fps_values if hz % o == 0), default=None)
            tail = f" {even} fps samples evenly." if even else ""
            self.fps_hint.set(f"This display runs at {hz} Hz. {fps} fps is not an even "
                     f"division, so motion may judder slightly.{tail}",
                T.TEXT_FAINT)
        else:
            self.fps_hint.set(f"This display runs at {hz} Hz. {fps} fps divides evenly.",
                T.TEXT_FAINT)

    def _on_fps(self):
        self._mark("fps", self.fps_values[self.fps.current()])
        i = self.monitor.current()
        hz = nabd.monitor_refresh(self.monitors[i]["device"]) if self.monitors else 0
        self._fps_note(hz)
        self._refresh_quality_labels()   # the rates are per-frame
        self._estimate()

    def _on_quality(self):
        self._mark("cq", QUALITY[self.quality.current()][1])
        self._estimate()
        self._refresh_quality_labels()   # rescale against the new preset

    # -- audio --------------------------------------------------------------

    def _build_audio(self, parent):
        card = self._make_group(parent, "audio")
        r = 0

        row = self._row(card, "Speakers", r, first=True)
        self.spk = U.Select(row.line, ["Loading\u2026"], 0,
                            command=lambda _i: self._mark(
                                "speaker_device", self._spk_value()),
                            width=T.CONTROL_COL)
        self.spk.pack(side="right")
        sub = row.sub()
        self.spk_read = self._readout(sub, "100%")
        self.spk_vol = U.Slider(
            sub, 0, 100, int(float(self.cfg.get("desktop_volume", 1)) * 100),
            command=lambda v: self._on_vol("desktop_volume", v, self.spk_read),
            width=268)
        self.spk_vol.pack(side="right", fill="x", expand=True)

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Microphone", r)
        self.mic = U.Select(row.line, ["Loading\u2026"], 0,
                            command=lambda _i: self._mark(
                                "mic_device", self._mic_value()),
                            width=T.CONTROL_COL)
        self.mic.pack(side="right")
        sub = row.sub()
        self.mic_read = self._readout(sub, "100%")
        self.mic_vol = U.Slider(
            sub, 0, 100, int(float(self.cfg.get("mic_volume", 1)) * 100),
            command=lambda v: self._on_vol("mic_volume", v, self.mic_read),
            width=268)
        self.mic_vol.pack(side="right", fill="x", expand=True)

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "A/V sync", r, last=True)
        U.Button(row.line, "Test", self._av_test, variant="ghost",
                 small=True).pack(side="right")
        self.sync_read = self._readout(row.line, "", padx=(T.px(9), T.px(9)))
        self.sync = U.Slider(row.line, -500, 500,
                             int(self.cfg.get("audio_offset_ms", 0)), step=10,
                             command=self._on_sync, width=190)
        self.sync.pack(side="right", fill="x", expand=True)
        self._on_sync(self.sync.get(), quiet=True)
        self.sync_help = row.helper(AV_HELP)

    @staticmethod
    def _readout(parent, text, padx=(0, 0)):
        """Mono value in a fixed 62px column, so dragging a slider next to it
        cannot shift the row."""
        # pack_propagate(False) pins both axes, so the height has to be given
        # too or the label is clipped to nothing.
        box = tk.Frame(parent, bg=T.SURFACE, width=T.px(62), height=T.px(18))
        box._dynamic = True         # reads a setting; kept out of the still
        box.pack(side="right", padx=padx)
        box.pack_propagate(False)
        lbl = tk.Label(box, text=text, bg=T.SURFACE, fg=T.TEXT_MUTED,
                       font=T.font("mono_sm"), anchor="e")
        lbl.pack(fill="both", expand=True)
        return lbl

    def _on_vol(self, key, value, readout):
        readout.configure(text=f"{value}%")
        self._mark(key, round(value / 100.0, 2))

    def _on_sync(self, value, quiet=False):
        self.sync_read.configure(text=f"{value} ms".replace("-", "\u2212"))
        if not quiet:
            self._mark("audio_offset_ms", value)

    def _spk_value(self):
        i = self.spk.current()
        if i == 0 or not (0 < i <= len(self.speakers)):
            return ""
        return device_name(self.speakers[i - 1])

    def _mic_value(self):
        i = self.mic.current()
        return "" if i == 0 else self.mics[i - 1]

    # -- hotkeys ------------------------------------------------------------

    def _build_hotkeys(self, parent):
        card = self._make_group(parent, "hotkeys")
        r = 0
        row = self._row(card, "Save nab", r, first=True)
        self.hk_nab = U.HotkeyField(row.line,
                                    self._pretty(self.cfg.get("hotkey", "")),
                                    command=lambda f: self._capture("hotkey", f),
                                    width=110)
        self.hk_nab.pack(side="right")
        self.hk_nab_note = row.helper("")
        self.hk_nab_note._dynamic = True

        r += 1
        self._sep(card, r)
        r += 1
        row = self._row(card, "Open Nab'd", r, last=True)
        self.hk_open = U.HotkeyField(
            row.line, self._pretty(self.cfg.get("open_hotkey", "")),
            command=lambda f: self._capture("open_hotkey", f), width=150)
        self.hk_open.pack(side="right")
        self.hk_open_note = row.helper(
            "Click a field, then press the combination you want. Esc cancels.")

    def _field_for(self, key):
        return ((self.hk_nab, self.hk_nab_note) if key == "hotkey"
                else (self.hk_open, self.hk_open_note))

    def _hold_hotkeys(self, on):
        """Ask the app to let go of the nab keys while we listen for one.

        RegisterHotKey is exclusive: while the app holds a combo, pressing it
        goes to the app and nowhere else - including this window. So the key
        you were trying to bind took a nab instead of being read, and there
        was no way to type it in at all.

        Only saving stops. The buffer goes on recording throughout, so nothing
        is lost while the key is being set.

        The note carries a deadline: if this panel dies mid-capture the app
        takes its keys back on its own rather than staying deaf.
        """
        try:
            if on:
                nabd.HOTKEY_HOLD.write_text("%.3f" % (time.time() + 90),
                                            encoding="utf-8")
            else:
                nabd.HOTKEY_HOLD.unlink(missing_ok=True)
        except OSError:
            pass

    def _capture(self, key, field):
        if self.capturing:
            self._cancel_capture()
        self.capturing = key
        self._hold_hotkeys(True)
        field.mark("capturing")
        field.set_text("Press keys\u2026")
        self.root.bind("<KeyPress>", self._on_key)
        self.root.focus_force()
        self._stuck = self.root.after(3500, lambda: self._capture_stuck(key))

    def _capture_stuck(self, key):
        if self.capturing != key:
            return
        field, note = self._field_for(key)
        note.set("That key never reached Nab'd - another app has "
                            "already claimed it system-wide. Try another.",
                       T.WARN)

    def _clear_stuck(self):
        job, self._stuck = getattr(self, "_stuck", None), None
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _cancel_capture(self):
        key, self.capturing = self.capturing, None
        self._hold_hotkeys(False)
        self._clear_stuck()
        self.root.unbind("<KeyPress>")
        if key:
            field, _ = self._field_for(key)
            field.mark("rest")
            field.set_text(self._pretty(self.cfg.get(key, "")))

    def _focus_left(self, _event=None):
        """Check as soon as Tk notices, not on the next poll."""
        try:
            self.root.after_idle(self._check_dismiss)
        except tk.TclError:
            pass

    def _on_escape(self, _event=None):
        """Esc cancels a hotkey capture, and otherwise closes the panel.

        Both used to be bound to the root: a plain <Escape> and the <KeyPress>
        that _capture installs. Tk fires only the most specific binding on a
        tag, so the capture branch was unreachable and the helper line under
        the field - "Esc cancels." - was a lie; Escape closed the panel with
        the capture still live.
        """
        if self.capturing:
            self._cancel_capture()
        else:
            self.dismiss()

    def _on_key(self, event):
        if not self.capturing or event.keysym in MOD_KEYSYMS:
            return
        mods = []
        if event.state & STATE_CTRL:
            mods.append("ctrl")
        if event.state & STATE_ALT:
            mods.append("alt")
        if event.state & STATE_SHIFT:
            mods.append("shift")
        key = event.keysym
        if len(key) == 1 and key.isalnum():
            key = key.lower()
        elif len(key) > 1 and key[0] in "Ff" and key[1:].isdigit():
            key = key.lower()
        else:
            key = NAMED_KEYS.get(key)
            if not key:
                return
        spec = "+".join(mods + [key])
        try:
            nabd.parse_hotkey(spec)
        except ValueError:
            return

        which, self.capturing = self.capturing, None
        # The key landed, so we are done listening - give the nab keys back
        # before anything else. This path does not go through
        # _cancel_capture, so it has to let go on its own.
        self._hold_hotkeys(False)
        self._clear_stuck()
        self.root.unbind("<KeyPress>")
        field, note = self._field_for(which)
        other = "open_hotkey" if which == "hotkey" else "hotkey"
        if spec == self.cfg.get(other):
            field.mark("error")
            field.set_text(self._pretty(spec))
            note.set(f"Already bound to "
                     f"{'Open Nab' if other != 'hotkey' else 'Save nab'}. Pick "
                     f"another combination, or Esc to keep "
                     f"{self._pretty(self.cfg.get(which, ''))}.", T.DANGER)
            self.root.after(2500, lambda: self._cancel_capture_visual(which))
            return
        field.mark("rest")
        field.set_text(self._pretty(spec))
        self._mark(which, spec)
        note.set("" if which == "hotkey" else
                 "Click a field, then press the combination you want. Esc "
                 "cancels.",
            T.TEXT_FAINT)
        if not nabd.hotkey_available(spec):
            note.set("Another app already holds this combination. "
                                "Nab'd will keep asking for it in the "
                                "background.", T.WARN)

    def _cancel_capture_visual(self, which):
        field, note = self._field_for(which)
        field.mark("rest")
        field.set_text(self._pretty(self.cfg.get(which, "")))
        note.set("", T.TEXT_FAINT)

    @staticmethod
    def _pretty(spec):
        if not spec:
            return "\u2014"
        parts = [p for p in spec.split("+") if p]
        return " + ".join(p.upper() if len(p) == 1 else p.capitalize()
                          for p in parts)

    # -- estimate -----------------------------------------------------------

    def _refresh_disk(self):
        try:
            self.free_bytes = shutil.disk_usage(
                os.path.dirname(self.cfg["output_dir"]) or "C:/").free
        except OSError:
            self.free_bytes = 0

    def _estimate(self):
        secs = self._lengths[self.length.current()] if hasattr(self, "length") \
            else int(self.cfg["clip_seconds"])
        bps = measured_bytes_per_sec()
        if bps is None:
            i = self.monitor.current() if self.monitors else 0
            mon = self.monitors[i] if self.monitors else {"width": 2560,
                                                          "height": 1440}
            fps = self.fps_values[self.fps.current()] if self.fps_values else 60
            cq = QUALITY[self.quality.current()][1] if hasattr(self, "quality") \
                else 23
            bps = modelled_bytes_per_sec(mon["width"], mon["height"], fps, cq)
        self.per_nab = int(secs * bps)
        ratio = (self.per_nab / self.free_bytes) if self.free_bytes else 0
        level = "danger" if ratio > 0.85 else "warn" if ratio > 0.60 else "ok"
        self.meter.set(min(1.0, ratio), level)
        self.size_label.configure(
            text=f"{human_bytes(self.per_nab)} per nab",
            fg=T.DANGER if level == "danger" else T.TEXT_MUTED)
        self.free_label.configure(
            text=f"{ratio * 100:.0f}% of {human_bytes(self.free_bytes)} free")
        self._disk_guard(level)

    def _disk_guard(self, level):
        if level == "danger" and self.disk_warn is None:
            self.disk_warn = self.disk_row.helper(
                f"A {self._lengths[self.length.current()] // 60}-minute buffer "
                f"needs {human_bytes(self.per_nab)} and only "
                f"{human_bytes(self.free_bytes)} is free. Choose a shorter "
                f"length, drop quality, or pick another drive.", T.DANGER)
        elif level != "danger" and self.disk_warn is not None:
            self.disk_warn.destroy()
            self.disk_warn = None
        self._refresh_footer()

    # -- dirty --------------------------------------------------------------

    def _mark(self, key, value):
        self.cfg[key] = value
        if self.start.get(key) != value:
            self.dirty.add(key)
        else:
            self.dirty.discard(key)
        self._refresh_footer()
        # The photographs are of settings the user has just changed.
        if self._shown:
            self._recapture()

    def _refresh_footer(self):
        blocked = self.disk_warn is not None
        n = len(self.dirty)
        if n:
            self.dirty_label.configure(
                text=f"{n} unsaved change" + ("s" if n != 1 else ""),
                fg=T.PURPLE_LIGHT)
            self.cancel_btn.set_text("Cancel")
        else:
            self.dirty_label.configure(text="No changes", fg=T.TEXT_FAINT)
            self.cancel_btn.set_text("Close")
        self.save_btn.set_enabled(bool(n) and not blocked)

    # -- actions ------------------------------------------------------------

    def _browse(self):
        # askdirectory runs a nested event loop, so the trigger watcher keeps
        # polling underneath it. auto_dismiss only covers focus loss; without
        # _modal the hotkey closed the panel out from under the open dialog
        # and the folder the user then picked was written to a hidden panel
        # and thrown away by the next prewarm.
        self.auto_dismiss = False
        self._modal = True
        try:
            path = filedialog.askdirectory(initialdir=self.cfg["output_dir"],
                                           parent=self.root)
        finally:
            self._modal = False
            self.root.after(400, lambda: setattr(self, "auto_dismiss", True))
        if path:
            path = os.path.normpath(path)
            if not os.access(path, os.W_OK):
                return
            self.folder.set(path)
            self._mark("output_dir", path)
            self._refresh_disk()
            self._estimate()

    def _open_folder(self):
        Path(self.cfg["output_dir"]).mkdir(parents=True, exist_ok=True)
        os.startfile(self.cfg["output_dir"])

    @staticmethod
    def _open(path):
        try:
            os.startfile(path)
        except OSError:
            pass

    # -- A/V sync test ------------------------------------------------------

    def _av_test(self):
        """Put a pattern on screen whose timing is known, then nab it.

        A plain five-second clip records whatever happened to be on screen, and
        nothing in it happened at a knowable instant - so there is nothing to
        check the audio against. This shows flashes and plays clicks at times
        we choose, then has the daemon save the window they fall in.

        The daemon is told before the card starts, and told *when* to save
        rather than being poked at the end: it polls every few seconds, and
        naming the moment absorbs that latency instead of racing it.
        """
        if self._avtest is not None:
            return
        i = self.monitor.current()
        mons = self.monitors or []
        if not (0 <= i < len(mons)):
            return
        if measured_bytes_per_sec() is None:
            self._av_help("Nothing is being recorded - start capture first.",
                          T.WARN)
            return
        at = time.time() + AV.TOTAL_MS / 1000.0 + 0.3
        try:
            Path(nabd.DATA_DIR / ".av_test").write_text(
                "%.3f %d" % (at, AV_CLIP_SECONDS), encoding="utf-8")
        except OSError:
            self._av_help("Could not reach the recorder.", T.WARN)
            return
        # The capture is running with the SAVED offset, so that is the number
        # the card has to show - a slider dragged but not saved is not in the
        # recording being made, and a card claiming otherwise would send the
        # user chasing an error that is really their own unsaved edit.
        live = int(self.start.get("audio_offset_ms", 0))
        note = "offset now  %s ms" % str(live).replace("-", "−")
        if "audio_offset_ms" in self.dirty:
            note += "   (slider %s not saved)" % str(
                int(self.cfg.get("audio_offset_ms", 0))).replace("-", "−")
        self._modal = True
        self.auto_dismiss = False
        self.dismiss()
        self._avtest = "pending"
        self.root.after(M.CLOSE_MS + 120, lambda: self._av_run(mons[i], note))

    def _av_run(self, monitor, note):
        if self._click is None:
            self._click = AV.click_path(nabd.DATA_DIR)
        try:
            self._avtest = AV.TestCard(self.root, monitor, note,
                                       self._av_click, self._av_finished)
        except tk.TclError:
            self._av_finished()
            return
        # Wake the output device before the pattern needs it. The card's
        # lead-in then covers the wake-up, instead of the first pair wearing
        # it as an offset that is not real.
        prime = AV.silence_path(nabd.DATA_DIR)
        if prime:
            try:
                winsound.PlaySound(
                    prime, winsound.SND_FILENAME | winsound.SND_ASYNC
                    | winsound.SND_NODEFAULT)
            except Exception:
                pass
        TIMER.begin()           # the flash-to-click gap is the measurement
        # The card guards itself, but if it ever went without saying so the
        # panel would sit modal and unprewarmed for the rest of the session.
        self.root.after(int(AV.TOTAL_MS + AV.GUARD_MS) + 2000,
                        self._av_finished)
        self._avtest.start()

    def _av_click(self):
        """A silent failure here is the worst outcome: the card still runs, the
        clip still saves, and the user judges sync against a pattern that has
        no sound in it. So it is said out loud, once."""
        if not self._click:
            return
        try:
            winsound.PlaySound(
                self._click,
                winsound.SND_FILENAME | winsound.SND_ASYNC
                | winsound.SND_NODEFAULT)
        except Exception as exc:
            self._click = None
            self._av_help("Could not play the test click: %s" % exc, T.WARN)

    def _av_finished(self):
        """Idempotent: the card calls this, and so does the failsafe above."""
        if self._avtest is None:
            return
        if self._avtest != "pending":
            TIMER.end()
        self._avtest = None
        self._modal = False
        self.root.after(400, lambda: setattr(self, "auto_dismiss", True))

    def _av_help(self, text, colour=None):
        """Say something on the A/V row, then put the instructions back."""
        try:
            self.sync_help.set(text, colour)
            self.root.after(6000, lambda: self.sync_help.set(AV_HELP))
        except tk.TclError:
            pass

    def _identify(self):
        if self._overlay:
            return
        i = self.monitor.current()
        if not (0 <= i < len(self.monitors)):
            return
        m = self.monitors[i]
        top = tk.Toplevel(self.root)
        self._overlay = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=T.PURPLE_LIGHT)
        top.geometry(f"{m['width']}x{m['height']}+{m['x']}+{m['y']}")
        inner = tk.Frame(top, bg=T.SHELL)
        inner.pack(fill="both", expand=True, padx=T.px(6), pady=T.px(6))
        tk.Label(inner, text=str(i + 1), bg=T.SHELL, fg=T.PURPLE_LIGHT,
                 font=(T.FONT_UI, -T.px(160))).place(relx=0.5, rely=0.5,
                                                     anchor="center")
        top.attributes("-alpha", 0.85)
        self.root.after(1600, self._clear_identify)

    def _clear_identify(self):
        if self._overlay:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None

    def save(self):
        if not self.dirty or self.disk_warn is not None:
            return
        nabd.save_config(self.cfg)
        self.start = dict(self.cfg)
        self.dirty.clear()
        self._refresh_footer()
        # Held so a manual close can cancel it; otherwise this fires on a panel
        # that has already gone and animates the hidden window.
        self._dismiss_id = self.root.after(700, self.dismiss)

    # -- devices / clips ----------------------------------------------------

    def _populate(self, spk, mics, mons):
        self.speakers, self.mics, self.monitors = spk, mics, mons
        # list_speakers returns dicts ({"name", "default"}) where
        # list_microphones returns plain names, and this treated both as
        # names: the dropdown was handed dicts, so opening it raised inside
        # elide_right; the selected-device match never fired, comparing a dict
        # to a string; and _spk_value wrote a dict into config.json, which
        # AudioMixer then received instead of a device name.
        want = self.cfg.get("speaker_device", "")
        names = [device_name(d) for d in spk]
        vals = ["Windows default output"] + names
        idx = next((i + 1 for i, n in enumerate(names) if n == want), 0)
        self.spk.set_values(vals, idx)

        want = self.cfg.get("mic_device", "")
        vals = ["Windows default input"] + mics
        idx = next((i + 1 for i, m in enumerate(mics) if m == want), 0)
        self.mic.set_values(vals, idx)

        labels = []
        for i, m in enumerate(mons):
            hz = nabd.monitor_refresh(m["device"])
            tail = f" \u00b7 {hz} Hz" if hz else ""
            labels.append(f"Monitor {i + 1} \u2014 {m['width']}\u00d7"
                          f"{m['height']}{tail}")
        if labels:
            mi = int(self.cfg.get("monitor", 0))
            self.monitor.set_values(labels, mi if 0 <= mi < len(labels) else 0)
            self._rebuild_fps()
            self._refresh_quality_labels()
            self._estimate()

    def _populate_clips(self, clips):
        same = (self._loaded
                and [c["path"] for c in clips] == [c["path"]
                                                   for c in self.clips])
        self.clips = clips
        self._loaded = True
        if same:
            return          # identical strip; re-rendering it changes nothing
        self.page = 0
        self._render_clips()

    # -- presentation -------------------------------------------------------

    # -- motion (PANEL-OPEN.md) ---------------------------------------------
    #
    # Two phases that never overlap: the shell arrives with an empty body and
    # comes to a complete stop, then the blocks deal out inside it. Sampled off
    # nabd_panel_open, so the spec and the build cannot drift.
    #
    # Mirrored: the spec docks to the left edge, this panel has always docked
    # to the right. Only the shell's direction of travel is flipped - the wipe
    # still runs left to right and the slip is still 56px to the right, exactly
    # as specified.

    def _hwnd(self):
        return (ctypes.windll.user32.GetParent(self.root.winfo_id())
                or self.root.winfo_id())

    def _tool_window(self):
        """Keep the panel out of the taskbar and out of Alt-Tab.

        The shell gives a taskbar button to any visible, unowned window that is
        not a tool window - and this one is visible the whole time it is
        armed, sitting transparent and clipped away between opens so that the
        hotkey costs nothing. That earned it a permanent button next to the
        real applications, which is not what a panel belonging to a tray icon
        should be. WS_EX_TOOLWINDOW says exactly that, and still allows focus,
        typing and hotkey capture.
        """
        try:
            u32 = ctypes.windll.user32
            hwnd = self._hwnd()
            style = u32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            want = (style | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
            if want != style:
                # The shell only re-reads this when the window is next shown,
                # so set it while it is hidden - which it is, until the first
                # arm.
                u32.ShowWindow(hwnd, 0)             # SW_HIDE
                u32.SetWindowLongW(hwnd, _GWL_EXSTYLE, want)
        except Exception:
            pass

    def _layered(self, on):
        """Add or drop WS_EX_LAYERED.

        Tk sets it when -alpha goes below 1.0 but never takes it off again, so
        the panel spent the whole block phase on a layered window - every
        repaint routed through the redirection surface, which is what made the
        deal choppy while the shell slide right before it was clean. The fade
        needs it; nothing after the fade does.

        Taking it off costs a full repaint of the window, so it is done either
        side of the animation. Doing it the instant alpha reached 1.0 put a
        37ms stall three quarters of the way through the shell slide.
        """
        try:
            u32 = ctypes.windll.user32
            hwnd = self._hwnd()
            style = u32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            want = (style | _WS_EX_LAYERED) if on else (
                style & ~_WS_EX_LAYERED)
            if want != style:
                u32.SetWindowLongW(hwnd, _GWL_EXSTYLE, want)
                if not on:
                    repaint(self.root)
        except Exception:
            pass

    # -- dealing a picture rather than the widgets -------------------------

    def _capture_blocks(self):
        """Photograph each block, so the deal has something cheap to move.

        Uncovering the live tree makes Windows repaint every child window in
        the strip - 7 to 13ms per block with four in flight, which is what made
        the deal choppy while the shell slide right before it held 8.5ms. The
        hero costs 1.25ms for the same strip because it is a single Canvas. A
        block that is one Label holding one picture of itself costs the same,
        and since the picture is of the widgets, putting them back when the
        panel settles is invisible.
        """
        self._capture_id = None
        if not self._shown or self._closing or self._sliding:
            return
        try:
            from PIL import ImageGrab, ImageTk
            cx, cy = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            vx = ctypes.windll.user32.GetSystemMetrics(76)
            vw = ctypes.windll.user32.GetSystemMetrics(78)
            if cw < 2 or ch < 2 or cx < vx or cx + cw > vx + vw:
                return
            # One grab of the viewport, cropped per block, rather than six.
            sheet = ImageGrab.grab(bbox=(cx, cy, cx + cw, cy + ch),
                                   all_screens=True)
            if sheet.size != (cw, ch):
                return
            self._slice_sheet(sheet, cx, cy, cw, ch)
        except Exception:
            self._shot_sig = None

    def _slice_sheet(self, sheet, cx, cy, cw, ch):
        """Cut one image of the viewport into a photograph per block."""
        from PIL import ImageTk
        for i, clip in enumerate(self._clip_frames):
            bx = clip.winfo_rootx() - cx
            by = clip.winfo_rooty() - cy
            bw, bh = self._block_w, self._block_h[i]
            if bx < 0 or by < 0 or bx + bw > cw or by + bh > ch:
                # Below the fold: the canvas clips it, so it costs nothing
                # to deal live and there is nothing on screen to copy.
                self._shot_img[i] = None
                continue
            img = ImageTk.PhotoImage(sheet.crop((bx, by, bx + bw, by + bh)))
            self._shot_img[i] = img
            self._shots[i].configure(image=img)
        self._shot_geom = self._column()
        self._shot_sig = self._content_stamp()

    def _column(self):
        return (self._block_w, tuple(self._block_y), tuple(self._block_h))

    def _content_stamp(self):
        """What the blocks are showing, cheaply. Any change makes the
        photographs a lie, and they would be dealt in place of the truth."""
        return (self._signature(), self._loaded, len(self.clips), self.page,
                tuple(sorted(self.dirty)),
                tuple(c.get("path") for c in self.clips[:PER_PAGE]),
                len(self.speakers), len(self.mics), len(self.monitors))

    def _shots_valid(self):
        return (self._shot_sig is not None
                and self._shot_geom == self._column()
                and self._shot_sig == self._content_stamp()
                and any(im is not None for im in self._shot_img))

    def _photograph_hidden(self):
        """Photograph the blocks without ever showing the panel.

        This is what makes the FIRST open as smooth as every other one. The
        photographs used to exist only after the panel had been on screen once,
        so the first open after logon - and the first after every nab, which
        invalidates them - dealt the live widget tree at p90 25ms with 9 frames
        over 16ms and a third of its frames dropped.

        Two things had to be understood. A window's own surface can be read
        with BitBlt while it is invisible (alpha 0) - PrintWindow appeared to
        return blanks only because PW_RENDERFULLCONTENT honours the window
        region, which is empty while armed. And Windows paints nothing outside
        the virtual desktop, which is exactly where the armed window parks: at
        x=-3200 the surface came back one flat colour, and moving it onto the
        display gave 24969. So: move it on, drop the region, uncover the
        blocks, force a paint, copy, and put everything back. Alpha stays 0
        throughout, so nothing appears and the mouse passes through, and
        SWP_NOACTIVATE means focus never moves.

        Costs ~130-240ms of a daemon that is otherwise idle between opens,
        against 9 dropped frames the user can see.
        """
        if self._shown or self._closing or self._sliding or not self._armed:
            return
        u32 = ctypes.windll.user32
        # Only if the dock is on the virtual desktop. Windows paints nothing
        # outside it, so off-desktop this would copy whatever stale pixels the
        # surface still held and deal them as if they were the panel - the very
        # failure this routine exists to avoid. Off-screen test harnesses park
        # there deliberately, and they should measure the live deal instead.
        vx = u32.GetSystemMetrics(76)
        vw = u32.GetSystemMetrics(78)
        if self._dock_x < vx or self._dock_x + self._w > vx + vw:
            return
        hwnd = self._hwnd()
        # Queue any trigger that lands inside root.update() below rather than
        # letting it re-enter and open the panel mid-capture - but under its
        # own flag, not _sliding: this draws a frame to put the blocks back,
        # and borrowing _sliding made that frame look like the tail of the
        # close animation (measured: close 370ms -> 972ms, one 600ms 'frame').
        self._capturing = True
        try:
            # Belt and braces: alpha 0 only hides the window while it is
            # layered, and _settle drops that style. Opaque at the dock would
            # be a full-size flash of the panel.
            self._layered(True)
            self.root.attributes("-alpha", 0.0)
            self._alpha = 0.0

            u32.SetWindowPos(hwnd, 0, self._dock_x, self._y, 0, 0, _SWP_MOVE)
            u32.SetWindowRgn(hwnd, None, False)   # an empty region never paints
            for i, clip in enumerate(self._clip_frames):
                self._covers[i].place_configure(x=self._block_w)
                clip.place_configure(x=0)
                self._block_on[i] = True
            u32.RedrawWindow(hwnd, None, None, _RDW_PAINT_NOW)
            # update(), not update_idletasks(): Tk queues its redraws as Expose
            # events, and idle tasks alone leave the surface blank.
            self.root.update()

            cx = self.canvas.winfo_rootx() - self.root.winfo_rootx()
            cy = self.canvas.winfo_rooty() - self.root.winfo_rooty()
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            sheet = window_pixels(hwnd, cx, cy, cw, ch) if cw > 1 and ch > 1 \
                else None
            # One flat colour means the surface was never painted - a display
            # that went away, say. Leave the photographs unset so the live deal
            # and the on-screen recapture still cover it.
            if sheet is not None and sheet.getcolors(2) is None:
                # The sheet starts at the canvas, but _slice_sheet locates each
                # block by subtracting the origin it is given from the block's
                # ROOT coordinates - so it needs the canvas in root coordinates,
                # not (0, 0). Passing zeros offset every crop by the header's
                # height: the hero photograph held the bottom of the hero plus
                # the strip below it, and the Buffering row was cut off the top.
                self._slice_sheet(sheet, self.canvas.winfo_rootx(),
                                  self.canvas.winfo_rooty(), cw, ch)
        except Exception:
            self._shot_sig = None
        finally:
            try:
                for clip in self._clip_frames:
                    clip.place_configure(x=-T.px(M.SLIP))
                self._alpha = self._x = self._clip_off = None
                self._draw(M.sample_open(0))   # re-cover, park, empty region
            except tk.TclError:
                pass
            self._capturing = False
        self._flush_pending()

    def _recapture(self, delay=150):
        """Re-photograph once whatever changed has stopped changing.

        Short, because a panel that is opened and closed inside a second never
        reached the old 600ms and so never had a photograph to deal - which is
        the slow, visibly choppy path. Taking one costs ~50ms of a panel that
        is sitting still, and a photograph of the wrong thing cannot survive
        _shots_valid, so taking it early is cheap and safe.
        """
        self._shot_sig = None
        if self._capture_id:
            try:
                self.root.after_cancel(self._capture_id)
            except Exception:
                pass
        try:
            self._capture_id = self.root.after(delay, self._capture_blocks)
        except tk.TclError:
            self._capture_id = None

    def _raise_shots(self):
        """Put the photographs over the widgets for the duration of a move.

        Returns whether it did, so the caller knows whether the blocks being
        dealt are one Label each or the whole widget tree.
        """
        if not self._shots_valid():
            return False
        for i, shot in enumerate(self._shots):
            if self._shot_img[i] is None:
                continue
            shot.place(x=0, y=0, width=self._block_w, height=self._block_h[i])
            shot.lift()
        return True

    def _drop_shots(self):
        for shot in self._shots:
            if shot.winfo_manager() == "place":
                shot.place_forget()

    def _clip_window(self, off):
        """Clip the window to the part inside its own display.

        The panel slides in from beyond the dock edge, and on a desktop with a
        monitor next door that space is somebody else's screen - without this
        the slide plays out over there too, sweeping across the neighbouring
        display every time the panel opens.
        """
        if off == self._clip_off:
            return
        self._clip_off = off
        try:
            hwnd = self._hwnd()
            if off <= 0:
                ctypes.windll.user32.SetWindowRgn(hwnd, None, True)
            else:
                # SetWindowRgn takes ownership of the region; do not free it.
                rgn = ctypes.windll.gdi32.CreateRectRgn(
                    off, 0, self._w, self._h)
                ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    def _move(self, x):
        """Move the window, without going through Tk.

        wm geometry only queues a request, serviced at idle - and clipping the
        window to its display provokes a WM_WINDOWPOSCHANGED, which Tk reads as
        the request having been satisfied and drops it. The panel then never
        moved at all: it sat one width off the dock edge, on the next monitor
        along, for the whole animation. SetWindowPos is immediate, so there is
        no pending request for anything to cancel.
        """
        ctypes.windll.user32.SetWindowPos(self._hwnd(), 0, x, self._y,
                                          0, 0, _SWP_MOVE)

    def _sync_geometry(self):
        """Hand Tk back its idea of where the window is, once nothing moves."""
        try:
            self.root.geometry(
                f"{self._w}x{self._h}+{self._x}+{self._y}")
        except (tk.TclError, TypeError):
            pass

    def _shell_x(self, shell):
        """Panel left edge. The only window value that changes; never width.

        Frame.x() against the display's left edge, worked in device pixels
        rather than the module's CSS-pixel PANEL_W.
        """
        return self._dock_x - int(round(self._w * (1.0 - shell)))

    def _draw(self, f):
        """One frame. Two calls per block in flight, and no layout anywhere.

        Every call is guarded on the value having actually changed. Alpha and
        geometry are each a round trip into the window manager, and re-sending
        the same alpha every frame keeps the window layered - which makes every
        repaint under it take the slow path, for the whole 400ms of the deal.
        """
        try:
            if f.alpha != self._alpha:
                self.root.attributes("-alpha", f.alpha)
                self._alpha = f.alpha
            x = self._shell_x(f.shell)
            if x != self._x:
                self._move(x)
                self._x = x
                self._clip_window(self._dock_x - x)
        except tk.TclError:
            return False
        for i in range(M.N):
            try:
                if not f.mapped(i):
                    # Covered, not unmapped. Unmapping means Tk maps the
                    # block's widgets again the first time it is dealt, which
                    # landed as a 160ms stall mid-wipe; mapping happens once,
                    # during the prewarm, where nobody is waiting (section 6).
                    if self._block_on[i]:
                        self._covers[i].place_configure(x=0)
                        self._block_on[i] = False
                    continue
                edge = f.clip_w(i, self._block_w)
                cover = self._covers[i]
                if cover.winfo_x() != edge:
                    cover.place_configure(x=edge)
                self._block_on[i] = True
                # SLIP is CSS px; the sampled fraction is what gets scaled, so
                # the slip is 56px of the user's screen at any DPI. The clip is
                # what moves: moving the block inside a stationary clip left a
                # ghost of the text at its previous position, because the strip
                # the block vacated was blitted rather than repainted.
                dx = -int(round(T.px(M.SLIP) * (1.0 - f.blocks[i])))
                clip = self._clip_frames[i]
                if clip.winfo_x() != dx:
                    clip.place_configure(x=dx)
                    # Only what is actually on screen. When the block is being
                    # dealt as a photograph the widget tree behind it is not
                    # visible, and invalidating it too would repaint every one
                    # of the ~80 windows the photograph exists to avoid.
                    shot = self._shots[i]
                    repaint(shot if shot.winfo_manager() == "place" else clip)
            except tk.TclError:
                return False
        return True

    def _display_moved(self):
        """Has the display changed shape since the window was armed?"""
        try:
            rect = screen_rect()
            return (rect.bottom - rect.top, rect.left, rect.top) != (
                self._h, self._dock_x, self._y)
        except Exception:
            return False

    def _arm(self):
        """Show the window while it is still invisible.

        Mapping a withdrawn window with 400 widgets in it costs about 110ms of
        compositing. Paid at the hotkey that is dead air before anything moves;
        paid here, between opens, it costs nothing anyone can see - the window
        is already on screen, fully transparent and clipped to nothing.
        """
        if self._armed or self._shown or self._closing:
            return
        rect = screen_rect()
        w, h = T.px(T.PANEL_W), rect.bottom - rect.top
        resized = (w, h) != (self._w, self._h)
        self._w, self._h = w, h
        self._y, self._dock_x = rect.top, rect.left
        if resized:
            # The display changed while the panel was away. Every frame of the
            # animation moves the window with SWP_NOSIZE, so without this the
            # whole open played at the old height and snapped to the new one at
            # settle - a 1440px panel on a 1000px display, footer off-screen,
            # for the entire 400ms deal.
            ctypes.windll.user32.SetWindowPos(
                self._hwnd(), 0, self._dock_x - w, self._y, w, h, _SWP_SIZE)
            self.root.update_idletasks()
            self._relayout_blocks()
            self._shot_sig = None      # photographs are of the old geometry
        self._alpha, self._x, self._clip_off = None, None, None
        self._draw(M.sample_open(0))    # transparent, parked, clipped away
        self._tool_window()
        self.root.deiconify()
        self.root.update()
        self._armed = True

    def _present(self):
        rect = screen_rect()          # re-read: the display may have changed
        w, h = T.px(T.PANEL_W), rect.bottom - rect.top
        if (w, h, rect.top, rect.left) != (self._w, self._h, self._y,
                                           self._dock_x):
            self._armed = False       # the display moved under us
        self._w, self._h = w, h
        self._y, self._dock_x = rect.top, rect.left
        self.root.update_idletasks()
        self._relayout_blocks()
        self._raise_shots()
        if not self._armed:
            # Position and empty the body BEFORE showing, or the first frame
            # flashes at wherever Tk last had the window.
            self._alpha, self._x, self._clip_off = None, None, None
            self._draw(M.sample_open(0))
            self.root.update_idletasks()
            self._tool_window()
            self.root.deiconify()
            self.root.update()
        TIMER.begin()
        self._sliding = True
        self._t0 = time.perf_counter()
        self._tick_open()

    def _tick_open(self):
        t = (time.perf_counter() - self._t0) * 1000.0
        if t >= M.OPEN_MS:
            self._settle()
            return
        if not self._draw(M.sample_open(t)):
            # _draw only fails on a TclError - a widget gone, a display gone.
            # Returning here used to leave _sliding True for the life of the
            # daemon, so every later press was queued against an animation
            # that had stopped and the panel never opened again.
            self._abandon()
            return
        try:
            self._anim_id = self.root.after(8, self._tick_open)
        except tk.TclError:
            pass

    def _settle(self):
        """Every final value written once, and only then take focus.

        Forcing focus mid-slide can pull a borderless-windowed game out of the
        foreground while the panel is still moving.
        """
        self._draw(M.sample_open(M.OPEN_MS))
        self._sync_geometry()
        self._layered(False)        # nothing is moving; a repaint is free here
        self._drop_shots()          # the widgets, in place of their picture
        try:
            self.root.focus_force()
            hwnd = (ctypes.windll.user32.GetParent(self.root.winfo_id())
                    or self.root.winfo_id())
            force_foreground(hwnd)
        except Exception:
            pass
        TIMER.end()
        self._sliding = False
        # Heights may have changed while the panel was away; settle the column
        # now that nothing is moving.
        self._queue_relayout()
        self._away_since = None
        self._shown = True
        self._flush_pending()
        # Anything that landed mid-animation was held back; this is the flush.
        if self._needs_hydrate:
            self._hydrate()
        if not self._shots_valid():
            self._recapture()

    def _flush_pending(self):
        """Act on a press that arrived while the panel was moving."""
        if not self._pending:
            return
        self._pending = False
        try:
            # after(), not a direct call: let the animation that just finished
            # unwind first, so the next one starts from a settled panel.
            self.root.after(1, self.toggle)
        except tk.TclError:
            pass

    def toggle(self):
        """The hotkey is a toggle: the same key puts the panel away again.

        Both the hotkey and the tray menu write the trigger file, so both
        behave the same way. The decision has to live here rather than in the
        app - the daemon is the only side that knows whether the panel is up.

        A press while the panel is moving is remembered rather than acted on
        at once: reversing an animation from an arbitrary point costs real
        state - where each block sits in its deal, which way its cover is
        sweeping - so the press is applied the moment the current one lands.
        Remembered as a parity, so four quick presses leave the panel where two
        would. Dropping them instead, which is what the spec suggests, meant
        every press inside the first 400ms did nothing at all.
        """
        if self._modal:
            return                  # a dialog is up; the panel is not the user's
        if self._sliding or self._capturing:
            self._pending = not self._pending
            return
        if self._shown and not self._closing:
            self.dismiss()
        else:
            self.reopen()

    def reopen(self):
        """Bring the resident panel back.

        When the prewarm still holds there is nothing to do here but move the
        window: the daemon has already reloaded the config, redrawn the hero,
        re-rendered the strip, enumerated the devices and cut the still. That
        work used to sit between the hotkey and the first frame of the slide,
        which is what made the panel look like it hesitated before coming out.
        """
        # Inert while the animation runs (section 8, question 3): 760ms is
        # short enough that nobody notices, and reversing from an arbitrary
        # point costs real state.
        if self._shown or self._closing or self._sliding:
            return
        if self._warm and self._signature() == self._sig:
            self._needs_hydrate = False
        else:
            self._refresh_all()
            self._needs_hydrate = True
        self._warm = False          # the user can change things from here on
        self._had_focus = False
        self._away_since = None
        self._present()

    # -- staying ready ------------------------------------------------------

    REWARM = 60.0       # how often the drifting figures are re-read

    def _signature(self):
        """What the content was built from. Cheap enough to test every tick."""
        def stamp(path):
            try:
                return Path(path).stat().st_mtime_ns
            except OSError:
                return 0
        # self.start, not self.cfg: cfg carries unsaved edits, so picking a
        # folder in the dialog made the panel's own change look like a config
        # change from outside and the next prewarm reloaded over the top of it.
        return (stamp(nabd.CONFIG_PATH), stamp(self.start.get("output_dir", "")))

    def _refresh_all(self):
        """Reload the config and rebuild every derived figure and drawing."""
        self.cfg = nabd.load_config()
        self.start = dict(self.cfg)
        self.dirty.clear()
        # The strip keeps what it has until the worker brings something
        # different. Blanking it to skeletons here changed the column height
        # twice a cycle for no visible benefit, and threw away the photographs
        # the deal is made of.
        self.page = 0
        self._sig = self._signature()
        self._cancel_capture()
        self._apply_config()
        self._refresh_disk()
        self._estimate()
        self._draw_hero()
        self._render_clips()
        self._refresh_footer()

    def _prewarm(self):
        """Do the whole open, hidden, and stop just short of showing it."""
        self._warm = False
        self._settled = False
        self._refresh_all()
        self._hydrate()

    def _finish_warm(self):
        """Everything has landed; the next open is nothing but the animation."""
        self.root.update_idletasks()
        self._relayout_blocks()
        self._arm()
        # _warm first: _photograph_hidden pumps the event loop, and _pump would
        # otherwise see an unwarm panel and start the prewarm again underneath
        # it. _sliding keeps _pump off the capture branch for the same reason.
        self._warm = True
        self._warm_at = time.perf_counter()
        if not self._shots_valid():
            self._photograph_hidden()

    def _maybe_prewarm(self):
        """One tick of the between-opens cycle. Only ever runs hidden."""
        if not self._warm:
            if self._settled:
                self._finish_warm()
            elif not self._hydrating:
                self._prewarm()
            return
        if self._signature() != self._sig:
            self._prewarm()             # the config changed, or a nab landed
        elif time.perf_counter() - self._warm_at > self.REWARM:
            self._refresh_figures()

    def _refresh_figures(self):
        """Free space and the size estimate drift on their own; nothing else
        does. Re-enumerating devices on a timer would mean an ffmpeg run every
        minute, all day, for a figure nobody is looking at."""
        self._refresh_disk()
        self._estimate()
        self._draw_hero()
        self._finish_warm()

    def _apply_config(self):
        """Push the freshly read config back onto the controls."""
        try:
            self.length.set(self._lengths.index(int(self.cfg["clip_seconds"])))
        except ValueError:
            self.length.set(2)
        self.reset_toggle.set(bool(self.cfg.get("reset_after_clip")))
        self._on_reset(update_only=True)
        self.folder.set(self.cfg["output_dir"])
        cq = int(self.cfg.get("cq", 23))
        self.quality.set_values(
            self._quality_labels(),
            next((i for i, q in enumerate(QUALITY) if q[1] == cq), 1))
        self.spk_vol.set(int(float(self.cfg.get("desktop_volume", 1)) * 100))
        self.spk_read.configure(text=f"{self.spk_vol.get()}%")
        self.mic_vol.set(int(float(self.cfg.get("mic_volume", 1)) * 100))
        self.mic_read.configure(text=f"{self.mic_vol.get()}%")
        self.sync.set(int(self.cfg.get("audio_offset_ms", 0)))
        self._on_sync(self.sync.get(), quiet=True)
        self.hk_nab.set_text(self._pretty(self.cfg.get("hotkey", "")))
        self.hk_nab.mark("rest")
        self.hk_nab_note.set("")
        self.hk_open.set_text(self._pretty(self.cfg.get("open_hotkey", "")))
        self.hk_open.mark("rest")
        self.hk_open_note.set(
            "Click a field, then press the combination you want. Esc cancels.")

    def _retire(self):
        """Hide, but stay alive for the next open."""
        self._sync_geometry()
        self.root.withdraw()
        self._armed = False
        self._clip_window(0)        # leave no region behind on the window
        self._drop_shots()
        self._cancel_dismiss()
        self._sliding = False
        self._shown = False
        self._closing = False
        self._warm = False      # _pump picks the next prewarm up from here
        self._settled = False
        self._had_focus = False
        self._away_since = None
        self._flush_pending()

    def dismiss(self):
        """Close: the body empties bottom-up, holds, then the shell leaves.

        Releases any hotkey hold on the way out: the panel is the only thing
        that knows the capture is over, and a panel that slid away mid-capture
        used to leave the nab key off until the deadline ran out.

        Deliberately less than half the length of the open. Opening is a
        presentation; closing is getting out of the way.

        Guarded on the whole state, not just _closing. Checking _closing alone
        let a close start on top of a running open - _tick_close and _tick_open
        both live, both resetting _t0 - and the open loop won the race: the
        panel slid away, was re-armed, then _settle drew sample_open(OPEN_MS)
        on the hidden window and it reappeared fully open, un-animated, two
        presses from where the user wanted it. Reachable from the footer Close
        button, which is on screen from the first frame of the slide.
        """
        if self._closing or self._capturing:
            return
        if self._sliding:
            # An open is in flight. Remember the close and let _flush_pending
            # play it at _settle - the same thing a hotkey press does.
            self._pending = not self._pending
            return
        if not self._shown:
            # Nothing to close: a deferred dismiss (save's after(700)) that
            # outlived a manual close would otherwise run the whole animation
            # on the armed, invisible window - its first frame is alpha 1.0 at
            # the dock, a full-size flash of the panel.
            return
        self._cancel_dismiss()
        # Sliding away with a capture live would leave the app deaf until the
        # hold's deadline expired.
        if self.capturing:
            self._cancel_capture()
        self._closing = True
        self._raise_shots()
        self._layered(True)         # the close fades out; put it back first
        TIMER.begin()
        self._sliding = True
        self._t0 = time.perf_counter()
        self._tick_close()

    def _cancel_dismiss(self):
        if self._dismiss_id:
            try:
                self.root.after_cancel(self._dismiss_id)
            except Exception:
                pass
            self._dismiss_id = None

    def _abandon(self):
        """An animation died mid-flight. Leave the panel in a state the next
        press can act on rather than wedged."""
        TIMER.end()
        self._sliding = False
        self._closing = False
        try:
            if self.daemon:
                self._retire()
            else:
                self._teardown()
        except Exception:
            self._shown = False

    def _tick_close(self):
        t = (time.perf_counter() - self._t0) * 1000.0
        if t >= M.CLOSE_MS:
            self._draw(M.sample_close(M.CLOSE_MS))
            TIMER.end()
            if self.daemon:
                self._retire()
            else:
                self._teardown()
            return
        if not self._draw(M.sample_close(t)):
            self._abandon()
            return
        try:
            self._anim_id = self.root.after(8, self._tick_close)
        except tk.TclError:
            pass

    def _teardown(self):
        TIMER.end()
        self._sliding = False
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        for attr in ("_pump_id", "_anim_id", "_relayout_id"):
            ident = getattr(self, attr, None)
            if ident:
                try:
                    self.root.after_cancel(ident)
                except Exception:
                    pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _check_dismiss(self, _event=None):
        """Slide away the moment focus moves to another application.

        Tested by process, not by focus: dropdown popups and the folder picker
        are separate windows that steal focus, and closing the panel out from
        under them would be maddening.

        Immediate. This used to note the departure on one 100ms poll and only
        act on a later one 250ms after that, so clicking away left the panel
        sitting there for up to half a second. The process test is what makes
        that safe to drop - our own popups never reach the code below - and
        <FocusOut> means it does not wait for the next poll either.
        """
        if (not self.auto_dismiss or not self._shown or self._closing
                or self._modal):
            return
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            # No foreground window at all: a handover in progress, not a
            # decision. Acting on it would close the panel at random.
            return
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            self._had_focus = True
            self._away_since = None
            return
        if not self._had_focus:
            return
        self.dismiss()

    def _pump(self):
        # Hold results back while the panel is moving, in either direction.
        # Repopulating the selects or rebuilding the thumbnail strip during the
        # slide is what made elements appear to pop in - and during the slide
        # *out* it meant content redrew just as the panel was leaving. While
        # the panel is hidden they are applied freely: that is the prewarm.
        if not self._closing and not self._sliding:
            batch = []
            try:
                while True:
                    batch.append(self._results.get_nowait())
            except queue.Empty:
                pass
            if batch:
                self._apply_batch(batch)
        # _avtest too: the prewarm hydrates, relayouts and photographs the
        # hidden window, all of which pump the event loop. The card's
        # flash-to-click gap IS the measurement, so nothing else may run inside
        # it - a hitch there is read back as an audio offset that is not real.
        if (not self._shown and not self._closing and not self._sliding
                and not self._capturing and self._avtest is None):
            try:
                # Arming is only geometry, so it must not wait on the hydrate
                # the way _finish_warm does - an unarmed window costs 110ms of
                # compositing at the hotkey.
                if self._armed and self._display_moved():
                    self._armed = False     # re-arm at the new size
                self._arm()
                self._maybe_prewarm()
            except Exception as exc:
                print("prewarm error:", exc)
        elif (self._shown and not self._closing and not self._sliding
                and self._capture_id is None and not self._shots_valid()):
            self._recapture()
        try:
            self._check_dismiss()
        except Exception:
            pass
        try:
            self._pump_id = self.root.after(100, self._pump)
        except tk.TclError:
            self._pump_id = None

    def _apply_batch(self, batch):
        """Apply everything that has landed together, not one at a time.

        Drained one per tick the panel filled in visibly, item by item; the
        whole queue at once costs a single relayout however much arrived.
        """
        for kind, payload in batch:
            try:
                if kind == "devices":
                    self._populate(*payload)
                elif kind == "clips":
                    self._populate_clips(payload)
                elif kind == "poster":
                    self._apply_poster(*payload)
                elif kind == "done":
                    self._hydrating = False
                    self._settled = True
            except Exception as exc:
                print("pump error:", exc)

    def run(self):
        self._pump()
        self.root.mainloop()

    # -- resident mode ------------------------------------------------------

    def run_daemon(self, show=False):
        """Stay hidden and built, and slide in when the trigger file changes.

        `show` presents the panel once it is warm, without going through the
        trigger file. The trigger cannot do this job: the baseline stamp below
        is taken before the widgets are built, so a write from the app that
        spawned us either lands before the baseline and is swallowed, or lands
        after it and has to be timed against a build we cannot observe from
        another process. Being told at spawn time has no race in it.

        Same shape as the banner helper: the expensive part is creating the Tk
        interpreter and ~340 widgets, so it is paid once at sign-in instead of
        on every open.
        """
        # Take the baseline stamp FIRST, before the window work below: the
        # app writes the trigger the moment the user presses the hotkey, and a
        # press landing between _warm_layout and here used to be adopted as
        # the baseline and silently discarded - the first press after logon
        # doing nothing at all.
        self._trigger_stamp = _stamp()
        if show:
            self.root.after(120, self._show_when_warm)
        self._warm_layout()
        # _pump takes it from here, prewarming until the panel is complete
        # and every block measured, so an open is nothing but the animation.
        self._pump()
        self._watch()
        self.root.mainloop()

    def _warm_layout(self):
        """Force one real layout pass before anything is measured.

        A window that has never been mapped lays out at Tk's requested size
        whatever its geometry says, so the header measured 1x1 and the header
        rule, the hero and every card sat at coordinates nothing else ever
        has. Setting the geometry is not enough and neither is update(): it
        has to be mapped once. Done far outside the virtual desktop, so there
        is no frame in which it could be seen, and the sizes survive the
        withdraw that follows.
        """
        self.root.geometry(f"{self._w}x{self._h}+{PARK_X}+0")
        self.root.deiconify()
        # update(), not update_idletasks(): the scrolling body sizes its inner
        # window from a <Configure> event, and idle tasks alone do not deliver
        # events - which left every card 32px narrow in the still.
        self.root.update()
        self.root.withdraw()
        self.root.geometry(
            f"{self._w}x{self._h}+{self._dock_x - self._w}+{self._y}")
        self.root.update_idletasks()

    def _show_when_warm(self, waited=0.0):
        """Present as soon as the panel is built, and only once.

        Waiting for _warm rather than opening immediately: the whole point of
        the resident helper is that an open is nothing but the animation, and
        sliding in over a half-built panel would undo that on the one open
        most likely to be somebody's first.
        """
        if self._shown or self._closing:
            return
        if not self._warm and waited < 20.0:
            self.root.after(100, lambda: self._show_when_warm(waited + 0.1))
            return
        try:
            self.toggle()
        except Exception as exc:
            print("open on launch failed:", exc)

    def _watch(self):
        stamp = _stamp()
        if stamp and stamp != self._trigger_stamp:
            self._trigger_stamp = stamp
            try:
                # A hotkey or a tray click toggles - you press the same thing
                # to put it away. Launching the exe does not: it means "open
                # the app", and closing the panel because it happened to be up
                # looks like the app shutting itself down.
                if _trigger_wants_show():
                    if not self._shown:
                        self.toggle()
                else:
                    self.toggle()
            except Exception as exc:
                print("toggle failed:", exc)
        try:
            self.root.after(25, self._watch)
        except tk.TclError:
            pass


def _stamp():
    try:
        return nabd.SETTINGS_TRIGGER.stat().st_mtime_ns
    except OSError:
        return None


def _trigger_wants_show():
    """Did whoever wrote the trigger mean "open", rather than "toggle"?"""
    try:
        return nabd.SETTINGS_TRIGGER.read_text(
            encoding="utf-8").strip() == nabd.SETTINGS_SHOW
    except OSError:
        return False


DAEMON_MUTEX = "Nabd.SettingsDaemon"


def daemon_running():
    handle = ctypes.windll.kernel32.OpenMutexW(0x00100000, False,
                                               DAEMON_MUTEX)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def wake_daemon():
    try:
        nabd.SETTINGS_TRIGGER.write_text(str(time.time()), encoding="utf-8")
        return True
    except OSError:
        return False


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    if "--daemon" in sys.argv:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, DAEMON_MUTEX)
        if not handle or ctypes.windll.kernel32.GetLastError() == 183:
            return 0                      # ERROR_ALREADY_EXISTS
        Panel(daemon=True).run_daemon(show="--show" in sys.argv)
        return 0
    # A one-shot launch (the Start Menu shortcut) should still go through the
    # resident panel when there is one, or two would appear.
    if "--pin" not in sys.argv and daemon_running() and wake_daemon():
        return 0
    if "--pin" not in sys.argv and focus_existing():
        return 0
    panel = Panel()
    if "--pin" in sys.argv:
        panel.auto_dismiss = False
    panel.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
