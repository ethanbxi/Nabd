"""The main window: is it a shell around the drawer's widgets, or a second UI?

    python _test/window_test.py

WINDOW.md section 6 lists what breaks this design, and that list is what these
checks are. The whole approach is cheap only because the window reuses the
group builders -- two settings UIs that drift apart is the failure it exists to
avoid, and it is the kind of failure that looks fine on the day it is written.
"""
import ctypes
import inspect
import sys
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass
ctypes.windll.shcore.SetProcessDpiAwareness(2)

import nabd                          # noqa: E402
import nabd_tokens as T              # noqa: E402
import nabd_window as NW             # noqa: E402
import settings as S                 # noqa: E402
import window as Wn                  # noqa: E402

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def reuse():
    """Section 6.1: copying a builder instead of passing a parent."""
    print("-- one implementation of each group --")
    src = (APP / "window.py").read_text(encoding="utf-8")
    for group in ("capture", "video", "audio", "hotkeys", "hero", "recent"):
        check("window.py does not define its own _build_%s" % group,
              ("def _build_%s" % group) not in src)
        check("...and calls the Panel's", "_build_%s(" % group in src)
    # App is the exception: it is the only group the drawer does not have.
    check("App is built here, because the drawer has no such group",
          "def _build_app" in src and not hasattr(S.Panel, "_build_app"))
    check("the builders still take a parent",
          all(len(inspect.signature(getattr(S.Panel, "_build_" + g)).parameters)
              >= 2 for g in ("capture", "video", "audio", "hotkeys")))


