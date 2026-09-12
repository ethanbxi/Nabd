"""
Settings panel for Nab'd.

Runs as its own process (tkinter and the tray icon cannot share a main thread).
Saving writes config.json; the running app notices the change within a few
seconds and rebuilds the capture pipeline without a restart.

Layout follows one grid: a fixed label column, every control starting at the
same left edge, and helper lines sitting under the control they explain.
"""

import ctypes
import os
import queue
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog

import brand
import nabd
import theme as T

QUALITY = [("Highest", 18), ("High", 23), ("Medium", 28), ("Low", 33)]
FPS_CHOICES = nabd.FPS_CHOICES

# Rough 1440p60 bitrates per quality step, used only for the size estimate.
# Measured against real motion; a still desktop compresses to a fraction.
MBPS_AT_60 = {18: 45.0, 23: 30.0, 28: 18.0, 33: 11.0}

MOD_KEYSYMS = {"Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L",
               "Shift_R", "Super_L", "Super_R", "Win_L", "Win_R"}

# Tk state bits on Windows. NumLock is 0x0008 and ScrollLock 0x0020 - neither
# is a modifier, and treating them as one silently injects Alt into every
# captured combo whenever NumLock happens to be on.
STATE_SHIFT, STATE_CTRL, STATE_ALT = 0x0001, 0x0004, 0x20000

NAMED_KEYS = {"Insert": "insert", "Delete": "delete", "Home": "home",
              "End": "end", "Prior": "pageup", "Next": "pagedown",
              "space": "space", "Tab": "tab", "Pause": "pause",
              "Scroll_Lock": "scrolllock", "Print": "print"}

THUMB_W, THUMB_H = 132, 74
PER_PAGE = 4          # cards visible at once
MAX_RECENT = 16       # how far back the arrows can page


def _photo(image):
    """PIL image -> Tk image, or None if ImageTk is unavailable."""
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(image)
    except Exception:
        return None


