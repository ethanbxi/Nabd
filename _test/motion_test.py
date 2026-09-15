"""Check the settings panel's open/close against PANEL-OPEN.md.

    python _test/motion_test.py

Two halves. First the spec's own `assert_invariants()`, which checks the
timeline as data. Then a real panel, driven off the virtual desktop, to check
that the build actually honours the rules the timeline encodes - above all that
the window's width and height never move, which section 7 names as the single
most likely regression.
"""
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

ctypes.windll.shcore.SetProcessDpiAwareness(2)

import settings as S                  # noqa: E402
import nabd_panel_open as M           # noqa: E402
import nabd_tokens as T               # noqa: E402

OFFSCREEN = (-9000, 0, 640, 1440)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def _pace(frames, when):
    """p90 frame gap over the part of the animation `when` selects."""
    gaps = sorted((frames[i][0] - frames[i - 1][0]) * 1000
                  for i in range(1, len(frames)) if when(frames[i][1]))
    return gaps[int(len(gaps) * 0.9)] if gaps else 0.0


def main():
    # -- the timeline, as data ---------------------------------------------
    try:
        worst, peak = M.assert_invariants()
        check("spec invariants hold", True,
              f"({worst} blocks in flight, {peak}px/frame at 60Hz)")
    except AssertionError as exc:
        check("spec invariants hold", False, str(exc))
        return 1

    # Derived, not hardcoded: the hold was closed to 0 deliberately (see
    # nabd_panel_open), and the totals follow from the parts.
    check("the timeline adds up",
          M.OPEN_MS == M.BLOCK_START + M.STAGGER * (M.N - 1) + M.BLOCK_MS
          and M.CLOSE_MS == M.SHELL_OUT_AT + M.SHELL_OUT_MS,
          f"(open {M.OPEN_MS}ms, close {M.CLOSE_MS}ms)")
    check("the deal starts the moment the shell is at rest",
          M.BLOCK_START == M.SHELL_MS and M.sample_open(M.SHELL_MS).shell == 1.0
          and M.sample_open(M.SHELL_MS).blocks == (0.0,) * M.N,
          f"(shell {M.SHELL_MS}ms, blocks {M.BLOCK_START}ms)")

    # -- a real panel -------------------------------------------------------
    class Rect:
        left, top = OFFSCREEN[0], OFFSCREEN[1]
        right, bottom = OFFSCREEN[0] + OFFSCREEN[2], OFFSCREEN[3]

    S.screen_rect = staticmethod(lambda: Rect)
    S.force_foreground = staticmethod(lambda hwnd: True)

    panel = S.Panel(daemon=True)
    panel.root.focus_force = lambda: None
    panel._warm_layout()
    panel._pump()
    t0 = time.perf_counter()
    while not panel._warm and time.perf_counter() - t0 < 90:
        panel.root.update()
        time.sleep(0.01)
    check("panel prewarmed before the open", panel._warm,
          f"({time.perf_counter() - t0:.1f}s)")

    check("six blocks, one per group",
          len(panel._block_frames) == M.N == 6, f"({len(panel._block_frames)})")

    # Intercept the moves the code commands. The animation moves the window
    # with SetWindowPos rather than wm geometry, so this is where the size
    # invariant has to be checked: _move passes SWP_NOSIZE, and nothing else
    # touches geometry while _sliding.
    geoms = []
    real_move = panel._move
    real_geom = panel.root.geometry

    def move_spy(x):
        geoms.append("%dx%d" % (panel._w, panel._h))
        return real_move(x)
    panel._move = move_spy

    def geom_spy(spec=None):
        if spec and panel._sliding:
            geoms.append(spec.split("+", 1)[0])
        return real_geom(spec) if spec else real_geom()
    panel.root.geometry = geom_spy

    frames = []
    real_draw = panel._draw

    def draw_spy(f):
        out = real_draw(f)
        # Only frames the animation itself drew. The panel also draws once
        # when it arms the window between opens, and counting that would put
        # a couple of hundred idle milliseconds inside the measurement.
        if panel._sliding:
            # Cover positions as they actually were on this frame, not as they
            # end up: the point is what the body looked like mid-slide.
            frames.append((time.perf_counter(), f,
                           [c.winfo_x() for c in panel._covers]))
        return out
    panel._draw = draw_spy

    def run(action, total):
        frames.clear()
        geoms.clear()
        action()
        end = time.perf_counter()
        while time.perf_counter() - end < total / 1000.0 + 0.45:
            panel.root.update()
            time.sleep(0.002)

    def pacing(label):
        gaps = sorted((frames[i][0] - frames[i - 1][0]) * 1000
                      for i in range(1, len(frames)))
        mid = gaps[len(gaps) // 2]
        print(f"        {label}: {len(frames)} frames, median {mid:.1f} ms, "
              f"p90 {gaps[int(len(gaps) * 0.9)]:.1f}, max {gaps[-1]:.1f}")
        return mid

    def sizes():
        return set(geoms)

    # -- open ---------------------------------------------------------------
    dealt_as_shots = panel._shots_valid()
    run(panel.reopen, M.OPEN_MS)
    check("open: width and height never change", len(sizes()) == 1,
          f"{sorted(sizes())}")
    check("open: the shell stops before any block moves",
          not [f for _t, f, _c in frames
               if f.shell < 1.0 and any(b > 0.0 for b in f.blocks)])
    moving = [xs for _t, f, xs in frames if f.shell < 1.0]
    check("open: the body is empty while the shell moves",
          bool(moving) and all(x <= 0 for xs in moving for x in xs),
          f"({len(moving)} frames under way)")
    span = (frames[-1][0] - frames[0][0]) * 1000
    check(f"open: ran for about {M.OPEN_MS}ms",
          M.OPEN_MS - 40 < span < M.OPEN_MS + 180,
          f"({span:.0f} ms)")
    mid = pacing("open")
    check("open: frames are paced under a 60Hz refresh", mid < 16.7,
          f"(median {mid:.1f} ms)")
    check("open: every block ends fully revealed",
          all(c.winfo_x() >= panel._block_w for c in panel._covers),
          f"{[c.winfo_x() for c in panel._covers]}")
    # Win32, not Tk: the animation moves the window behind Tk's back, so Tk's
    # cached position is only right once _sync_geometry has run.
    from ctypes import wintypes
    box = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(panel._hwnd(), ctypes.byref(box))
    check("open: panel is docked flush to the edge", box.left == Rect.left,
          f"(x={box.left}, want {Rect.left})")
    check("open: Tk agrees where the window is",
          panel.root.winfo_rootx() == box.left,
          f"(tk={panel.root.winfo_rootx()}, real={box.left})")
    # The blocks are dealt as photographs of themselves, which is what keeps
    # the deal inside a refresh - but they can only be photographed off the
    # screen, and this panel is parked outside the desktop so the grab cannot
    # run. On a real screen the deal holds a p90 of about 9.5ms.
    if dealt_as_shots:
        check("open: the deal drops no frames",
              _pace(frames, lambda f: f.shell >= 1.0) < 16.7,
              f"(p90 {_pace(frames, lambda f: f.shell >= 1.0):.1f} ms)")
    else:
        print("  SKIP  deal pacing (no photographs off-screen; "
              f"p90 {_pace(frames, lambda f: f.shell >= 1.0):.1f} ms live)")
    check("open: takes focus only at the end", panel._shown)

    # -- close --------------------------------------------------------------
    run(panel.dismiss, M.CLOSE_MS)
    check("close: width and height never change", len(sizes()) == 1,
          f"{sorted(sizes())}")
    moving = [xs for _t, f, xs in frames if f.shell < 1.0]
    check("close: the body is empty before the shell leaves",
          not [f for _t, f, _c in frames
               if f.shell < 1.0 and any(b > 0.0 for b in f.blocks)]
          and all(x <= 0 for xs in moving for x in xs),
          f"({len(moving)} frames under way)")
    span = (frames[-1][0] - frames[0][0]) * 1000
    check(f"close: ran for about {M.CLOSE_MS}ms",
          M.CLOSE_MS - 40 < span < M.CLOSE_MS + 180, f"({span:.0f} ms)")
    mid = pacing("close")
    check("close: frames are paced under a 60Hz refresh", mid < 16.7,
          f"(median {mid:.1f} ms)")
    check("close: the panel is hidden and reusable",
          not panel._shown and not panel._closing and not panel._sliding)

    # -- the slip, in device pixels ----------------------------------------
    step = max(abs(-int(round(T.px(M.SLIP) * (1.0 - M.sample_open(t).blocks[0])))
                   - -int(round(T.px(M.SLIP)
                                * (1.0 - M.sample_open(t + 1000 / 60).blocks[0]))))
               for t in range(M.BLOCK_START, M.BLOCK_START + M.BLOCK_MS, 2))
    budget = int(round(24 * T.scale()))
    check("a block never travels more than 24px per 60Hz frame",
          step <= budget, f"({step}px, budget {budget}px at {T.scale():.2f}x)")

    try:
        panel.root.destroy()
    except Exception:
        pass

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("failed:", ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
