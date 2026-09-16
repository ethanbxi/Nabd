"""nab'd main window.

A second container around the widgets the docked drawer already has. It is not
a second settings UI: the content column is deliberately the drawer's width
(860 = 196 rail + 664 content, 624 card against the drawer's 608), so
`Panel._build_capture(parent)` and its siblings render into it unmodified. One
embedded Panel owns all the state; this file owns only the shell around it and
the two things the drawer has no equivalent of -- the App group and first run.
See docs/window/WINDOW.md.

Chrome is NATIVE, tinted dark through nabd_window.apply_dark_titlebar. That one
call keeps snap layouts, Aero Peek, the system menu, eight-edge resize and
mixed-DPI behaviour working. The banner stays overrideredirect -- it is
non-interactive and should not read as a window at all. The two being chromed
differently is a decision, not an inconsistency.
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import brand
import nabd
import nabd_paint as P
import nabd_tokens as T
import nabd_ui as U
import nabd_window as W
import settings as S

RAIL_BG = "#0E0E11"          # the drawer's header/footer field, reused
FOOTER_BG = "#0E0E11"

TRAY_NOTE = ("nab'd keeps running in your tray when you close this window. "
             "The buffer only stops when you quit.")
SETUP_NOTE = ("nab'd keeps the last few minutes in memory. When something good "
              "happens, you press a key and it writes the part that already "
              "went past.")


def work_areas():
    """Display work areas for clamp_to_visible, primary first.

    WINDOW.md section 5 asks for the enumeration the frame-rate helper already
    does, and for WORK areas so a restored window does not come back
    underneath the taskbar. list_monitors read rcWork out of MONITORINFOEXW all
    along and discarded it; it now carries both.
    """
    out = []
    for m in nabd.list_monitors():
        r = m.get("work") or (m["x"], m["y"], m["width"], m["height"])
        out.append(tuple(r))
    return out


class Window:
    """The window. One instance per process, guarded by a mutex in main()."""

    def __init__(self, cfg, first_run=False):
        self.cfg = cfg
        self.first_run = first_run
        self.section = None
        self._nav = {}
        self._panes = {}
        self._pump_id = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.configure(bg=T.PANEL)
        W.configure(self.root, "nab'd")
        self._set_icon()
        try:
            T.set_scale(ctypes.windll.user32.GetDpiForWindow(
                self.root.winfo_id()))
        except Exception:
            pass
        W.restore_geometry(self.root, self.cfg.get("window_geometry", ""),
                           work_areas())
        self.root.minsize(T.px(W.MIN_W), T.px(W.MIN_H))

        self._build()
        self._build_sections()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-f>",
                       lambda _e: self.search_entry.focus_set())
        self.show("Home")
        self._set_status(not self.first_run)
        self.root.deiconify()
        self._pump()
        self._watch()

    def _set_icon(self):
        """The title bar, Alt-Tab and the taskbar.

        Nothing ever set one, so Tk showed its own feather. Rendered from the
        same brand tile the tray icon uses rather than shipping an .ico:
        icon.ico exists but is not in the bundle - it is Inno's setup icon and
        the exe's resource, neither of which Tk can reach at runtime.
        """
        try:
            from PIL import ImageTk
            # Held on the instance: Tk keeps no reference and the image is
            # collected out from under the window if this is a local.
            self._icon = ImageTk.PhotoImage(brand.tile_image(64))
            self.root.iconphoto(True, self._icon)
        except Exception as exc:
            nabd.log(f"could not set the window icon: {exc}")

    # -- shell -------------------------------------------------------------

    def _build(self):
        body = tk.Frame(self.root, bg=T.PANEL)
        body.pack(fill="both", expand=True)

        rail = tk.Frame(body, bg=RAIL_BG, width=T.px(W.RAIL_W))
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Frame(body, bg=T.LINE, width=T.px(1)).pack(side="left", fill="y")
        self._build_rail(rail)

        # The content column owns its own footer: WINDOW.md puts the footer
        # under the content only, not across the rail.
        right = tk.Frame(body, bg=T.PANEL)
        right.pack(side="left", fill="both", expand=True)
        self._build_footer(right)
        self.content = tk.Frame(right, bg=T.PANEL)
        self.content.pack(fill="both", expand=True,
                          padx=T.px(W.CONTENT_PAD), pady=T.px(W.CONTENT_PAD))

    def _build_rail(self, rail):
        head = tk.Frame(rail, bg=RAIL_BG)
        head.pack(fill="x", padx=T.px(16), pady=(T.px(18), T.px(14)))
        lock = tk.Label(head, bg=RAIL_BG, bd=0)
        P.photo(lock, brand.tile_lockup_image(T.px(T.LOGO_TILE),
                                              field=T.PURPLE, ring=T.TEXT,
                                              word=T.TEXT))
        lock.configure(image=lock._img)
        lock.pack(side="left")

        self.search = self._build_search(rail)

        items = tk.Frame(rail, bg=RAIL_BG)
        items.pack(fill="x", pady=(T.px(14), 0))
        for name in W.NAV:
            self._nav[name] = self._nav_item(items, name)

        foot = tk.Frame(rail, bg=RAIL_BG)
        foot.pack(side="bottom", fill="x", padx=T.px(16), pady=(0, T.px(16)))
        tk.Frame(rail, bg=T.LINE, height=T.px(1)).pack(
            side="bottom", fill="x", padx=T.px(16), pady=(0, T.px(14)))
        # Visible from every section on purpose: a tray app is invisible by
        # design, and the one place it IS visible should never make anyone hunt
        # for whether it is working.
        self.status_dot = tk.Label(foot, text="\u25cf", bg=RAIL_BG,
                                   fg=T.PURPLE_LIGHT, font=T.font("mono_sm"))
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(foot, text="Buffering", bg=RAIL_BG,
                                    fg=T.TEXT, font=T.font("value"))
        self.status_text.pack(side="left", padx=(T.px(8), 0))
        tk.Label(foot, text=nabd.VERSION, bg=RAIL_BG, fg=T.TEXT_FAINT,
                 font=T.font("mono_xs")).pack(side="right")

    def _build_search(self, rail):
        """Drawn here rather than reusing U.Field: that one is a read-only path
        field that elides from the LEFT, which is right for C:\\...\\Videos and
        wrong for a query. Filters the rail as you type."""
        box = U.RoundedFrame(rail, radius=T.R_CONTROL, fill=T.RAISED,
                             outline=T.LINE_STRONG, bg=RAIL_BG,
                             height=T.px(W.SEARCH_H))
        box.pack(fill="x", padx=T.px(16))
        box.pack_propagate(False)
        inner = tk.Frame(box, bg=T.RAISED)
        inner.pack(fill="both", expand=True, padx=T.px(10))
        tk.Label(inner, text="\u2315", bg=T.RAISED, fg=T.TEXT_FAINT,
                 font=(T.FONT_UI, -T.px(14))).pack(side="left")
        self.search_entry = tk.Entry(
            inner, bg=T.RAISED, fg=T.TEXT, bd=0, highlightthickness=0,
            insertbackground=T.TEXT, font=T.font("value"))
        self.search_entry.pack(side="left", fill="both", expand=True,
                               padx=(T.px(7), 0))
        self.search_hint = tk.Label(inner, text="Search", bg=T.RAISED,
                                    fg=T.TEXT_FAINT, font=T.font("value"))
        self.search_hint.place(in_=self.search_entry, x=0, rely=0.5,
                               anchor="w")
        self.search_tag = tk.Label(inner, text="Ctrl F", bg=T.RAISED,
                                   fg=T.TEXT_FAINT, font=T.font("mono_xs"))
        self.search_tag.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._on_search())
        self.search_entry.bind("<Escape>", lambda _e: self._clear_search())
        return box

    def _on_search(self):
        """Filter the rail. The panes themselves do not scroll, so jumping to
        the section is the whole of what searching can usefully do here."""
        if self.search_entry.get():
            self.search_hint.place_forget()
        else:
            self.search_hint.place(in_=self.search_entry, x=0, rely=0.5,
                                   anchor="w")
        q = self.search_entry.get().strip().lower()
        for name, item in self._nav.items():
            hit = not q or q in name.lower() or q in _KEYWORDS.get(name, "")
            if hit and not item["row"].winfo_ismapped():
                item["row"].pack(fill="x", pady=T.px(1))
            elif not hit and item["row"].winfo_ismapped():
                item["row"].pack_forget()

    def _clear_search(self):
        self.search_entry.delete(0, "end")
        self._on_search()

    def _nav_item(self, parent, name):
        """A rail entry: raised background when active, plus a 2px bar on its
        left edge -- the bar is what reads as 'you are here' at a glance."""
        row = tk.Frame(parent, bg=RAIL_BG, height=T.px(44))
        row.pack(fill="x", pady=T.px(1))
        row.pack_propagate(False)
        bar = tk.Frame(row, bg=RAIL_BG, width=T.px(2))
        bar.pack(side="left", fill="y")
        inner = tk.Frame(row, bg=RAIL_BG)
        inner.pack(side="left", fill="both", expand=True,
                   padx=(T.px(14), T.px(16)))
        label = tk.Label(inner, text=name, bg=RAIL_BG, fg=T.TEXT_MUTED,
                         font=T.font("label"), anchor="w", cursor="hand2")
        label.pack(fill="both", expand=True)
        item = {"row": row, "bar": bar, "body": inner, "label": label}
        for w in (row, inner, label):
            w.bind("<Button-1>", lambda _e, n=name: self.show(n))
            w.bind("<Enter>", lambda _e, i=item: self._nav_hover(i, True))
            w.bind("<Leave>", lambda _e, i=item: self._nav_hover(i, False))
        return item

    def _nav_hover(self, item, on):
        if item["label"].cget("text") == self.section:
            return
        bg = T.RAISED if on else RAIL_BG
        for key in ("row", "body", "label"):
            item[key].configure(bg=bg)

    def _build_footer(self, parent):
        tk.Frame(parent, bg=T.LINE, height=T.px(1)).pack(fill="x",
                                                         side="bottom")
        foot = tk.Frame(parent, bg=FOOTER_BG, height=T.px(W.FOOTER_H))
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        self.dirty_label = tk.Label(foot, text="No changes", bg=FOOTER_BG,
                                    fg=T.TEXT_FAINT, font=T.font("mono_sm"))
        self.dirty_label.pack(side="left", padx=T.px(16))
        self.save_btn = U.Button(foot, "Save", self.save, variant="primary",
                                 bg=FOOTER_BG, width=78)
        self.save_btn.pack(side="right", padx=(0, T.px(16)))
        self.close_btn = U.Button(foot, "Close", self.close, variant="quiet",
                                  bg=FOOTER_BG)
        self.close_btn.pack(side="right", padx=(0, T.px(9)))
        self.save_btn.set_enabled(False)

    # -- the sections ------------------------------------------------------

    def _build_sections(self):
        """One embedded Panel, its groups built into our panes.

        The builders already take a parent, so none of them is touched. The
        footer widgets are handed over as-is: Panel._refresh_footer writes to
        dirty_label / save_btn / cancel_btn, and ours are those.
        """
        self.panel = S.Panel(embed=self.content)
        self.panel.dirty_label = self.dirty_label
        self.panel.save_btn = self.save_btn
        self.panel.cancel_btn = self.close_btn

        for name in W.NAV:
            self._panes[name] = self._pane(name)

        p = self.panel
        # Home's groups are built whatever the state, so every Panel method
        # that reaches for them stays safe; first run only changes what gets
        # packed. See _build_home.
        self._build_home(self._panes["Home"].inner)
        p._build_capture(self._panes["Capture"].inner)
        p._build_video(self._panes["Video"].inner)
        p._build_audio(self._panes["Audio"].inner)
        p._build_hotkeys(self._panes["Hotkeys"].inner)
        self._build_app(self._panes["App"].inner)

        # The same settle-up the drawer does at the end of its own __init__.
        p._refresh_disk()
        p._estimate()
        p._draw_hero()
        p._refresh_footer()
        p._hydrate()

    def _pane(self, name):
        """A pane, capped at GROUP_MAX_W so maximising does not stretch cards.

        Placed rather than packed: place is what can be given an explicit
        width, and the cap is the whole point.
        """
        pane = tk.Frame(self.content, bg=T.PANEL)
        inner = tk.Frame(pane, bg=T.PANEL)
        inner.place(x=0, y=0, relheight=1.0, width=T.px(W.GROUP_MAX_W))
        pane.bind("<Configure>", lambda e, f=inner: f.place_configure(
            width=min(e.width, T.px(W.GROUP_MAX_W))))
        pane.inner = inner
        return pane

    def _build_home(self, parent):
        """Not a settings group. It answers what somebody actually opened the
        window to ask -- is it running, what has it got, where did my nabs go --
        and it is where the tray behaviour gets explained, because "I closed it
        and it kept recording" is the most surprising thing about this app."""
        self.setup_box = tk.Frame(parent, bg=T.PANEL)
        self.hero_box = tk.Frame(parent, bg=T.PANEL)
        self.recent_box = tk.Frame(parent, bg=T.PANEL)
        self.panel._build_hero(self.hero_box)
        self.panel._build_recent(self.recent_box)
        if self.first_run:
            self._build_setup(self.setup_box)
            self.setup_box.pack(fill="x")
        else:
            self.hero_box.pack(fill="x")
            self.recent_box.pack(fill="x")

        # Pinned to the bottom: the first time somebody closes this window they
        # will assume they closed the app.
        note = U.card(parent)
        note.pack(side="bottom", fill="x", pady=(T.px(16), 0))
        inner = tk.Frame(note, bg=T.SURFACE)
        inner.pack(fill="x", padx=T.px(T.ROW_PAD_X), pady=T.px(T.ROW_PAD_Y))
        U.Button(inner, "Quit nab'd", self.quit_app, variant="quiet",
                 bg=T.SURFACE).pack(side="right", padx=(T.px(14), 0))
        tk.Label(inner, text=TRAY_NOTE, bg=T.SURFACE, fg=T.TEXT_MUTED,
                 font=T.font("value"), justify="left", anchor="w",
                 wraplength=T.px(420)).pack(side="left", fill="x", expand=True)

    # -- App: the only genuinely new group ---------------------------------

    def _build_app(self, parent):
        card = self.panel._make_group(parent, "app")
        r = 0
        row = self.panel._row(card, "Start with Windows", r, first=True)
        self.autostart = U.Toggle(row.line, nabd_autostart_enabled(),
                                  command=lambda v: self._on_autostart(v))
        self.autostart.pack(side="right")
        self.autostart_note = row.helper(
            "Launches minimised to the tray so the buffer is always warm.")

        r += 1
        self.panel._sep(card, r)
        r += 1
        row = self.panel._row(card, "Automatic updates", r)
        self.auto_update = U.Toggle(
            row.line, bool(self.panel.cfg.get("auto_update", True)),
            command=lambda v: self.panel._mark("auto_update", bool(v)))
        self.auto_update.pack(side="right")
        row.helper("Downloads new versions in the background and installs "
                   "them the next time nab'd starts, so the buffer is never "
                   "interrupted. Off means it never checks.")

        r += 1
        self.panel._sep(card, r)
        r += 1
        row = self.panel._row(card, "Version", r)
        self.update_btn = U.Button(row.line, "Check for updates",
                                   self._check_updates, variant="ghost")
        self.update_btn.pack(side="right")
        tk.Label(row.line, text=nabd.VERSION, bg=T.SURFACE, fg=T.TEXT_MUTED,
                 font=T.font("mono")).pack(side="right", padx=(0, T.px(9)))
        # No claim about being current until something has actually looked.
        self.version_note = row.helper("")
        self._ready = None          # a staged installer, once one is found
        self._show_staged()

        r += 1
        self.panel._sep(card, r)
        r += 1
        row = self.panel._row(card, "Licences", r, last=True)
        U.Button(row.line, "FFmpeg source", self._ffmpeg_source,
                 variant="ghost").pack(side="right")
        U.Button(row.line, "Third-party notices", self._notices,
                 variant="ghost").pack(side="right", padx=(0, T.px(9)))
        row.helper("FFmpeg is bundled and redistributed under its own licence.")

    def _on_autostart(self, on):
        """Written straight to the Run key rather than into config.json.

        Windows owns this setting - the installer writes the same value, and
        anyone can turn it off from Task Manager - so config.json would be a
        second copy of a truth it does not hold.
        """
        ok = set_autostart(bool(on))
        if not ok:
            self.autostart_note.set("Could not change the startup entry.",
                                    T.WARN)
            self.autostart.set(nabd_autostart_enabled())
        else:
            self.autostart_note.set(
                "Launches minimised to the tray so the buffer is always warm.")

    def _show_staged(self):
        """A build already downloaded is waiting for the next start; offer to
        take it now rather than making somebody wonder when 'next' is."""
        import nabd_update
        self._ready = nabd_update.staged(nabd.DATA_DIR, nabd.VERSION)
        if self._ready:
            version = self._ready.stem.split("-")[-1]
            self.version_note.set(
                "%s is downloaded. It installs when nab'd next starts."
                % version, T.PURPLE_LIGHT)
            self.update_btn.set_text("Install and restart")

    def _check_updates(self):
        """Ask GitHub, on a thread, because you asked.

        The background check does the same thing on a timer when automatic
        updates are on; this is the same call without the wait.
        """
        if self._ready:
            self._install_now()
            return
        self.version_note.set("Checking\u2026", T.TEXT_FAINT)
        self.update_btn.set_enabled(False)
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        import nabd_update
        found = nabd_update.check(nabd.VERSION)
        if not found:
            self._version_says("Up to date, or could not reach GitHub.",
                               T.TEXT_FAINT)
            return
        version, url, name = found
        self._version_says("%s is available - downloading\u2026" % version,
                           T.PURPLE_LIGHT)
        path = nabd_update.stage(nabd.DATA_DIR, url, name, nabd.VERSION)
        if path is None:
            self._version_says("%s is available, but the download failed."
                               % version, T.WARN, link=True)
            return
        self._version_says("%s is ready to install." % version,
                           T.PURPLE_LIGHT, staged=path)

    def _install_now(self):
        """Hand off and go. The installer restarts nab'd afterwards."""
        import nabd_update
        self.version_note.set("Installing\u2026", T.PURPLE_LIGHT)
        self.root.update_idletasks()
        if not nabd_update.apply(self._ready):
            self.version_note.set("Could not start the installer.", T.WARN)
            return
        # The app has to be out of the way before its own exe is replaced.
        try:
            nabd.QUIT_TRIGGER.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass
        self.close()

    def _version_says(self, text, colour, detail="", link=False, staged=None):
        """Back onto the Tk thread; a worker must not touch widgets."""
        def apply():
            try:
                self.version_note.set(text, colour)
                self.update_btn.set_enabled(True)
                if staged is not None:
                    self._ready = staged
                    self.update_btn.set_text("Install and restart")
                if link:
                    self.version_note.configure(cursor="hand2")
                    self.version_note.bind(
                        "<Button-1>", lambda _e: self._releases())
            except tk.TclError:
                pass
            if detail:
                nabd.log(f"update check failed: {detail}")
        try:
            self.root.after(0, apply)
        except tk.TclError:
            pass

    def _releases(self):
        import webbrowser
        import nabd_update
        webbrowser.open(nabd_update.RELEASES)

    def _notices(self):
        self._open(nabd.ASSET_DIR / "THIRD-PARTY-NOTICES.md")

    def _ffmpeg_source(self):
        import webbrowser
        webbrowser.open("https://www.gyan.dev/ffmpeg/builds/")

    @staticmethod
    def _open(path):
        try:
            os.startfile(str(path))
        except OSError as exc:
            nabd.log(f"could not open {path}: {exc}")

    # -- first run ---------------------------------------------------------

    def _build_setup(self, parent):
        """Three questions, because three are the ones that cannot be
        defaulted. Quality, frame rate, devices and length all have defensible
        defaults; asking about them turns a 20-second setup into a form."""
        card = U.card(parent)
        card.pack(fill="x")
        pad = T.px(T.ROW_PAD_X) + T.px(9)
        head = tk.Frame(card, bg=T.SURFACE)
        head.pack(fill="x", padx=pad, pady=(T.px(22), 0))
        tk.Label(head, text="Three things, then you\u2019re recording.",
                 bg=T.SURFACE, fg=T.TEXT, anchor="w",
                 font=(T.FONT_UI_MEDIUM, -T.px(21))).pack(fill="x")
        tk.Label(head, text=SETUP_NOTE, bg=T.SURFACE, fg=T.TEXT_MUTED,
                 anchor="w", justify="left", wraplength=T.px(520),
                 font=T.font("label")).pack(fill="x", pady=(T.px(8), 0))

        rows = tk.Frame(card, bg=T.SURFACE)
        rows.pack(fill="x", padx=pad, pady=(T.px(20), 0))
        self._setup_row(rows, 1, "Where nabs go", self._setup_folder)
        self._setup_row(rows, 2, "Key to save a nab", self._setup_hotkey)
        # Nothing to choose when there is one display; the row would be a
        # question with one answer.
        self.mons_at_setup = len(nabd.list_monitors())
        if self.mons_at_setup > 1:
            self._setup_row(rows, 3, "Screen to capture", self._setup_monitor)

        tk.Frame(card, bg=T.LINE, height=T.px(1)).pack(
            fill="x", padx=pad, pady=(T.px(20), 0))
        foot = tk.Frame(card, bg=T.SURFACE)
        foot.pack(fill="x", padx=pad, pady=(T.px(18), T.px(22)))
        U.Button(foot, "Start buffering", self._start_buffering,
                 variant="primary", bg=T.SURFACE,
                 width=168).pack(side="left")
        tk.Label(foot, text="Everything else is already set sensibly. "
                            "Change any of it from the left.",
                 bg=T.SURFACE, fg=T.TEXT_FAINT, font=T.font("value"),
                 anchor="w", justify="left",
                 wraplength=T.px(360)).pack(side="left", padx=(T.px(16), 0))

    def _setup_row(self, parent, n, label, build):
        row = tk.Frame(parent, bg=T.SURFACE)
        row.pack(fill="x", pady=(0, T.px(14)))
        dot = tk.Label(row, text=str(n), bg=T.SURFACE, fg=T.PURPLE_LIGHT,
                       font=T.font("mono_sm"), width=2)
        dot.pack(side="left")
        tk.Label(row, text=label, bg=T.SURFACE, fg=T.TEXT, anchor="w",
                 font=T.font("label")).pack(side="left", padx=(T.px(10), 0))
        holder = tk.Frame(row, bg=T.SURFACE)
        holder.pack(side="right")
        build(holder)

    def _setup_folder(self, holder):
        U.Button(holder, "Browse", self._setup_browse,
                 variant="ghost").pack(side="right")
        self.setup_folder = U.Field(holder, self.cfg["output_dir"], width=240)
        self.setup_folder.pack(side="right", padx=(0, T.px(9)))

    def _setup_browse(self):
        self.panel._browse()
        self.setup_folder.set(self.panel.cfg["output_dir"])

    def _setup_hotkey(self, holder):
        self.setup_hotkey = U.HotkeyField(
            holder, self.panel._pretty(self.cfg.get("hotkey", "")),
            command=lambda f: self.panel._capture("hotkey", f), width=110)
        self.setup_hotkey.pack(side="right")

    def _setup_monitor(self, holder):
        U.Button(holder, "Identify", self.panel._identify,
                 variant="ghost").pack(side="right")
        self.setup_monitor = U.Select(holder, ["Loading\u2026"], 0,
                                      command=self._setup_pick_monitor,
                                      width=240)
        self.setup_monitor.pack(side="right", padx=(0, T.px(9)))

    def _setup_pick_monitor(self, i):
        self.panel.monitor.set_values(self.panel.monitor.values, i)
        self.panel._mark("monitor", i)

    def _start_buffering(self):
        """Writes config.json -- which is what makes first_run false for ever
        after, with no new flag and no migration. That is the existing design
        and it is the right one."""
        nabd.save_config(self.panel.cfg)
        self.panel.start = dict(self.panel.cfg)
        self.panel.dirty.clear()
        self.panel._refresh_footer()
        self.first_run = False
        self.setup_box.pack_forget()
        self.hero_box.pack(fill="x")
        self.recent_box.pack(fill="x")
        self._set_status(True)

    # -- sections ----------------------------------------------------------

    def show(self, name):
        if name not in W.NAV or name == self.section:
            return
        if self.section and self.section in self._panes:
            self._panes[self.section].pack_forget()
        self.section = name
        for key, item in self._nav.items():
            on = key == name
            bg = T.RAISED if on else RAIL_BG
            item["row"].configure(bg=bg)
            item["body"].configure(bg=bg)
            item["bar"].configure(bg=T.PURPLE_LIGHT if on else RAIL_BG)
            item["label"].configure(
                bg=bg, fg=T.TEXT if on else T.TEXT_MUTED,
                font=T.font("label", T.FONT_UI_MEDIUM if on else None))
        self._panes[name].pack(fill="both", expand=True)

    # -- lifecycle ---------------------------------------------------------

    def _pump(self):
        """Drain what the hydrate worker has finished.

        The drawer's own _pump is a prewarm state machine - it holds results
        back mid-slide and drives the dismissal - and none of that means
        anything here. Applying the batch is the part worth sharing, and that
        is _apply_batch.
        """
        batch = []
        try:
            while True:
                batch.append(self.panel._results.get_nowait())
        except queue.Empty:
            pass
        if batch:
            self.panel._apply_batch(batch)
            if self.first_run and getattr(self, "setup_monitor", None):
                self.setup_monitor.set_values(self.panel.monitor.values,
                                              self.panel.monitor.current())
        try:
            self._pump_id = self.root.after(100, self._pump)
        except tk.TclError:
            pass

    def _watch(self):
        """Somebody launched the exe again. Come to the front."""
        try:
            stamp = nabd.WINDOW_TRIGGER.stat().st_mtime_ns
        except OSError:
            stamp = None
        if stamp and stamp != getattr(self, "_trigger_stamp", None):
            if getattr(self, "_trigger_stamp", None) is not None:
                self.raise_window()
            self._trigger_stamp = stamp
        elif not hasattr(self, "_trigger_stamp"):
            self._trigger_stamp = stamp
        try:
            self.root.after(150, self._watch)
        except tk.TclError:
            pass

    def raise_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def _set_status(self, running):
        self.status_dot.configure(fg=T.PURPLE_LIGHT if running else T.WARN)
        self.status_text.configure(text="Buffering" if running
                                   else "Not started")

    def save(self):
        self.panel.save()

    def quit_app(self):
        """Stop the app itself, not just this window."""
        try:
            nabd.QUIT_TRIGGER.write_text(str(time.time()), encoding="utf-8")
        except OSError as exc:
            nabd.log(f"could not ask nab'd to quit: {exc}")
        self.close()

    def close(self):
        self.remember_geometry()
        if self._pump_id:
            try:
                self.root.after_cancel(self._pump_id)
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def remember_geometry(self):
        """Never stores a maximised or iconified size -- save_geometry returns
        None for those, and None means 'use the default' on the way back."""
        geo = W.save_geometry(self.root)
        if geo is None or geo == self.cfg.get("window_geometry"):
            return
        self.panel.cfg["window_geometry"] = geo
        self.cfg["window_geometry"] = geo
        try:
            nabd.save_config(self.panel.cfg)
        except OSError as exc:
            nabd.log(f"could not store the window geometry: {exc}")

    def run(self):
        self.root.mainloop()