class SettingsWindow:
    def __init__(self):
        self.cfg = nabd.load_config()
        try:
            self.ffmpeg = nabd.find_ffmpeg()
        except RuntimeError:
            self.ffmpeg = None

        self.root = tk.Tk()
        self.font_family = T.init()
        self.root.title(f"{nabd.DISPLAY_NAME} Settings")
        self.root.configure(bg=T.BG)
        self.root.resizable(False, False)
        # No system title bar: the panel draws its own header and close button.
        # Topmost so it stays visible across the taskbar it overlaps.
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda _e: self.dismiss())

        self._results = queue.Queue()
        self._pump_id = None
        self._shown = False
        self._closing = False
        self._had_focus = False
        self._away_since = None
        self.auto_dismiss = True   # tests drive the window without focus

        self.capturing = None      # which hotkey field is listening
        self.hotkey_value = self.cfg["hotkey"]
        self.open_hotkey_value = self.cfg.get("open_hotkey", "")
        self.speakers, self.mics, self.monitors = [], [], []
        self.clips = []
        self._thumbs = []          # PhotoImage refs; Tk drops unreferenced ones
        self._overlay = None

        self.root.withdraw()       # stay hidden until it slides in
        self._build()
        self._load_devices_async()
        self._load_clips_async()
        self._present()

    # -- layout helpers -----------------------------------------------------

    def _heading(self, parent, title, trailing=None):
        """Section title, optional controls on the right, rule between them."""
        head = tk.Frame(parent, bg=T.BG)
        head.pack(fill="x", pady=(T.GAP_SECTION, 9))
        # H2 is the guidelines' style for section headings: Outfit 20px at
        # weight 500, set as written rather than upper-cased.
        tk.Label(head, text=title, bg=T.BG, fg=T.TEXT, font=T.F_H2,
                 anchor="w").pack(side="left")
        if trailing:
            trailing(head)   # packs itself to the right, before the rule
        tk.Frame(head, bg=T.BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(12, 12), pady=(1, 0))
        return head

    def _section(self, parent, title, trailing=None):
        """A heading, then a grid whose columns line up with every other
        section's."""
        self._heading(parent, title, trailing)
        grid = tk.Frame(parent, bg=T.BG)
        grid.pack(fill="x")
        grid.columnconfigure(0, minsize=T.LABEL_COL)
        grid.columnconfigure(1, weight=1)
        # Every section reserves the same trailing column, so a row that has a
        # button beside its control does not end up with a narrower control
        # than the sections that do not.
        grid.columnconfigure(2, minsize=T.ACTION_COL)
        return grid

    def _label(self, grid, row, text):
        tk.Label(grid, text=text, bg=T.BG, fg=T.MUTED, font=T.F_BODY,
                 anchor="w").grid(row=row, column=0, sticky="w",
                                  pady=(0, T.GAP_ROW))

    def _note(self, grid, row, text, colour=None):
        """Helper line, aligned to the control column rather than the label."""
        widget = tk.Label(grid, text=text, bg=T.BG, fg=colour or T.MUTED,
                          font=T.F_SMALL, anchor="w", justify="left")
        widget.grid(row=row, column=1, columnspan=2, sticky="we",
                    pady=(0, T.GAP_ROW))
        return widget

    # -- build --------------------------------------------------------------

    def _build(self):
        # One-pixel rule down the left edge, so the panel reads as docked
        # rather than as a window that happens to be at the screen edge.
        self.root.configure(bg=T.BORDER)
        self.shell = shell = tk.Frame(self.root, bg=T.BG)
        shell.pack(fill="both", expand=True, padx=(1, 0))

        self._build_header(shell)

        foot = tk.Frame(shell, bg=T.BG)
        foot.pack(fill="x", side="bottom", padx=T.PAD, pady=(0, 20))
        tk.Frame(shell, bg=T.BORDER, height=1).pack(fill="x", side="bottom",
                                                    pady=(0, 16))

        body = tk.Frame(shell, bg=T.BG)
        body.pack(fill="both", expand=True, padx=T.PAD)

        self._build_recent(body)
        self._build_clips(body)
        self._build_length(body)
        self._build_hotkeys(body)
        self._build_video(body)
        self._build_audio(body)
        self._build_footer(foot)
        self._estimate()

    def _build_header(self, shell):
        head = tk.Frame(shell, bg=T.BG)
        head.pack(fill="x", padx=(T.PAD, 10), pady=(18, 0))
        T.CloseButton(head, self.dismiss).pack(side="right")

        # Rendered by PIL and shown as an image: the Tk canvas has no
        # antialiasing, and the logo's curves show it at this size.
        # Back to the compact header size. It sits under the guidelines' 120px
        # lockup minimum, but the artwork is now downscaled from a 512px render
        # rather than drawn, so it holds together at this size.
        tile = 34
        self.logo_image = _photo(brand.tile_lockup_image(tile))
        if self.logo_image is not None:
            tk.Label(head, image=self.logo_image, bg=T.BG,
                     bd=0).pack(side="left")
        else:   # Pillow without ImageTk: fall back to the canvas drawing
            width = int(brand.tile_lockup_width(tile)) + 2
            logo = tk.Canvas(head, width=width, height=tile + 2, bg=T.BG,
                             highlightthickness=0, bd=0)
            logo.pack(side="left")
            brand.draw_tile_lockup(logo, 1, 1, tile)
        tk.Label(head, text="Settings", bg=T.BG, fg=T.MUTED,
                 font=T.F_BODY).pack(side="left", padx=(14, 0), pady=(4, 0))
        tk.Frame(shell, bg=T.BORDER, height=1).pack(fill="x", pady=(16, 0))

    def _arrow(self, parent, glyph, command):
        btn = tk.Label(parent, text=glyph, bg=T.BG, fg=T.MUTED, font=T.F_H2,
                       padx=9, cursor="hand2")
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn["fg"] != T.BORDER
                 and btn.config(fg=T.TEXT))
        btn.bind("<Leave>", lambda _e: btn["fg"] != T.BORDER
                 and btn.config(fg=T.MUTED))
        return btn

    def _build_recent(self, body):
        def pager(head):
            self.page_next = self._arrow(head, "\u203a", lambda: self._page(1))
            self.page_next.pack(side="right")
            self.page_prev = self._arrow(head, "\u2039", lambda: self._page(-1))
            self.page_prev.pack(side="right")
            self.page_label = tk.Label(head, text="", bg=T.BG, fg=T.MUTED,
                                       font=T.F_MONO)
            self.page_label.pack(side="right", padx=(0, 8))

        grid = self._section(body, "Recent nabs", trailing=pager)
        # This strip spans the whole width rather than sitting in the columns.
        grid.columnconfigure(0, minsize=0)
        grid.columnconfigure(2, minsize=0)

        self.recent = tk.Frame(grid, bg=T.BG, height=THUMB_H + 52)
        self.recent.grid(row=0, column=0, columnspan=3, sticky="we")
        self.recent.pack_propagate(False)
        tk.Label(self.recent, text="Looking for nabs...", bg=T.BG, fg=T.MUTED,
                 font=T.F_SMALL, anchor="w").pack(anchor="w")

        actions = tk.Frame(grid, bg=T.BG)
        actions.grid(row=1, column=0, columnspan=3, sticky="we",
                     pady=(12, T.GAP_ROW))
        T.Button(actions, "Open nabs folder", self._open_clips).pack(
            side="left")
        self._update_pager()

    def _build_clips(self, body):
        grid = self._section(body, "Nabs")
        self._label(grid, 0, "Folder")
        self.dir_var = tk.StringVar(value=self.cfg["output_dir"])
        # Paths, hotkeys and durations are set in the mono face.
        self.dir_entry = T.Entry(grid, textvariable=self.dir_var,
                                 font=T.F_MONO)
        self.dir_entry.grid(row=0, column=1, sticky="we", pady=(0, T.GAP_ROW))
        # Browse shares the action column with Identify, so they line up.
        T.Button(grid, "Browse", self._browse).grid(
            row=0, column=2, sticky="we", padx=(8, 0), pady=(0, T.GAP_ROW))

    def _build_length(self, body):
        grid = self._section(body, "Nab length")
        self._label(grid, 0, "Length")
        self.length = T.Segmented(
            grid, [(s, lbl) for s, lbl in nabd.CLIP_LENGTHS],
            int(self.cfg["clip_seconds"]), on_change=lambda _v: self._estimate())
        self.length.grid(row=0, column=1, sticky="w", pady=(0, T.GAP_TIGHT))
        self.estimate = self._note(grid, 1, "")

        self._label(grid, 2, "Buffer")
        self.reset_after = T.Check(
            grid, "Start a fresh buffer after each nab",
            value=bool(self.cfg.get("reset_after_clip")),
            on_change=lambda _v: self._reset_hint())
        self.reset_after.grid(row=2, column=1, sticky="w",
                              pady=(0, T.GAP_TIGHT))
        self.reset_hint = self._note(grid, 3, "")
        self._reset_hint()

    def _build_hotkeys(self, body):
        grid = self._section(body, "Hotkeys")
        self._label(grid, 0, "Save nab")
        row = tk.Frame(grid, bg=T.BG)
        row.grid(row=0, column=1, sticky="w", pady=(0, T.GAP_ROW))
        self.hotkey_btn = T.Button(row, "", lambda: self._begin_capture("clip"),
                                   width=18, font=T.F_MONO)
        self.hotkey_btn.pack(side="left")
        self.hotkey_status = tk.Label(row, text="", bg=T.BG, fg=T.MUTED,
                                      font=T.F_SMALL)
        self.hotkey_status.pack(side="left", padx=(12, 0))

        self._label(grid, 1, "Open Nab'd")
        row2 = tk.Frame(grid, bg=T.BG)
        row2.grid(row=1, column=1, sticky="w", pady=(0, T.GAP_TIGHT))
        self.open_hotkey_btn = T.Button(
            row2, "", lambda: self._begin_capture("open"), width=18,
            font=T.F_MONO)
        self.open_hotkey_btn.pack(side="left")
        self.open_hotkey_status = tk.Label(row2, text="", bg=T.BG, fg=T.MUTED,
                                           font=T.F_SMALL)
        self.open_hotkey_status.pack(side="left", padx=(12, 0))
        self._note(grid, 2, "Click a field, then press the combination you "
                            "want. Esc cancels.")
        self._set_hotkey("clip", self.hotkey_value, check=False)
        self._set_hotkey("open", self.open_hotkey_value, check=False)

    def _build_video(self, body):
        grid = self._section(body, "Video")
        # Every select is the width of the control column, so Identify sits
        # under its field rather than squeezing it.
        self._label(grid, 0, "Monitor")
        self.monitor_dd = T.Dropdown(grid, ["Loading..."])
        self.monitor_dd.grid(row=0, column=1, sticky="we",
                             pady=(0, T.GAP_ROW))
        T.Button(grid, "Identify", self._identify).grid(
            row=0, column=2, sticky="we", padx=(8, 0), pady=(0, T.GAP_ROW))

        self._label(grid, 1, "Quality")
        cur_cq = int(self.cfg["cq"])
        q_idx = min(range(len(QUALITY)),
                    key=lambda i: abs(QUALITY[i][1] - cur_cq))
        self.quality_dd = T.Dropdown(grid, [q[0] for q in QUALITY],
                                     on_change=lambda _i: self._estimate())
        self.quality_dd.current(q_idx)
        self.quality_dd.grid(row=1, column=1, sticky="we", pady=(0, T.GAP_ROW))

        self._label(grid, 2, "Frame rate")
        self.fps_dd = T.Dropdown(grid, [f"{f} fps" for f in FPS_CHOICES],
                                 on_change=lambda _i: self._estimate())
        try:
            self.fps_dd.current(FPS_CHOICES.index(int(self.cfg["fps"])))
        except ValueError:
            self.fps_dd.current(1)
        self.fps_dd.grid(row=2, column=1, sticky="we", pady=(0, T.GAP_ROW))

    def _build_audio(self, body):
        grid = self._section(body, "Audio")
        self._label(grid, 0, "Speakers")
        self.speaker_dd = T.Dropdown(grid, ["Loading..."])
        self.speaker_dd.grid(row=0, column=1, sticky="we",
                             pady=(0, T.GAP_TIGHT))
        self.desktop_slider = self._volume(
            grid, 1, float(self.cfg["desktop_volume"]))

        self._label(grid, 2, "Microphone")
        self.mic_dd = T.Dropdown(grid, ["Loading..."])
        self.mic_dd.grid(row=2, column=1, sticky="we", pady=(0, T.GAP_TIGHT))
        self.mic_slider = self._volume(grid, 3, float(self.cfg["mic_volume"]))

        self._label(grid, 4, "A/V sync")
        # Slider fills the control column like a select; its readout sits in
        # the action column beside Identify and Browse.
        self.sync_read = tk.Label(grid, text="", bg=T.BG, fg=T.MUTED,
                                  font=T.F_MONO, anchor="w")
        self.sync_slider = T.Slider(
            grid, value=float(self.cfg.get("audio_offset_ms", 0)),
            minimum=-300.0, maximum=300.0, centred=True,
            on_change=lambda v: self.sync_read.config(text=f"{int(v):+d} ms"))
        self.sync_slider.grid(row=4, column=1, sticky="we",
                              pady=(0, T.GAP_TIGHT))
        self.sync_read.grid(row=4, column=2, sticky="w", padx=(10, 0),
                            pady=(0, T.GAP_TIGHT))
        self.sync_read.config(
            text=f"{int(self.cfg.get('audio_offset_ms', 0)):+d} ms")
        self._note(grid, 5, "Negative pulls audio earlier. Save a nab, watch "
                            "it, nudge until it matches.")

    def _volume(self, parent, row, value):
        read = tk.Label(parent, text="", bg=T.BG, fg=T.MUTED, font=T.F_MONO,
                        anchor="w")
        slider = T.Slider(parent, value=value,
                          on_change=lambda v: read.config(
                              text=f"{int(v * 100)}%"))
        slider.grid(row=row, column=1, sticky="we", pady=(0, T.GAP_ROW))
        read.grid(row=row, column=2, sticky="w", padx=(10, 0),
                  pady=(0, T.GAP_ROW))
        read.config(text=f"{int(value * 100)}%")
        return slider

    def _build_footer(self, foot):
        self.status = tk.Label(foot, text="", bg=T.BG, fg=T.MUTED,
                               font=T.F_SMALL, anchor="w")
        self.status.pack(side="left")
        T.Button(foot, "Save", self._save, accent=True, width=8).pack(
            side="right")
        T.Button(foot, "Cancel", self.dismiss, width=8).pack(side="right",
                                                             padx=(0, 8))

    # -- presentation -------------------------------------------------------

    def _present(self):
        """Dock full-height against the right edge and slide in."""
        self.root.update_idletasks()
        # A withdrawn window has no actual size yet, so ask the layout what it
        # wants. Using winfo_width() here pins the window to Tk's 200x200
        # default and clips the whole form.
        w = self.root.winfo_reqwidth()
        work = work_area()
        self._w = w
        self._h = work.bottom - work.top
        self._y = work.top
        self._start_x = work.right
        self._target_x = work.right - w
        self.root.geometry(f"{w}x{self._h}+{self._start_x}+{self._y}")
        self.root.deiconify()
        self.root.after(10, self._slide_in, 0)

    def _slide_in(self, step, steps=18):
        f = 1 - (1 - step / steps) ** 3  # ease out
        x = int(self._start_x + (self._target_x - self._start_x) * f)
        try:
            self.root.geometry(f"{self._w}x{self._h}+{x}+{self._y}")
        except tk.TclError:
            return
        if step < steps:
            self.root.after(14, self._slide_in, step + 1, steps)
        else:
            # An overrideredirect window is not given focus automatically, and
            # the text field and dropdowns need it.
            try:
                self.root.focus_force()
                hwnd = (ctypes.windll.user32.GetParent(self.root.winfo_id())
                        or self.root.winfo_id())
                force_foreground(hwnd)
            except Exception:
                pass
            self._away_since = None
            self._shown = True   # only now may click-away dismiss it

    # -- worker plumbing ----------------------------------------------------

    def _pump(self):
        """Deliver worker results on the main thread.

        Tk is not thread-safe and even root.after() raises if the main thread
        is not inside mainloop yet, so background work hands results over a
        queue and only this main-thread poller touches widgets.
        """
        try:
            while True:
                kind, payload = self._results.get_nowait()
                if kind == "devices":
                    self._populate(*payload)
                elif kind == "clips":
                    self._populate_clips(payload)
        except queue.Empty:
            pass
        except Exception as exc:
            print("pump error:", exc)
        try:
            self._check_dismiss()
        except Exception:
            pass
        try:
            self._pump_id = self.root.after(100, self._pump)
        except tk.TclError:
            self._pump_id = None

    def _load_devices_async(self):
        """Enumerating DirectShow costs about a second - keep the UI responsive."""
        def work():
            try:
                payload = (nabd.list_speakers(),
                           nabd.list_microphones(self.ffmpeg),
                           nabd.list_monitors())
            except Exception:
                payload = ([], [], [])
            self._results.put(("devices", payload))

        threading.Thread(target=work, daemon=True).start()
        self._pump_id = self.root.after(50, self._pump)

    def _load_clips_async(self):
        """Thumbnails are an ffmpeg call each, so they load behind the UI.

        The first page is published as soon as it is ready; the rest follows,
        so the strip fills immediately instead of waiting on every clip.
        """
        def work():
            found = []
            try:
                scratch = Path(tempfile.gettempdir()) / "nabd_thumbs"
                scratch.mkdir(parents=True, exist_ok=True)
                clips = nabd.recent_clips(self.cfg["output_dir"], MAX_RECENT)
                for i, clip in enumerate(clips):
                    thumb = scratch / f"recent_{i}.png"
                    try:
                        ok = nabd.clip_thumbnail(clip, thumb, THUMB_W,
                                                 self.ffmpeg)
                    except Exception:
                        ok = False
                    found.append((clip, thumb if ok else None))
                    if i + 1 == PER_PAGE:
                        self._results.put(("clips", list(found)))
            except Exception:
                pass
            self._results.put(("clips", found))

        threading.Thread(target=work, daemon=True).start()

    def _populate(self, speakers, mics, monitors):
        self.speakers, self.mics, self.monitors = speakers, mics, monitors

        labels = ["Windows default output"]
        for s in speakers:
            labels.append(s["name"] + ("  (default)" if s["default"] else ""))
        want = self.cfg["speaker_device"]
        idx = 0
        if want:
            for i, s in enumerate(speakers, start=1):
                if s["name"] == want:
                    idx = i
                    break
        self.speaker_dd.set_values(labels, idx)

        mic_labels = ["None - desktop audio only"] + mics
        idx = 0
        if self.cfg["capture_mic"]:
            want_mic = self.cfg["mic_device"]
            if want_mic and want_mic in mics:
                idx = mics.index(want_mic) + 1
            elif mics:
                idx = 1
        self.mic_dd.set_values(mic_labels, idx)

        mon_labels = []
        for i, m in enumerate(monitors):
            tag = "  (Primary)" if m["primary"] else ""
            mon_labels.append(f"Monitor {i + 1} - {m['width']}x{m['height']}{tag}")
        cur = int(self.cfg["monitor"])
        self.monitor_dd.set_values(
            mon_labels or ["Monitor 1"],
            cur if 0 <= cur < len(mon_labels) else 0)

    def _populate_clips(self, found):
        self.found = found
        self.clips = [c for c, _ in found]
        # Keep whatever page is showing if it still exists: the second delivery
        # arrives while the strip is already on screen.
        self.page = min(getattr(self, "page", 0), self._pages() - 1)
        self._render_page()

    def _pages(self):
        return max(1, -(-len(getattr(self, "found", [])) // PER_PAGE))

    def _page(self, delta):
        page = self.page + delta
        if 0 <= page < self._pages():
            self.page = page
            self._render_page()

    def _update_pager(self):
        total = len(getattr(self, "found", []))
        pages = self._pages()
        page = getattr(self, "page", 0)
        self.page_label.config(
            text=f"{page + 1}/{pages}" if total > PER_PAGE else "")
        for btn, enabled in ((self.page_prev, page > 0),
                             (self.page_next, page + 1 < pages)):
            btn.config(fg=T.MUTED if enabled else T.BORDER,
                       cursor="hand2" if enabled else "arrow")

    def _render_page(self):
        for child in self.recent.winfo_children():
            child.destroy()
        self._thumbs.clear()

        if not getattr(self, "found", []):
            tk.Label(self.recent,
                     text=f"No nabs yet - press {self._pretty(self.hotkey_value)}"
                          f" while something is on screen.",
                     bg=T.BG, fg=T.MUTED, font=T.F_SMALL, anchor="w",
                     justify="left").pack(anchor="w")
            self._update_pager()
            return

        start = self.page * PER_PAGE
        for column, (clip, thumb) in enumerate(
                self.found[start:start + PER_PAGE]):
            self._clip_card(self.recent, column, clip, thumb)
        self._update_pager()

    def _clip_card(self, parent, column, clip, thumb):
        card = tk.Frame(parent, bg=T.SURFACE, cursor="hand2")
        card.grid(row=0, column=column, sticky="nw",
                  padx=(0, 8) if column < PER_PAGE - 1 else 0)

        if thumb and thumb.exists():
            try:
                image = tk.PhotoImage(file=str(thumb))
                self._thumbs.append(image)
                art = tk.Label(card, image=image, bg=T.SURFACE, bd=0)
            except tk.TclError:
                art = tk.Frame(card, bg=T.SURFACE_2, width=THUMB_W,
                               height=THUMB_H)
        else:
            art = tk.Frame(card, bg=T.SURFACE_2, width=THUMB_W, height=THUMB_H)
        art.pack()

        # Timestamp from the name; it is already the clip's identity.
        stamp = re.sub(r"^(nab|clip)_", "", clip.stem).replace("_", "  ")
        caption = tk.Label(card, text=stamp, bg=T.SURFACE, fg=T.TEXT,
                           font=T.F_MONO, anchor="w", padx=8,
                           wraplength=THUMB_W)
        caption.pack(fill="x", pady=(6, 0))
        meta = tk.Label(card, text=nabd.clip_summary(clip), bg=T.SURFACE,
                        fg=T.MUTED, font=T.F_SMALL, anchor="w", padx=8)
        meta.pack(fill="x", pady=(0, 7))

        def open_clip(_event=None):
            try:
                os.startfile(clip)
            except OSError as exc:
                self._note_status(f"Could not open: {exc}", T.ERR)

        def hover(on):
            shade = T.SURFACE_2 if on else T.SURFACE
            for widget in (card, caption, meta):
                widget.config(bg=shade)
            if isinstance(art, tk.Label):
                art.config(bg=shade)

        for widget in (card, art, caption, meta):
            widget.bind("<Button-1>", open_clip)
            widget.bind("<Enter>", lambda _e: hover(True))
            widget.bind("<Leave>", lambda _e: hover(False))

    # -- actions ------------------------------------------------------------

    def _note_status(self, text, colour=None):
        self.status.config(text=text, fg=colour or T.MUTED)

    def _browse(self):
        chosen = filedialog.askdirectory(
            initialdir=self.dir_var.get() or str(Path.home()),
            title="Choose where nabs are saved")
        if chosen:
            self.dir_var.set(os.path.normpath(chosen))

    def _open_clips(self):
        path = Path(self.dir_var.get().strip() or self.cfg["output_dir"])
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except OSError as exc:
            self._note_status(f"Could not open the folder: {exc}", T.ERR)

    def _identify(self):
        """Outline the selected display so you can see which it is."""
        if not self.monitors:
            return
        idx = max(0, self.monitor_dd.current())
        if idx >= len(self.monitors):
            return
        mon = self.monitors[idx]

        if self._overlay is not None:
            try:
                self._overlay.destroy()
            except tk.TclError:
                pass
            self._overlay = None

        key = "#010203"
        thickness = 12
        w, h = mon["width"], mon["height"]

        top = tk.Toplevel(self.root)
        self._overlay = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=key)
        try:
            top.attributes("-transparentcolor", key)
        except tk.TclError:
            top.attributes("-alpha", 0.35)
        top.geometry(f"{w}x{h}+{mon['x']}+{mon['y']}")

        canvas = tk.Canvas(top, width=w, height=h, bg=key,
                           highlightthickness=0, bd=0)
        canvas.pack()
        half = thickness / 2
        canvas.create_rectangle(half, half, w - half, h - half,
                                outline=T.ACCENT, width=thickness)

        # Click-through and never focus-stealing: the overlay is decoration.
        top.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(top.winfo_id()) or top.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, -20, style | 0x00000020 | 0x08000000 | 0x00000080)
        except Exception:
            pass

        def fade(step=0):
            if step > 6:
                try:
                    top.destroy()
                except tk.TclError:
                    pass
                if self._overlay is top:
                    self._overlay = None
                return
            try:
                top.attributes("-alpha", 1.0 - step / 7)
            except tk.TclError:
                return
            top.after(45, fade, step + 1)

        top.after(1300, fade)
        self._note_status(f"Monitor {idx + 1} outlined")

    # -- hotkey capture -----------------------------------------------------

    def _pretty(self, spec):
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
        out = []
        for part in (spec or "").split("+"):
            if not part:
                continue
            out.append(names.get(part, part.upper() if len(part) <= 3
                                 else part.title()))
        return " + ".join(out) or "None"

    def _field(self, which):
        if which == "clip":
            return self.hotkey_btn, self.hotkey_status
        return self.open_hotkey_btn, self.open_hotkey_status

    def _set_hotkey(self, which, spec, check=True):
        if which == "clip":
            self.hotkey_value = spec
        else:
            self.open_hotkey_value = spec
        button, status = self._field(which)
        button.set_text(self._pretty(spec))
        if not check:
            status.config(text="")
            return
        if nabd.hotkey_available(spec):
            status.config(text="available", fg=T.OK)
        else:
            status.config(text="already in use", fg=T.ERR)

    def _begin_capture(self, which):
        self.capturing = which
        button, status = self._field(which)
        button.set_text("Press a combination...")
        status.config(text="listening", fg=T.MUTED)
        self.root.bind("<KeyPress>", self._on_key)
        self.root.focus_force()

    def _cancel_capture(self):
        which, self.capturing = self.capturing, None
        self.root.unbind("<KeyPress>")
        if which:
            value = (self.hotkey_value if which == "clip"
                     else self.open_hotkey_value)
            self._set_hotkey(which, value, check=False)

    def _on_key(self, event):
        if not self.capturing or event.keysym in MOD_KEYSYMS:
            return
        if event.keysym == "Escape":
            self._cancel_capture()
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
                return  # unsupported key; keep listening

        spec = "+".join(mods + [key])
        try:
            nabd.parse_hotkey(spec)
        except ValueError:
            return

        which, self.capturing = self.capturing, None
        self.root.unbind("<KeyPress>")
        self._set_hotkey(which, spec)
        if not mods and not key.startswith("f"):
            self._note_status("Heads up: a bare key also fires while you type.")
        else:
            self._note_status("")

    # -- estimate -----------------------------------------------------------

    def _reset_hint(self):
        if self.reset_after.get():
            text = ("Each nab picks up where the last ended, so nabs never "
                    "overlap.")
        else:
            text = ("Always keeps the most recent footage, so nabs taken "
                    "close together overlap.")
        self.reset_hint.config(text=text)

    def _selected_cq(self):
        i = self.quality_dd.current()
        return QUALITY[i][1] if 0 <= i < len(QUALITY) else 23

    def _selected_fps(self):
        i = self.fps_dd.current()
        return FPS_CHOICES[i] if 0 <= i < len(FPS_CHOICES) else 60

    def _estimate(self):
        mbps = MBPS_AT_60.get(self._selected_cq(), 30.0) * (
            self._selected_fps() / 60)
        mb = self.length.get() * mbps / 8
        size = f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:,.0f} MB"
        # Buffer and clip are the same footage, so one number covers both.
        self.estimate.config(
            text=f"About {size} per nab, and that much stays buffered on disk.")

    # -- save / dismiss -----------------------------------------------------

    def _save(self):
        out_dir = self.dir_var.get().strip()
        if not out_dir:
            self._note_status("Choose a nabs folder.", T.ERR)
            return
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._note_status(f"Cannot use that folder: {exc}", T.ERR)
            return

        cfg = dict(self.cfg)
        cfg["output_dir"] = out_dir
        cfg["clip_seconds"] = int(self.length.get())
        cfg["reset_after_clip"] = bool(self.reset_after.get())
        cfg["hotkey"] = self.hotkey_value
        cfg["open_hotkey"] = self.open_hotkey_value
        cfg["cq"] = self._selected_cq()
        cfg["fps"] = self._selected_fps()
        cfg["monitor"] = max(0, self.monitor_dd.current())
        cfg["desktop_volume"] = round(self.desktop_slider.get(), 2)
        cfg["mic_volume"] = round(self.mic_slider.get(), 2)
        cfg["audio_offset_ms"] = int(self.sync_slider.get())

        spk = self.speaker_dd.current()
        cfg["speaker_device"] = "" if spk <= 0 else self.speakers[spk - 1]["name"]

        mic = self.mic_dd.current()
        if mic <= 0:
            cfg["capture_mic"] = False
            cfg["mic_device"] = ""
        else:
            cfg["capture_mic"] = True
            cfg["mic_device"] = self.mics[mic - 1]

        try:
            nabd.save_config(cfg)
        except OSError as exc:
            self._note_status(f"Could not save: {exc}", T.ERR)
            return

        self._note_status("Saved - applying...", T.OK)
        self.root.after(900, self.dismiss)

    def _check_dismiss(self):
        """Slide away once focus moves to another application.

        Tested by process, not by focus: dropdown menus and the folder picker
        are separate windows that steal focus, and closing the panel out from
        under them would be maddening.
        """
        if not self.auto_dismiss or not self._shown or self._closing:
            return
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            self._had_focus = True
            self._away_since = None
            return
        # Windows refuses foreground to a process launched in the background.
        # If we never held it, vanishing unprompted would be far worse than
        # staying put until the user closes the panel themselves.
        if not self._had_focus:
            return
        now = time.time()
        if self._away_since is None:
            self._away_since = now      # brief handovers are normal
        elif now - self._away_since > 0.25:
            self.dismiss()

    def dismiss(self):
        """Animate out, then tear down."""
        if self._closing:
            return
        self._closing = True
        self._slide_out(0)

    def _slide_out(self, step, steps=13):
        # Ease in rather than out: leaving should feel decisive.
        f = (step / steps) ** 2.2
        x = int(self._target_x + (self._start_x - self._target_x) * f)
        try:
            self.root.geometry(f"{self._w}x{self._h}+{x}+{self._y}")
            self.root.update_idletasks()
        except tk.TclError:
            return
        if step < steps:
            self.root.after(12, self._slide_out, step + 1, steps)
        else:
            self.close()

    def close(self):
        """Cancel the poller before tearing down, or Tk complains about
        invoking a command that no longer exists."""
        if self._pump_id is not None:
            try:
                self.root.after_cancel(self._pump_id)
            except Exception:
                pass
            self._pump_id = None
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.mainloop()


