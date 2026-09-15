"""nab'd settings panel open/close motion, as data.

The panel docks to the left edge of the screen on a hotkey. Two phases, and the
separation between them is the whole design:

    1. the SHELL arrives  -- header, footer, empty body. Nothing in the body.
    2. the BLOCKS deal out -- each group wipes out from the panel's left edge
                              while slipping to the right (see SLIP).

Phase 1 moves the window. Phase 2 moves nothing but content, and only inside a
body that is already sitting still. They never overlap, and `assert_invariants()`
enforces it. The spec put a 40 ms hold between them as well; see HOLD_MS for why
it is 0 here.

Drive both off a real clock, never a tick counter and never chained callbacks:

    start = time.perf_counter()
    def tick():
        t = (time.perf_counter() - start) * 1000.0
        if t >= OPEN_MS:
            settle(); return
        draw(sample_open(t))
        root.after(8, tick)

Wall-clock sampling means a dropped frame skips a value instead of
desynchronising the phases, which matters because this runs on a machine that
is also running a game.
"""
from __future__ import annotations
from dataclasses import dataclass

from nabd_ease import SLIDE, LEAVE, FADE

# -- geometry (CSS px at 96 dpi; scale everything with nabd_tokens.px) ------
PANEL_W  = 640     # nabd_tokens.PANEL_W
BODY_PAD = 24      # body inset each side
BLOCK_W  = PANEL_W - 2 * BODY_PAD          # 592
# How far a block travels. NOT its full width -- see below.
# Was 56. A block slips in from the left inside a container that clips at the
# content gutter, so anything in the leftmost SLIP px is hidden until the slip
# nearly finishes and then emerges from the gutter edge with no runway. The
# hero's status dot sits 17px in: at 56 it was still clipped at t=361ms and
# appeared at ~386, which reads as the Buffering row popping in. Holding SLIP
# at or below that 17px inset means the wipe edge reveals it like everything
# else. Scales with DPI on both sides, so the relation holds at any scale.
SLIP     = 16

# The blocks, top to bottom. Order is the build order of the panel body.
BLOCKS = ("hero", "recent", "capture", "hotkeys", "video", "audio")
N = len(BLOCKS)

# -- open ------------------------------------------------------------------
SHELL_MS    = 320   # window slides in from off-screen left
# Was 40ms. The spec argues for a beat here, but SLIDE decelerates so hard
# that the panel is within 2px of docked at 292ms and only reports at rest at
# 324 - so the hold read as 76ms of dead air, not 40, and the open felt like it
# stalled before the content arrived. At 0 the two phases are adjacent rather
# than overlapping: the shell still reaches 1.0 at SHELL_MS before any block
# leaves 0.0, and assert_invariants still holds.
HOLD_MS     = 0
BLOCK_START = SHELL_MS + HOLD_MS           # 320
BLOCK_MS    = 160   # one block's wipe + slip
STAGGER     = 48    # between consecutive blocks
FADE_MS     = 180   # window alpha 0 -> 1, inside the shell slide
OPEN_MS     = BLOCK_START + STAGGER * (N - 1) + BLOCK_MS       # 720

# -- close -----------------------------------------------------------------
OUT_MS        = 110  # one block's wipe out
OUT_STAGGER   = 14   # blocks leave in reverse order, bottom first
OUT_HOLD      = 30
BLOCKS_OUT_MS = OUT_STAGGER * (N - 1) + OUT_MS                 # 180
SHELL_OUT_AT  = BLOCKS_OUT_MS + OUT_HOLD                       # 210
SHELL_OUT_MS  = 160
OUT_FADE_MS   = 120  # alpha 1 -> 0, at the tail of the shell slide
CLOSE_MS      = SHELL_OUT_AT + SHELL_OUT_MS                    # 370


@dataclass(frozen=True)
class Frame:
    """Every animated value for one instant. Nothing else should move."""
    alpha: float                # window opacity, 0..1
    shell: float                # 0 = fully off-screen left, 1 = docked
    blocks: tuple               # per-block reveal 0..1, in BLOCKS order

    # -- shell -------------------------------------------------------------
    def x(self, work_x: int = 0) -> int:
        """Panel left edge. The ONLY window value that changes. Never width."""
        return work_x - int(round(PANEL_W * (1.0 - self.shell)))

    def geometry(self, work_x: int, work_y: int, work_h: int) -> str:
        return "%dx%d+%d+%d" % (PANEL_W, work_h, self.x(work_x), work_y)

    # -- blocks ------------------------------------------------------------
    def clip_w(self, i: int, block_w: int = BLOCK_W) -> int:
        """Width of block i's clip frame. The wipe: 0 -> block_w, left to right."""
        return max(1, int(round(block_w * self.blocks[i])))

    def dx(self, i: int) -> int:
        """Block i's x inside its clip frame. -SLIP -> 0."""
        return -int(round(SLIP * (1.0 - self.blocks[i])))

    def mapped(self, i: int) -> bool:
        """False -> keep the canvas item hidden. Do not rely on clipping alone."""
        return self.blocks[i] > 0.0


