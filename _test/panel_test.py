"""Drive the rebuilt settings panel and check it.

    python _test/panel_test.py

Runs the panel in-process so the event loop can be pumped by hand: that is the
only way to scroll it, click things and read state back without a second
process in the way. Shoots the top and the bottom of the scroll so both halves
can be eyeballed against the mockups.
"""
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

ctypes.windll.shcore.SetProcessDpiAwareness(2)

import tkinter as tk                 # noqa: E402

import settings as S                # noqa: E402
import nabd_panel_open as M         # noqa: E402
import nabd_tokens as T             # noqa: E402

# --offscreen parks the panel outside the virtual desktop and neuters anything
# that could take focus, so the suite can run while a game is in the
# foreground. The three checks that assert against the real screen edge are
# skipped, since there is no real screen edge to assert against.
OFFSCREEN = "--offscreen" in sys.argv
if OFFSCREEN:
    class _Rect:
        left, top, bottom = -9000, 0, 1440
        right = -8000
    S.screen_rect = staticmethod(lambda: _Rect)
    S.force_foreground = staticmethod(lambda hwnd: True)
    tk.Misc.focus_force = lambda self: None

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")


def pump(panel, n=30):
    for _ in range(n):
        panel.root.update()


def settle(panel, seconds=2.0):
    """Pump the loop while real time passes.

    The slide and the eased scroll are timed off perf_counter, so a tight
    update() loop advances no wall clock and they never progress. Anything
    waiting on an animation has to be driven like this.
    """
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        panel.root.update()
        time.sleep(0.002)


def shoot(panel, name):
    from PIL import ImageGrab
    r = panel.root
    x, y = r.winfo_rootx(), r.winfo_rooty()
    w, h = r.winfo_width(), r.winfo_height()
    ImageGrab.grab(all_screens=False).crop((x, y, x + w, y + h)).save(
        HERE / f"{name}.png")


def _cycle_clean(panel):
    """Open, close and open again: the block column must come back identical.

    The blocks are placed, not packed, and their y positions are recomputed
    from measured heights - so a cycle that leaves one misplaced or a cover
    stranded over its block is the failure this catches.
    """
    if not panel.daemon:
        return True, ""
    before = (list(panel._block_y), list(panel._block_h))
    for _ in range(2):
        panel.dismiss()
        t0 = time.perf_counter()
        while panel._shown and time.perf_counter() - t0 < 3:
            panel.root.update(); time.sleep(0.001)
        panel.reopen()
        t0 = time.perf_counter()
        while not panel._shown and time.perf_counter() - t0 < 5:
            panel.root.update(); time.sleep(0.001)
    settle(panel, 0.4)
    after = (list(panel._block_y), list(panel._block_h))
    if after != before:
        return False, f"(column moved: {before} -> {after})"
    stuck = [M.BLOCKS[i] for i, c in enumerate(panel._covers)
             if c.winfo_x() < panel._block_w]
    if stuck:
        return False, f"(covers still over {stuck})"
    return True, ""


def _toggles(panel):
    """The trigger opens a hidden panel and closes a shown one.

    Both the hotkey and the tray menu write the same trigger file, so this is
    the behaviour of both. A press while the panel is moving does nothing.
    """
    if not panel.daemon:
        return True, ""

    def wait(shown, limit=6.0):
        """Wait for the panel to reach a state AND stop moving.

        Not just _shown: a press can be queued behind the hidden photograph
        pass as well as behind an animation, so the panel reaches the state a
        beat later than the flag flips. Waiting on _shown alone made this
        check race the capture.
        """
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < limit:
            busy = panel._sliding or panel._closing or panel._capturing
            if panel._shown == shown and not busy and not panel._pending:
                break
            panel.root.update(); time.sleep(0.001)
        settle(panel, 0.35)

    if not panel._shown:
        panel.toggle(); wait(True)
    if not panel._shown:
        return False, "(a hidden panel did not open)"
    panel.toggle(); wait(False)
    if panel._shown:
        return False, "(a shown panel did not close)"
    panel.toggle(); wait(True)
    if not panel._shown:
        return False, "(it did not open again)"

    # mid-animation: the press is remembered, not dropped, and applied once
    # the current animation lands. Two of them cancel out.
    panel.toggle()
    settle(panel, 0.06)
    if not panel._sliding:
        return False, "(expected the close to be under way)"
    panel.toggle()
    if not panel._pending:
        return False, "(a press mid-animation was dropped)"
    if not panel._closing:
        return False, "(it reversed mid-animation instead of queueing)"
    wait(False)                     # the close lands first...
    wait(True, 6.0)                 # ...then the queued press reopens it
    if not panel._shown:
        return False, "(the queued press never landed)"
    panel.toggle()                  # start a close
    settle(panel, 0.06)
    panel.toggle(); panel.toggle()  # parity: two extra presses cancel
    wait(False, 6.0)
    settle(panel, 0.5)
    if panel._shown or panel._pending:
        return False, "(two queued presses did not cancel)"
    panel.toggle(); wait(True)
    return True, ""