def metrics():
    """Section 6.2: widening the control column forks the row grammar."""
    print("\n-- the numbers come from nabd_window --")
    check("CONTROL_COL is unchanged at 344",
          T.CONTROL_COL == 344 == NW.CONTROL_COL,
          "tokens %d, window %d" % (T.CONTROL_COL, NW.CONTROL_COL))
    check("the content column is the drawer's width plus the rail",
          NW.WINDOW_W - NW.RAIL_W == 664
          and NW.WINDOW_W - NW.RAIL_W - 2 * NW.CONTENT_PAD == 624,
          "%d rail + %d content" % (NW.RAIL_W, NW.WINDOW_W - NW.RAIL_W))
    # Code only: the module docstring quotes the arithmetic on purpose, and a
    # naive grep counts that as re-deriving it.
    import io as _io
    import tokenize
    code = []
    with open(APP / "window.py", "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                code.append(tok.string)
    code = " ".join(code)
    hard = [n for n in ("860", "640", "820", "560", "196", "680")
            if n in code]
    check("no metric is re-derived in window.py", not hard, repr(hard))


def geometry():
    """Section 6.3: a window remembered on an unplugged monitor."""
    print("\n-- geometry, and the monitor that went away --")
    mons = [(0, 0, 2560, 1400), (-2560, 0, 2560, 1400)]
    w, h, x, y = NW.clamp_to_visible((860, 640, 9000, 5000), mons)
    check("a rect off every monitor is pulled back",
          any(x >= m[0] and x < m[0] + m[2] for m in mons),
          "-> +%d+%d" % (x, y))
    keep = NW.clamp_to_visible((860, 640, 100, 100), mons)
    check("a rect already on screen is left alone", keep == (860, 640, 100, 100),
          str(keep))
    small = NW.clamp_to_visible((200, 100, 0, 0), mons)
    check("never smaller than the minimum",
          small[0] >= NW.MIN_W and small[1] >= NW.MIN_H, str(small[:2]))
    check("work areas, not full bounds, are what the app offers",
          all("work" in m for m in nabd.list_monitors()),
          str([m.get("work") for m in nabd.list_monitors()][:1]))
    # A maximised size must never be stored, or it comes back as the default.
    root = tk.Tk()
    root.geometry("900x700+80+60")
    root.update()
    check("a normal size is saved", NW.save_geometry(root) is not None)
    root.state("zoomed")
    root.update()
    check("a maximised size is not", NW.save_geometry(root) is None)
    root.destroy()


def config():
    """Section 6.6: a setup_complete key would show first run after an update."""
    print("\n-- the config, and the key that must not exist --")
    check("window_geometry is there, empty",
          nabd.DEFAULTS.get("window_geometry") == "")
    check("no setup_complete key", "setup_complete" not in nabd.DEFAULTS)
    check("first run is still the absence of the file",
          "CONFIG_PATH.exists()" in (APP / "nabd.py").read_text(
              encoding="utf-8"))
    check("no config_version bump was needed",
          nabd.DEFAULTS["config_version"] == 2)


def launch():
    """Section 2, and 6.5: --autostart must stay silent."""
    print("\n-- which launch opens the window --")
    cases = [(["Nabd.exe"], True, True, "launched by hand"),
             (["Nabd.exe"], False, True, "first run"),
             (["Nabd.exe", "--autostart"], True, False, "sign-in"),
             (["Nabd.exe", "--autostart"], False, True, "sign-in, unconfigured")]
    for argv, cfg_there, want, what in cases:
        check("%s -> %s" % (what, "window" if want else "tray only"),
              nabd.wants_window(argv, cfg_there) == want)
    check("the old name still resolves", nabd.wants_panel is nabd.wants_window)
    check("--window is a role",
          '"--window" in sys.argv' in (APP / "nabd.py").read_text(
              encoding="utf-8"))
    check("WINDOW_SHOW sits beside SETTINGS_SHOW",
          nabd.WINDOW_SHOW != nabd.SETTINGS_SHOW and bool(nabd.WINDOW_SHOW))


def built(first_run):
    root_cfg = nabd.load_config()
    win = Wn.Window(root_cfg, first_run=first_run)
    for _ in range(220):
        win.root.update()
        time.sleep(0.01)
    return win


def panes():
    print("\n-- the panes at the default size --")
    win = built(False)
    try:
        check("every section has a pane",
              set(win._panes) == set(NW.NAV), str(sorted(win._panes)))
        check("the groups came from the embedded Panel",
              [g["title"] for g in win.panel.groups]
              == ["capture", "video", "audio", "hotkeys", "app"],
              str([g["title"] for g in win.panel.groups]))
        check("the panel knows it is embedded", win.panel.embedded)
        check("it never made a window of its own",
              win.panel.root is win.root)
        # Section 6.4: a pane that scrolls at the default size means the group
        # is doing too much - fix the group, not the container.
        win.root.geometry("%dx%d" % (T.px(NW.WINDOW_W), T.px(NW.WINDOW_H)))
        for _ in range(60):
            win.root.update()
            time.sleep(0.01)
        avail = win.content.winfo_height()
        for name in NW.NAV:
            win.show(name)
            for _ in range(30):
                win.root.update()
                time.sleep(0.005)
            need = win._panes[name].inner.winfo_reqheight()
            check("%s fits without scrolling" % name, need <= avail,
                  "needs %dpx of %dpx" % (need, avail))
        # The control column is what makes the cards identical.
        cols = {r.control.winfo_width() for r in win.panel.rows
                if r.control.winfo_ismapped()}
        check("rows still use the 344px control column",
              all(abs(c - T.px(T.CONTROL_COL)) <= 1 for c in cols),
              str(sorted(cols)))
        # The footer is shared with the Panel, not reimplemented.
        win.panel._mark("clip_seconds", 60)
        win.root.update()
        check("editing marks the shared footer",
              "unsaved" in win.dirty_label.cget("text"),
              repr(win.dirty_label.cget("text")))
        win.panel._mark("clip_seconds", root_cfg_value(win))
        win.root.update()
        check("and clears again", win.dirty_label.cget("text") == "No changes")
    finally:
        win.root.destroy()


def root_cfg_value(win):
    return win.panel.start.get("clip_seconds", 300)


def first_run_pane():
    print("\n-- first run --")
    win = built(True)
    try:
        check("the setup card replaces the hero",
              win.setup_box.winfo_ismapped()
              and not win.hero_box.winfo_ismapped())
        n = len(nabd.list_monitors())
        has_row = hasattr(win, "setup_monitor")
        check("the monitor row appears only with more than one display",
              has_row == (n > 1), "%d display(s), row %s"
              % (n, "shown" if has_row else "hidden"))
        check("the rail stays usable during setup",
              all(i["label"].cget("state") != "disabled"
                  for i in win._nav.values()))
        check("the status reads not started",
              win.status_text.cget("text") == "Not started"
              or not win.first_run)
    finally:
        win.root.destroy()


def main():
    reuse()
    metrics()
    geometry()
    config()
    launch()
    panes()
    first_run_pane()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