# -- window helpers --------------------------------------------------------

def work_area():
    """Full primary display, taskbar included.

    The panel runs the whole height of the screen, so it uses the monitor
    bounds rather than the work area and sits topmost to stay visible over the
    taskbar.
    """
    rect = wintypes.RECT()
    rect.left, rect.top = 0, 0
    rect.right = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
    rect.bottom = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return rect


def force_foreground(hwnd):
    """Actually bring a window to the front.

    SetForegroundWindow alone is refused unless the calling thread owns the
    current foreground window, which a tray-launched process does not.
    Attaching to the foreground thread first is the supported way around it.
    """
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.GetForegroundWindow() == hwnd:
        return True
    foreign = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(),
                                              None)
    ours = kernel32.GetCurrentThreadId()
    attached = bool(foreign and foreign != ours
                    and user32.AttachThreadInput(ours, foreign, True))
    try:
        user32.ShowWindow(hwnd, 5)          # SW_SHOW
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(ours, foreign, False)


def focus_existing():
    """Raise the settings window that is already open, if there is one."""
    hwnd = ctypes.windll.user32.FindWindowW(
        None, f"{nabd.DISPLAY_NAME} Settings")
    if not hwnd:
        return False
    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    force_foreground(hwnd)
    return True


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # Opening it repeatedly should raise this window, not stack up copies that
    # each write config on save.
    ctypes.windll.kernel32.CreateMutexW(None, False, "Nabd.Settings")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        focus_existing()
        return
    window = SettingsWindow()
    # --pin keeps the panel up when focus moves, for screenshots and tooling.
    if "--pin" in sys.argv:
        window.auto_dismiss = False
    window.run()


if __name__ == "__main__":
    main()

