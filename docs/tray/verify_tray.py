# -*- coding: utf-8 -*-
"""Tests for the tray menu model, and the spec's numbers.

    python verify_tray.py

The Tk view is a renderer with no decisions in it, so everything worth
testing is here and runs on any machine -- including the CI box that has no
display and the laptop that is not Windows.
"""
from __future__ import annotations
import sys

from nabd_tray_model import (Menu, State, place, human_duration, clock,
                             WIDTH, ROW_H, SEP_H, STATUS_H, PAD, ITEM, SEP, STATUS)

ok = 0


def check(label, cond, detail=""):
    global ok
    if cond:
        ok += 1
        return
    print("FAIL  %s  %s" % (label, detail))
    raise SystemExit(1)


# ── labels tell the truth ────────────────────────────────────────────────
check("full buffer", Menu.build(State(True, 60, 60)).rows[2].label == "Nab last minute")
check("partial buffer names what you get",
      Menu.build(State(True, 22, 60)).rows[2].label == "Nab last 22 seconds")
check("90 s buffer", Menu.build(State(True, 90, 120)).rows[2].label == "Nab last 1:30 minutes")
check("2 min buffer", Menu.build(State(True, 120, 120)).rows[2].label == "Nab last 2 minutes")
check("singular second", human_duration(1) == "1 second")
check("empty buffer names the ACTION, not 0 seconds",
      Menu.build(State(False, 0, 60)).rows[2].label == "Nab last minute",
      Menu.build(State(False, 0, 60)).rows[2].label)
check("clock", clock(22) == "0:22" and clock(60) == "1:00" and clock(95) == "1:35")

# ── state ────────────────────────────────────────────────────────────────
rec = Menu.build(State(True, 60, 60))
pau = Menu.build(State(False, 0, 60))
check("toggle verb flips", rec.rows[3].label == "Pause recording"
      and pau.rows[3].label == "Resume recording")
check("nab disabled with nothing buffered", not pau.rows[2].enabled)
check("nab enabled with a buffer", rec.rows[2].enabled)
check("nab disabled while paused even if bytes remain",
      not Menu.build(State(False, 60, 60)).rows[2].enabled)
check("settings is the default item",
      [r.key for r in rec.rows if r.default] == ["settings"])
check("one primary only", sum(1 for r in rec.rows if r.primary) == 1)
check("six interactive rows", len([r for r in rec.rows if r.kind == ITEM]) == 6)
check("status is not an item", rec.rows[0].kind == STATUS and not rec.rows[0].focusable)

t, buf, fill = rec.status_text()
check("status recording", (t, buf) == ("Recording", "1:00") and fill == 1.0)
t, buf, fill = Menu.build(State(True, 22, 60)).status_text()
check("status filling", (t, buf) == ("Recording", "0:22") and abs(fill - 22 / 60) < 1e-9)
t, buf, fill = pau.status_text()
check("status paused", t == "Paused" and fill == 0.0)

# ── keyboard ─────────────────────────────────────────────────────────────
f = rec.focusables()
check("focus skips separators and the status block",
      all(rec.rows[i].kind == ITEM for i in f))
check("first/last", rec.first() == f[0] and rec.last() == f[-1])
check("down wraps", rec.move(f[-1], +1) == f[0])
check("up wraps", rec.move(f[0], -1) == f[-1])
check("down from nothing lands on the first", rec.move(None, +1) == f[0])
check("up from nothing lands on the last", rec.move(None, -1) == f[-1])
pf = pau.focusables()
check("a disabled row is never focused", rec.rows[2].focusable and 2 not in pf)
check("paused menu still navigable", len(pf) == 5 and pau.move(pf[-1], +1) == pf[0])

check("type-ahead finds Settings", rec.rows[rec.type_ahead(None, "s")].key == "settings")
check("type-ahead is case-insensitive",
      rec.type_ahead(None, "S") == rec.type_ahead(None, "s"))
# Every row currently starts with a different letter, so pressing the same key
# again must wrap all the way round and land back on the same row rather than
# returning None -- that is what a native menu does.
i_set = rec.type_ahead(None, "s")
check("type-ahead wraps back to the only match", rec.type_ahead(i_set, "s") == i_set)
check("type-ahead skips a disabled row", pau.type_ahead(None, "n") is None,
      "paused: 'Nab last minute' is disabled, so n must match nothing")
check("type-ahead ignores punctuation", rec.type_ahead(None, "\u2026") is None)
check("type-ahead misses cleanly", rec.type_ahead(None, "z") is None)

# ── hit testing ──────────────────────────────────────────────────────────
nab = rec.rows[2]
check("hit inside a row", rec.row_at(nab.y + 2) == 2)
check("hit on a separator is nothing", rec.row_at(rec.rows[1].y + 1) is None)
check("hit on the status block is nothing", rec.row_at(rec.rows[0].y + 1) is None)
check("hit below the last row", rec.row_at(10_000) is None)

# ── geometry ─────────────────────────────────────────────────────────────
check("width", rec.width == WIDTH == 248)
expect = PAD * 2 + STATUS_H + 3 * SEP_H + 6 * ROW_H
check("height is the sum of its parts", rec.height == expect, "%d vs %d" % (rec.height, expect))
check("rows are contiguous",
      all(rec.rows[i].y + rec.rows[i].height == rec.rows[i + 1].y
          for i in range(len(rec.rows) - 1)))
check("first row starts after the padding", rec.rows[0].y == PAD)
check("last row ends before the padding", rec.rows[-1].y + rec.rows[-1].height + PAD == rec.height)

# ── placement: the part that is actually easy to get wrong ───────────────
W, H = rec.width, rec.height
WORK = (0, 0, 1920, 1040)                      # 1080 screen, 40 px taskbar
x, y = place(1900, 1035, W, H, WORK)
check("opens up and left from the tray", x == 1900 - W and y == 1035 - H)
check("never under the taskbar", y + H <= WORK[3], "%d + %d > %d" % (y, H, WORK[3]))
check("stays on screen", x >= WORK[0] and x + W <= WORK[2])

x, y = place(12, 1035, W, H, WORK)             # tray on the left
check("flips right when there is no room left", x == 12)
x, y = place(960, 8, W, H, (0, 0, 1920, 1040))  # taskbar at the top
check("flips down when there is no room above", y == 8)

SECOND = (-1920, -200, 0, 880)                  # a monitor up and to the left
x, y = place(-30, 870, W, H, SECOND)
check("works on a negative-origin monitor",
      SECOND[0] <= x and x + W <= SECOND[2] and SECOND[1] <= y and y + H <= SECOND[3],
      "(%d,%d)" % (x, y))

TINY = (0, 0, 200, 200)                         # smaller than the menu
x, y = place(190, 190, W, H, TINY)
check("clamps to a work area smaller than the menu", x == TINY[0] and y == TINY[1])

# ── bad input is refused, not rendered ───────────────────────────────────
for bad in (dict(buffered_s=-1), dict(buffered_s=61), dict(capacity_s=0)):
    try:
        State(**bad)
    except ValueError:
        pass
    else:
        check("State rejects %r" % bad, False)
    ok += 1

print("%d checks passed" % ok)
print("menu is %d x %d logical px at 100%% DPI" % (W, H))