_KEYWORDS = {
    "Home": "status buffer recent nabs quit tray",
    "Capture": "folder length disk sound buffer",
    "Video": "monitor screen quality frame rate fps encoder",
    "Audio": "speakers microphone mic sync offset volume",
    "Hotkeys": "key bind shortcut insert",
    "App": "startup version licence license ffmpeg notices",
}

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def nabd_autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, "Nabd")
        return True
    except Exception:
        return False


def set_autostart(on):
    """The Run key, which is where the installer writes it too.

    --autostart is what keeps a sign-in launch from opening this window, so it
    has to be part of the value rather than something main() infers.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                exe = Path(sys.executable)
                if not nabd.FROZEN:
                    return False        # nothing sensible to register
                winreg.SetValueEx(k, "Nabd", 0, winreg.REG_SZ,
                                  '"%s" --autostart' % exe)
            else:
                try:
                    winreg.DeleteValue(k, "Nabd")
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        nabd.log(f"could not write the startup entry: {exc}")
        return False


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    # One window. A second launch raises this one through WINDOW_TRIGGER.
    handle = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                 nabd.WINDOW_MUTEX)
    if not handle or ctypes.windll.kernel32.GetLastError() == 183:
        nabd.signal_window()
        return 0
    first_run = not nabd.CONFIG_PATH.exists()
    cfg = nabd.load_config()
    Window(cfg, first_run=first_run).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