def main():
    panel = S.Panel(daemon=OFFSCREEN)
    panel.auto_dismiss = False
    if OFFSCREEN:                       # a daemon does not present on its own
        panel._warm_layout()
        panel.root.update()
        panel.reopen()
    # run() normally starts this; without it the async device results are never
    # drained and every check guarded by "if mons" silently skips.
    panel._pump()
    settle(panel, 5.0)          # slide in, then devices, metadata, posters

    # -- geometry ----------------------------------------------------------
    r = panel.root
    check("panel is 640px wide", r.winfo_width() == T.px(T.PANEL_W),
          f"({r.winfo_width()}px)")
    if OFFSCREEN:
        print("  SKIP  screen-edge checks (offscreen mode)")
    else:
        check("panel is full screen height",
              r.winfo_height() == r.winfo_screenheight(),
              f"({r.winfo_height()}px)")
        check("docked flush left", r.winfo_rootx() == 0,
              f"(x={r.winfo_rootx()})")

    # The control column is what the layout rests on: a row whose control is
    # paired with a button ends earlier than one that is not, so it is the
    # column's own edges that must line up, not each widget's.
    lefts = {r.control.winfo_rootx() for r in panel.rows}
    rights = {r.control.winfo_rootx() + r.control.winfo_width()
              for r in panel.rows}
    # 1px of slack: Tk's grid hands leftover space to the weighted label
    # column and the split can round differently between cards. Invisible, and
    # not worth distorting the layout to chase.
    widths = {r.control.winfo_width() for r in panel.rows}
    check("every control column shares one left edge",
          max(lefts) - min(lefts) <= 1, f"{sorted(lefts)}")
    check("every control column shares one right edge", len(rights) == 1,
          f"{sorted(rights)}")
    check("control column is 344px wide",
          max(abs(w - T.px(T.CONTROL_COL)) for w in widths) <= 1,
          f"{sorted(widths)}")

    # gutters: the scrollbar is overlaid in the right margin, not packed
    # beside the canvas, so content keeps equal margins on both sides
    card = panel.groups[0]["card"]
    gl = card.winfo_rootx() - r.winfo_rootx()
    gr = (r.winfo_rootx() + r.winfo_width()) - (card.winfo_rootx()
                                                + card.winfo_width())
    check("card gutters are symmetric", gl == gr, f"(left {gl}px, right {gr}px)")
    check("open and close leave the column intact", *_cycle_clean(panel))
    check("the hotkey toggles rather than only opening", *_toggles(panel))
    check("gutters are the spec's 16px", gl == T.px(T.PANEL_PAD), f"({gl}px)")
    check("hero spans the full content width",
          panel.hero.winfo_width() == r.winfo_width() - 2 * T.px(T.PANEL_PAD),
          f"({panel.hero.winfo_width()}px)")

    # controls paired with a button must fill the column beside it, not sit
    # at a fixed width with dead space to their left
    for name, w in (("folder field", panel.folder),
                    ("monitor select", panel.monitor)):
        col = next((r.control for r in panel.rows
                    if str(w).startswith(str(r.line))), None)
        gap = w.winfo_rootx() - col.winfo_rootx() if col else -1
        check(f"{name} fills its column", gap == 0, f"({gap}px dead space)")

    shoot(panel, "panel_top_test")

    # -- scrolling ---------------------------------------------------------
    panel.canvas.yview_moveto(1.0)
    pump(panel, 20)
    shoot(panel, "panel_bottom_test")
    hk_visible = panel.hk_open.winfo_rooty() < r.winfo_height()
    check("scrolls to the hotkeys card", hk_visible,
          f"(open-hotkey y={panel.hk_open.winfo_rooty()})")
    panel.canvas.yview_moveto(0.0)
    pump(panel, 10)

    # -- dirty tracking ----------------------------------------------------
    check("starts clean", not panel.dirty and not panel.save_btn.enabled)
    panel.length.set(0, notify=True)
    pump(panel, 10)
    check("changing nab length marks dirty", "clip_seconds" in panel.dirty)
    check("Save enables when dirty", panel.save_btn.enabled)
    check("footer counts the change",
          "1 unsaved change" in panel.dirty_label.cget("text"),
          repr(panel.dirty_label.cget("text")))
    check("discard button says Cancel",
          panel.cancel_btn.cget("text") == "Cancel")

    before = panel.per_nab
    panel.length.set(2, notify=True)
    pump(panel, 10)
    check("estimate tracks nab length", panel.per_nab > before,
          f"({S.human_bytes(before)} -> {S.human_bytes(panel.per_nab)})")
    check("returning to the original value clears dirty", not panel.dirty)
    check("footer reverts to Close",
          panel.cancel_btn.cget("text") == "Close"
          and "No changes" in panel.dirty_label.cget("text"))

    # -- audio devices -----------------------------------------------------
    # list_speakers() hands back dicts and list_microphones() hands back
    # strings. Feeding a dict to the dropdown put an unrenderable value in the
    # list (elide_right slices it and raises), wrote the dict into config.json
    # and never matched a saved device again.
    check("speaker dropdown holds strings, not dicts",
          all(isinstance(v, str) for v in panel.spk.values),
          repr(panel.spk.values[:2]))
    check("mic dropdown holds strings",
          all(isinstance(v, str) for v in panel.mic.values))
    if len(panel.spk.values) > 1:
        was = panel.spk.current()
        panel.spk._choose(1)
        pump(panel, 10)
        picked = panel.cfg.get("speaker_device")
        check("picking a speaker saves its name", isinstance(picked, str)
              and picked == panel.spk.values[1], repr(picked))
        panel.spk._choose(0)
        pump(panel, 10)
        check("the default entry saves an empty device",
              panel.cfg.get("speaker_device") == "")
        panel.spk._choose(was)
        pump(panel, 10)

        # and a saved device comes back selected on the next build
        want = panel.spk.values[1]
        names = [S.device_name(d) for d in panel.speakers]
        back = next((i + 1 for i, n in enumerate(names) if n == want), 0)
        check("a saved device is re-selected", back == 1,
              f"index {back} for {want!r}")

    # -- estimate ----------------------------------------------------------
    mons = panel.monitors
    check("device enumeration completed", bool(mons), f"({len(mons)} monitors)")
    if mons:
        m = mons[0]
        modelled = S.modelled_bytes_per_sec(m["width"], m["height"], 60, 23)
        gb = modelled * 300 / (1 << 30)
        check("1440p60 High models ~1.2 GB for 5 min", 1.1 <= gb <= 1.3,
              f"({gb:.2f} GB)")

    # -- quality names what it actually changes ----------------------------
    # Not the resolution: every preset records at the display's native size,
    # so that printed the same figure four times and read as though the preset
    # shrank the picture. It sets the encoder's CQ, which shows up as bytes.
    if mons:
        vals = panel.quality.values
        check("quality presets name a byte rate, not a resolution",
              all("/min)" in v for v in vals)
              and not any("×" in v for v in vals),
              str(vals[:2]))
        rates = []
        for v in vals:
            body = v[v.index("(~") + 2:v.index("/min)")]
            n, unit = body.split()
            rates.append(float(n) * (1024 if unit == "GB" else 1))
        check("a higher preset costs more per minute",
              all(a > b for a, b in zip(rates, rates[1:])),
              " > ".join(f"{r:.0f}" for r in rates))
        check("quality still maps to the right cq",
              S.QUALITY[panel.quality.current()][1] == panel.cfg["cq"],
              f"(cq={panel.cfg['cq']})")

    # -- toggle ------------------------------------------------------------
    was = panel.reset_toggle.get()
    panel.reset_toggle._click()
    pump(panel, 6)
    check("buffer toggle flips and marks dirty",
          panel.reset_toggle.get() != was and "reset_after_clip" in panel.dirty)
    panel.reset_toggle._click()
    pump(panel, 6)

    # -- frame rate follows the display ------------------------------------
    if mons:
        hz = panel._fps_options(240)
        check("240 Hz offers 30/60/80/120/240", hz == [30, 60, 80, 120, 240],
              str(hz))
        check("60 Hz offers only 30/60", panel._fps_options(60) == [30, 60],
              str(panel._fps_options(60)))
        check("165 Hz offers 30/55/60/165",
              panel._fps_options(165) == [30, 55, 60, 165],
              str(panel._fps_options(165)))

    # -- hotkey capture ----------------------------------------------------
    panel._capture("hotkey", panel.hk_nab)
    pump(panel, 6)
    check("capture mode shows a prompt",
          "Press keys" in panel.hk_nab.get_text())
    if OFFSCREEN:
        # event_generate needs real keyboard focus, which offscreen mode gives
        # up on purpose. Feed the handler the event it would have received.
        class _Key:
            keysym, state = "F9", 0
        panel._on_key(_Key())
    else:
        panel.root.event_generate("<KeyPress-F9>", when="now")
    pump(panel, 10)
    check("captured key commits", panel.hk_nab.get_text() == "F9",
          repr(panel.hk_nab.get_text()))
    check("captured key marks dirty", "hotkey" in panel.dirty)

    # -- reference parity ---------------------------------------------------
    # Numbers taken straight off settings-reference.html's CSS.
    check("hero is 170px tall", panel.hero.winfo_height() == T.px(170),
          f"({panel.hero.winfo_height()}px)")
    check("segmented track is 38px",
          panel.length.winfo_height() == T.px(T.CONTROL_H_SM + 8),
          f"({panel.length.winfo_height()}px)")
    # The track has to be wide enough for its own cells. A Label carries 1px
    # of padding each side that the width total did not know about, so the
    # last cell hung over the end and the selected pill lost the round of its
    # right edge to the clip.
    seg = panel.length
    need = (sum(c._w_px for c in seg.cells) + T.px(3) * (len(seg.cells) - 1)
            + T.px(3) * 2)
    check("the segmented track fits its own cells",
          seg.winfo_width() >= need,
          f"({seg.winfo_width()}px, cells need {need}px)")
    last = seg.cells[-1]
    overhang = (last.winfo_x() + last.winfo_width()
                - seg.holder.winfo_width())
    check("the last cell does not hang over the end", overhang <= 0,
          f"(overhangs by {overhang}px)")
    for i, c in enumerate(seg.cells):
        check(f"cell {i} gets the width its pill was drawn at",
              c.winfo_width() >= c._w_px,
              f"({c.winfo_width()}px, pill is {c._w_px}px)")

    check("selects are 36px", panel.quality.winfo_height() == T.px(36),
          f"({panel.quality.winfo_height()}px)")
    check("keycaps are 34px", panel.hk_open.winfo_height() == T.px(34),
          f"({panel.hk_open.winfo_height()}px)")

    # A keycap is as wide as the combination on it. A fixed width plus
    # pack_propagate(False) clipped anything longer than the combo the width
    # happened to be chosen for - "Ins" fits 110px and "Alt + Insert" does not.
    for combo in ("Ins", "Alt + Insert", "Ctrl + Alt + N",
                  "Ctrl + Alt + Shift + F12", "—"):
        panel.hk_nab.set_text(combo)
        pump(panel, 6)
        need = panel.hk_nab.label.winfo_reqwidth() + 2 * T.px(panel.hk_nab.PAD)
        check(f"the keycap fits {combo!r}",
              panel.hk_nab.winfo_width() >= need,
              f"({panel.hk_nab.winfo_width()}px, needs {need}px)")
    # ...and does not shrink to the placeholder the moment it is clicked.
    panel.hk_nab.set_text("Ctrl + Alt + Shift + F12")
    pump(panel, 6)
    wide = panel.hk_nab.winfo_width()
    panel.hk_nab.mark("capturing")
    panel.hk_nab.set_text("Press keys…")
    pump(panel, 6)
    check("the keycap holds its width while listening",
          panel.hk_nab.winfo_width() >= wide,
          f"({wide}px -> {panel.hk_nab.winfo_width()}px)")
    panel.hk_nab.mark("rest")
    panel.hk_nab.set_text(panel._pretty(panel.cfg.get("hotkey", "")))
    pump(panel, 6)

    # eyebrow tracking: .16em at 10px mono is ~1.6px on top of a 5px glyph
    import nabd_ui as UU
    eye = UU.eyebrow(panel.body, "capture")
    panel.root.update_idletasks()
    track = eye.winfo_children()[0]
    per = track.winfo_reqwidth() / 7.0
    check("eyebrow tracking is close to .16em", 6.0 <= per <= 8.0,
          f"({per:.1f}px per glyph, reference 6.6)")
    eye.destroy()

    # The timeline wash must be the translucent one, not full-strength
    # purple. Read it off the rendered image rather than the screen, so it
    # holds regardless of where the window is.
    import nabd_paint as PP
    bar = PP.timeline(T.px(400), T.px(T.CONTROL_H))
    right = bar.getpixel((T.px(380), T.px(18)))
    check("timeline wash is subdued, not full purple",
          right[0] < 0x50 and right[2] < 0x68, f"rgb{right} (target ~#37264F)")

    # -- scrollbar ----------------------------------------------------------
    overflow = panel.body.winfo_reqheight() > panel.canvas.winfo_height()
    check("scrollbar shown exactly when content overflows",
          panel.vbar.winfo_ismapped() == overflow,
          f"(overflow={overflow}, shown={bool(panel.vbar.winfo_ismapped())})")
    if overflow:
        check("scrollbar is 10px wide", panel.vbar.winfo_width() == T.px(10),
              f"({panel.vbar.winfo_width()}px)")

    # -- brand rules -------------------------------------------------------
    import nabd_tokens as TT
    check("purple is a fill, linework is purple-light",
          TT.PURPLE == "#6C3BAA" and TT.PURPLE_LIGHT == "#9B6BD8")

    panel._closing = True
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