def _seg(t: float, t0: float, t1: float, ease) -> float:
    if t <= t0:
        return 0.0
    if t >= t1:
        return 1.0
    return ease((t - t0) / (t1 - t0))


def sample_open(t: float) -> Frame:
    return Frame(
        alpha=_seg(t, 0, FADE_MS, FADE),
        shell=_seg(t, 0, SHELL_MS, SLIDE),
        blocks=tuple(
            _seg(t, BLOCK_START + STAGGER * i, BLOCK_START + STAGGER * i + BLOCK_MS, SLIDE)
            for i in range(N)
        ),
    )


def sample_close(t: float) -> Frame:
    # bottom block leaves first: block i waits for the (N-1-i) blocks below it
    outs = []
    for i in range(N):
        t0 = OUT_STAGGER * (N - 1 - i)
        outs.append(1.0 - _seg(t, t0, t0 + OUT_MS, LEAVE))
    return Frame(
        alpha=1.0 - _seg(t, CLOSE_MS - OUT_FADE_MS, CLOSE_MS, FADE),
        shell=1.0 - _seg(t, SHELL_OUT_AT, CLOSE_MS, LEAVE),
        blocks=tuple(outs),
    )


def timeline(sampler=sample_open, total: float = OPEN_MS, fps: int = 120):
    step = 1000.0 / fps
    t = 0.0
    while t < total:
        yield t, sampler(t)
        t += step


# -- the invariants --------------------------------------------------------
def assert_invariants() -> None:
    """The four things that, if broken, put the jank back. Run this in CI."""

    # 1. The shell is fully at rest before any block moves. This is the whole
    #    fix -- the window stops, THEN the content arrives. Closing the hold to
    #    save 40 ms makes the content look like it is chasing the panel.
    assert SHELL_MS + HOLD_MS <= BLOCK_START, "block phase overlaps the shell slide"
    for t in (SHELL_MS, BLOCK_START - 1):
        assert sample_open(t).blocks == (0.0,) * N, "a block moved during the hold"
    assert sample_open(BLOCK_START + 1).shell == 1.0, "shell still moving under the blocks"

    # 2. Closing mirrors it: the body is empty before the window moves.
    assert BLOCKS_OUT_MS + OUT_HOLD <= SHELL_OUT_AT
    assert sample_close(SHELL_OUT_AT).blocks == (0.0,) * N, "window left with content in it"

    # 3. A block slips SLIP px, not BLOCK_W. A full-width slide moves a 592 px
    #    card at ~60 px per frame and the text smears -- which is the artifact
    #    we set out to remove. The wipe is what makes the block appear; the
    #    slip is what gives it life. Raising SLIP past ~72 brings the smear back.
    assert SLIP <= 72, "SLIP that large reintroduces the horizontal smear"
    peak = max(abs(sample_open(t + 1000 / 60).dx(0) - sample_open(t).dx(0))
               for t, _ in timeline(fps=240) if BLOCK_START <= t <= BLOCK_START + BLOCK_MS)
    assert peak <= 24, "block travels %d px/frame at 60 Hz; keep it under 24" % peak

    # 4. At most four blocks in flight at once. At 30/200 (the numbers the
    #    schematic used) all six move together, which is the thing being fixed.
    worst = 0
    for t, f in timeline(fps=240):
        worst = max(worst, sum(1 for p in f.blocks if 0.0 < p < 1.0))
    assert worst <= 4, "%d blocks in flight; raise STAGGER or drop BLOCK_MS" % worst

    # 5. Ease direction. Arriving decelerates, leaving accelerates. Getting
    #    these backwards is what made the banner's exit feel choppy.
    assert SLIDE(0.5) > 0.5, "SLIDE must be front-loaded (comes to rest)"
    assert LEAVE(0.5) < 0.5, "LEAVE must be back-loaded (actually leaves)"

    return worst, peak


if __name__ == "__main__":
    worst, peak = assert_invariants()
    print("open  %4d ms   close %4d ms" % (OPEN_MS, CLOSE_MS))
    print("peak block travel %d px/frame @60Hz   max %d blocks in flight\n" % (peak, worst))
    print("   t    alpha  shell  " + "  ".join("%-7s" % b for b in BLOCKS))
    for t, f in timeline(fps=25):
        print("%4d    %.2f   %.2f   " % (t, f.alpha, f.shell)
              + "  ".join("%5.2f  " % p for p in f.blocks))
