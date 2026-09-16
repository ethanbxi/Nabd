"""nab'd main window -- metrics and Win32 chrome.

The window is a second container around the widgets the docked panel already
has. Its content column is deliberately the drawer's width, so the group cards,
rows, 344 px control column and footer are the same code at the same numbers.

    860 = 196 rail + 664 content
    664 - 2*20 padding = 624 card, against the drawer's 608

Everything here that touches Win32 is a no-op off Windows, so the module
imports cleanly anywhere and the pure geometry helpers are testable.
"""
from __future__ import annotations

import sys

# ── metrics (CSS px at 96 dpi; scale with nabd_tokens.px) ────────────────
WINDOW_W, WINDOW_H = 860, 640      # default size
MIN_W, MIN_H       = 820, 560      # below this the 344 px control column stops fitting
RAIL_W             = 196
CONTENT_PAD        = 20
GROUP_MAX_W        = 680           # stop cards stretching when maximised
FOOTER_H           = 60
CONTROL_COL        = 344           # nabd_tokens.CONTROL_COL -- restated as the invariant
SEARCH_H           = 30
NAV_ITEM_H         = 32

NAV = ("Home", "Capture", "Video", "Audio", "Hotkeys", "App")

# Keep the window at least this much on screen, or a saved position from a
# monitor that is no longer attached strands it where nobody can drag it back.
KEEP_VISIBLE_X = 120
KEEP_VISIBLE_Y = 32                # roughly the title bar


# ── native title bar ─────────────────────────────────────────────────────
def apply_dark_titlebar(root) -> bool:
    """Tint the NATIVE title bar dark. Returns False off Windows / pre-20H1.

    This is the whole reason the window keeps native chrome: one call buys the
    dark bar while snap layouts, Aero Peek, the system menu, eight-edge resize
    and mixed-DPI behaviour all keep working. The banner stays
    overrideredirect -- it is non-interactive and should not read as a window.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        root.update_idletasks()                       # HWND must exist
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        val = ctypes.c_int(1)
        for attr in (20, 19):                         # 20 = 20H1+, 19 = older builds
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                return True
    except Exception:
        pass
    return False


def configure(root, title="nab'd") -> None:
    root.title(title)
    root.minsize(MIN_W, MIN_H)
    apply_dark_titlebar(root)


# ── geometry persistence ─────────────────────────────────────────────────
def parse_geometry(s: str):
    """'WxH+X+Y' -> (w, h, x, y), or None if it is not that."""
    try:
        size, x, y = s.replace("+-", "+~").split("+")
        w, h = size.split("x")
        return int(w), int(h), int(x.replace("~", "-")), int(y.replace("~", "-"))
    except Exception:
        return None


def clamp_to_visible(rect, monitors):
    """Pull a saved window rect back onto a monitor that still exists.

    `monitors` is a list of work-area rects (x, y, w, h) -- the same
    EnumDisplayMonitors data the frame-rate helper already collects, using the
    WORK area so the taskbar is not covered.

    A window remembered on a monitor that has since been unplugged otherwise
    opens at coordinates nobody can reach, which reads as "the app stopped
    opening". This is the single most common windowed-app bug.
    """
    w, h, x, y = rect
    w, h = max(w, MIN_W), max(h, MIN_H)
    if not monitors:
        return w, h, x, y

    def overlap(m):
        mx, my, mw, mh = m
        ox = min(x + w, mx + mw) - max(x, mx)
        oy = min(y + h, my + mh) - max(y, my)
        return min(ox, KEEP_VISIBLE_X) > 0 and min(oy, KEEP_VISIBLE_Y) > 0 \
            and ox >= KEEP_VISIBLE_X and oy >= KEEP_VISIBLE_Y

    if any(overlap(m) for m in monitors):
        return w, h, x, y
    mx, my, mw, mh = monitors[0]                      # primary first
    return (min(w, mw), min(h, mh),
            mx + max(0, (mw - min(w, mw)) // 2),
            my + max(0, (mh - min(h, mh)) // 3))      # a third down looks centred


def save_geometry(root) -> str | None:
    """Call on close. Never save a maximised or iconified size."""
    try:
        if root.state() != "normal":
            return None
        return root.geometry()
    except Exception:
        return None


def restore_geometry(root, saved: str | None, monitors) -> None:
    rect = parse_geometry(saved) if saved else None
    if rect is None:
        rect = (WINDOW_W, WINDOW_H, 0, 0)
        if monitors:
            mx, my, mw, mh = monitors[0]
            rect = (WINDOW_W, WINDOW_H,
                    mx + (mw - WINDOW_W) // 2, my + (mh - WINDOW_H) // 3)
    w, h, x, y = clamp_to_visible(rect, monitors)
    root.geometry("%dx%d+%d+%d" % (w, h, x, y))
