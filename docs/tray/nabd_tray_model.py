# -*- coding: utf-8 -*-
"""nab'd tray menu -- every decision, with no toolkit attached.

The Tk file is a renderer. Everything that can be got *wrong* lives here:
which rows exist, what they say, which are disabled, where the keyboard goes
next, and how big the window ends up. All of it is pure stdlib, so it is
testable on any machine -- which matters, because a tray menu is awkward to
test by hand and easy to regress.

    from nabd_tray_model import Menu, State
    m = Menu.build(State(recording=True, buffered_s=22, capacity_s=60))
    m.rows          -> the rows to draw
    m.width, m.height
    m.move(idx, +1) -> the next focusable row

Sizes are in logical pixels at 100% DPI. Multiply by the monitor's scale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# ── metrics, in logical px at 100% DPI ───────────────────────────────────
WIDTH = 248
PAD = 5                 # gap between the window edge and the rows
ROW_H = 30
SEP_H = 11              # 1 px rule with 5 px either side
STATUS_H = 56           # the block: 19 px mark row + meter + padding
RADIUS = 8
ROW_RADIUS = 5
ROW_PAD_X = 11
GAP = 10                # label to icon / label to accelerator
METER_H = 4
MARK = 19
TICK_W = 13

# type, as (family-role, pixel size). Negative sizes in Tk mean pixels.
FONT_ROW = ("ui", 13)
FONT_ROW_PRIMARY = ("ui-medium", 13)
FONT_STATUS = ("ui-medium", 13)
FONT_MONO = ("mono", 11)
FONT_KEY = ("mono", 10.5)

# ── colour, from the nab'd palette ───────────────────────────────────────
# These mirror nabd_tokens.py. Import from there rather than re-typing them
# if it already carries these names; they are here so the model is standalone.
C = {
    "menu":      "#1C1C21",   # the window
    "border":    "#33333A",
    "rule":      "#33333A",
    "hover":     "#26262B",
    "text":      "#E8E4DC",
    "muted":     "#9A958C",
    "faint":     "#6B6760",
    "lit":       "#9B6BD8",   # purple-light -- anything that must be SEEN
    "deep":      "#4E2A7D",   # the primary row's hover fill
    "key":       "#DCCCF2",   # accelerator on the hovered primary row
    "meter_bg":  "#33333C",
    "meter_off": "#57545C",
    "mark_off":  "#57545C",
}

SEP = "sep"
STATUS = "status"
ITEM = "item"


@dataclass(frozen=True)
class State:
    """What the app knows when the menu opens."""
    recording: bool = True
    buffered_s: int = 60          # seconds actually in the ring buffer
    capacity_s: int = 60          # the configured buffer length
    hotkey: str = "Alt+Ins"

    def __post_init__(self):
        if self.capacity_s <= 0:
            raise ValueError("capacity_s must be positive")
        if not 0 <= self.buffered_s <= self.capacity_s:
            raise ValueError("buffered_s %r outside 0..%d"
                             % (self.buffered_s, self.capacity_s))

    @property
    def fill(self) -> float:
        return self.buffered_s / float(self.capacity_s)


@dataclass
class Row:
    kind: str                     # ITEM | SEP | STATUS
    key: str = ""                 # stable id the app dispatches on
    label: str = ""
    accel: str = ""
    enabled: bool = True
    primary: bool = False
    default: bool = False         # bold; what a double-click on the icon does
    height: int = ROW_H
    y: int = 0

    @property
    def focusable(self) -> bool:
        return self.kind == ITEM and self.enabled


def human_duration(seconds: int) -> str:
    """'22 seconds', 'minute', '2 minutes', '1:30 minutes'.

    The menu promises what you will actually get, so this has to be honest
    about partial buffers rather than rounding up to the configured length.
    """
    s = int(seconds)
    if s < 60:
        return "%d seconds" % s if s != 1 else "1 second"
    m, r = divmod(s, 60)
    if r == 0:
        return "minute" if m == 1 else "%d minutes" % m
    return "%d:%02d minutes" % (m, r)


def clock(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return "%d:%02d" % (m, s)


@dataclass
class Menu:
    rows: list
    state: State
    width: int = WIDTH

    # ── construction ─────────────────────────────────────────────────────
    @classmethod
    def build(cls, state: State) -> "Menu":
        has_buffer = state.recording and state.buffered_s > 0
        rows = [
            Row(STATUS, key="status", height=STATUS_H),
            Row(SEP, height=SEP_H),
            # The reason the app exists. Named for what is ACTUALLY buffered:
            # offering "last minute" 22 s in is a promise the app cannot keep.
            # With nothing buffered it falls back to the configured length --
            # the row then names the ACTION, which is what a disabled row is
            # for. "Nab last 0 seconds" is not a thing anyone should read.
            Row(ITEM, key="nab",
                label="Nab last %s" % human_duration(
                    state.buffered_s if has_buffer else state.capacity_s),
                accel=state.hotkey, enabled=has_buffer, primary=True),
            # a verb, not a tick beside a noun -- "Recording ✓" never said what
            # clicking it would do.
            Row(ITEM, key="toggle",
                label="Pause recording" if state.recording else "Resume recording"),
            Row(SEP, height=SEP_H),
            Row(ITEM, key="folder", label="Open nabs folder"),
            Row(ITEM, key="settings", label="Settings…", default=True),
            Row(ITEM, key="log", label="View log"),
            Row(SEP, height=SEP_H),
            Row(ITEM, key="quit", label="Quit nab’d"),
        ]
        y = PAD
        for r in rows:
            r.y = y
            y += r.height
        return cls(rows=rows, state=state)

    @property
    def height(self) -> int:
        return sum(r.height for r in self.rows) + 2 * PAD

    # ── keyboard ─────────────────────────────────────────────────────────
    def focusables(self):
        return [i for i, r in enumerate(self.rows) if r.focusable]

    def first(self) -> Optional[int]:
        f = self.focusables()
        return f[0] if f else None

    def last(self) -> Optional[int]:
        f = self.focusables()
        return f[-1] if f else None

    def move(self, current: Optional[int], step: int) -> Optional[int]:
        """Next focusable row, wrapping. Separators and disabled rows are
        skipped -- a menu that lets you land on a rule is broken."""
        f = self.focusables()
        if not f:
            return None
        if current is None or current not in f:
            return f[0] if step > 0 else f[-1]
        return f[(f.index(current) + step) % len(f)]

    def type_ahead(self, current: Optional[int], ch: str) -> Optional[int]:
        """Jump to the next focusable row starting with `ch`, wrapping.

        Native menus do this and people use it without noticing. Mnemonics
        (underlined letters) are NOT implemented -- see TRAY.md.
        """
        ch = (ch or "").lower()
        if not ch.isalnum():
            return None
        f = self.focusables()
        if not f:
            return None
        start = (f.index(current) + 1) if current in f else 0
        order = f[start:] + f[:start]
        for i in order:
            if self.rows[i].label.lower().startswith(ch):
                return i
        return None

    def row_at(self, y: int) -> Optional[int]:
        for i, r in enumerate(self.rows):
            if r.y <= y < r.y + r.height:
                return i if r.focusable else None
        return None

    # ── the status block ─────────────────────────────────────────────────
    def status_text(self):
        s = self.state
        return ("Recording" if s.recording else "Paused",
                clock(s.buffered_s) if s.recording else "——",
                s.fill if s.recording else 0.0)


# ── geometry for the popup ───────────────────────────────────────────────
def place(cursor_x: int, cursor_y: int, w: int, h: int, work) -> tuple:
    """Where to put the window, given the cursor and the monitor's WORK area.

    Grows up and left: the tray is already at the corner of the work area, so
    every other direction runs off-screen. `work` is (left, top, right, bottom)
    of the work area -- NOT the screen. Using screen height opens the menu
    underneath the taskbar, which is the classic version of this bug.
    """
    left, top, right, bottom = work
    x = cursor_x - w
    y = cursor_y - h
    if x < left:                       # tray on the left, or a narrow monitor
        x = min(cursor_x, right - w)
    if y < top:                        # taskbar at the top
        y = min(cursor_y, bottom - h)
    x = max(left, min(x, right - w))
    y = max(top, min(y, bottom - h))
    return int(x), int(y)
