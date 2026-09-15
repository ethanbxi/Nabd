"""Build the panel at other people's monitors and check it still holds up.

    python _test/scale_test.py

One process per configuration: a Tk interpreter caches fonts and images per
scale, so they cannot share one. Each run is parked outside the virtual
desktop, so nothing appears on screen.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# dpi, screen width, screen height - the common desktop and laptop panels
CASES = [
    (96,  1920, 1080), (96,  2560, 1440), (96,  3840, 2160),
    (120, 1920, 1080), (120, 2560, 1440),
    (144, 1920, 1080), (144, 3840, 2160),
    (168, 2560, 1440), (192, 3840, 2160),
]

CHILD = r'''
import sys, time, ctypes
sys.path.insert(0, r"{app}")
ctypes.windll.shcore.SetProcessDpiAwareness(2)
import nabd_tokens as T
_real = T.set_scale
T.set_scale = lambda _dpi, want={dpi}: _real(want)
import settings as S
import nabd_panel_open as PO

class R:
    left, top = -9000, 0
    right, bottom = -9000 + {w}, {h}
S.screen_rect = lambda: R()
S.force_foreground = lambda hwnd: None

p = S.Panel(daemon=True)
p.root.focus_force = lambda: None
p._warm_layout()
p._pump()
t0 = time.perf_counter()
while not p._warm and time.perf_counter() - t0 < 90:
    p.root.update(); time.sleep(0.01)
p.reopen()
t0 = time.perf_counter()
while time.perf_counter() - t0 < 2.0:
    p.root.update(); time.sleep(0.004)

fail = []
r = p.root
if r.winfo_width() != T.px(T.PANEL_W):
    fail.append(f"panel {{r.winfo_width()}} != {{T.px(T.PANEL_W)}}")
if r.winfo_height() != {h}:
    fail.append(f"height {{r.winfo_height()}} != {h}")
if r.winfo_width() > {w}:
    fail.append("panel wider than the screen")

# the strip lands on the cards' edges. Only a full page of three fills the
# row - fewer nabs than that means fewer tiles, left-packed at the same
# width, so what is checked then is the width itself.
tiles = [c for c in p.thumb_row.winfo_children()]
card = p.groups[0]["card"]
cl = card.winfo_rootx() - r.winfo_rootx()
cr = cl + card.winfo_width()
sl = tiles[0].winfo_rootx() - r.winfo_rootx()
sr = tiles[-1].winfo_rootx() - r.winfo_rootx() + tiles[-1].winfo_width()
tile_w, gaps = p._tile_metrics()
# A full page has to come out exactly the content width, whatever the
# scale rounds to - checked as arithmetic so it holds even on a machine
# with fewer than three nabs to show.
span = tile_w * S.PER_PAGE + sum(gaps)
if span != cr - cl:
    fail.append(f"three tiles span {{span}}, content is {{cr - cl}}")
if len(tiles) == S.PER_PAGE:
    if (sl, sr) != (cl, cr):
        fail.append(f"strip {{sl}}..{{sr}} vs cards {{cl}}..{{cr}}")
elif sl != cl or any(t.winfo_width() != tile_w for t in tiles):
    fail.append(f"{{len(tiles)}} tile(s) at "
                f"{{[t.winfo_width() for t in tiles]}}, want {{tile_w}} "
                f"from {{cl}}")

# nothing sticks out sideways. The wipe covers are parked past the right
# edge on purpose and are clipped by their own block, so they are exempt.
over = []
covers = set(str(c) for c in p._covers)
def walk(w_):
    try:
        if str(w_) in covers:
            return
        x = w_.winfo_rootx() - r.winfo_rootx()
        if w_.winfo_ismapped() and (x < 0 or x + w_.winfo_width()
                                    > r.winfo_width()):
            over.append(w_.winfo_class())
    except Exception:
        return
    for c in w_.winfo_children():
        walk(c)
walk(p.shell)
if over:
    fail.append(f"{{len(over)}} widgets overflow: {{over[:3]}}")

# the block column stacks without gaps or overlaps, and fills the width
if len(p._block_frames) != PO.N:
    fail.append(f"{{len(p._block_frames)}} blocks, want {{PO.N}}")
run = 0
for i in range(PO.N):
    if p._block_y[i] != run:
        fail.append(f"block {{i}} at y={{p._block_y[i]}}, want {{run}}")
        break
    run += p._block_h[i]
if p._block_w != cr - cl:
    fail.append(f"blocks {{p._block_w}} wide, content is {{cr - cl}}")
# and every cover is parked clear of its block once the open has settled
late = [i for i, c in enumerate(p._covers) if c.winfo_x() < p._block_w]
if late:
    fail.append(f"covers still over blocks {{late}}")

scroll = p.body.winfo_reqheight() > p.canvas.winfo_height()
print(f"RESULT|{dpi}|{w}|{h}|{{T.scale():.2f}}|{{r.winfo_width()}}|"
      f"{{p.body.winfo_reqheight()}}|{{scroll}}|{{len(tiles)}}|"
      f"{{';'.join(fail)}}")
try: p.root.destroy()
except Exception: pass
'''

def main():
    app = str(HERE.parent)
    bad = 0
    print(f"{'dpi':>4} {'screen':>11} {'scale':>6} {'panel':>6} "
          f"{'content':>8} {'scrolls':>8} {'tiles':>6}  result")
    for dpi, w, h in CASES:
        out = subprocess.run(
            [sys.executable, "-c", CHILD.format(app=app, dpi=dpi, w=w, h=h)],
            capture_output=True, text=True, timeout=240)
        line = next((l for l in out.stdout.splitlines()
                     if l.startswith("RESULT|")), None)
        if not line:
            print(f"{dpi:>4} {w}x{h:<6} CRASHED  "
                  f"{out.stderr.strip().splitlines()[-1][:70] if out.stderr else ''}")
            bad += 1
            continue
        _, d, sw, sh, scale, pw, content, scrolls, tiles, fail =             line.split("|")
        ok = "ok" if not fail else "FAIL " + fail
        print(f"{d:>4} {sw}x{sh:<6} {scale:>6} {pw:>6} {content:>8} "
              f"{scrolls:>8} {tiles:>6}  {ok}")
        bad += bool(fail)
    print(f"\n{len(CASES) - bad} of {len(CASES)} configurations clean")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
