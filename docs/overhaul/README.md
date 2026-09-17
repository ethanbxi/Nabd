# nab'd brand overhaul — handoff

New mark, new wordmark, new save-banner motion. Stack unchanged: Python 3.10 /
classic tkinter, svglib + reportlab at build time only. **No new runtime
dependency.**

Read order:

1. **`OVERHAUL.md`** — the spec. What changed and by how much, the horn rule,
   the swap list, the motion, the flipbook, and why the sound is untouched.
2. **`brand/`** — 15 SVGs, generated from the supplied artwork.
3. **`nabd_mark.py`** — the paths, plus the arithmetic that poses them.
4. **`nabd_banner.py`** — the motion as data. Run it directly.
5. **`nabd_mark_frames.py`** — the build-time flipbook. Run it directly.
6. **`PROMPT.md`** — what to paste into Claude Code.

```
python nabd_banner.py        # timeline + invariants
python nabd_mark_frames.py   # frame plan + invariants
python nabd_mark_frames.py assets/mark --scale 1 1.25 1.5 2
```

## The short version

The bite survived. Sweep 295.3° against the old 295°, bite 64.7° against 65° —
rotated to 4 o'clock so the horns could have the top. The ring draws and winds
along the same path it always did, so **the 4,120 ms timeline and the sound
files are untouched.**

```
line · card · ring draws · horns grow · eyes open
   ... hold, rule draining ...
turn + tilt + squash + wink, as one action, then unwind
   ... eyes out · horns out · ring winds · card collapses · line off
```

Three things carry it, and all three are easy to undo by accident:

- **The horns never translate.** They scale about their roots on the rim, and
  the only rotation pivots at the head's centre. Anything else tears them off.
- **The turn is a head turn, not a rotation.** The silhouette holds; the
  features move across it. `rotateY` reads as a squash.
- **The eyes land on 900**, where the ring closes and the sound resolves. One
  event, one note.

## Decided in review

- Two-tone, not the layered three-tone version — it cannot reduce to one colour
  and the third tone becomes noise at 16 px. Keep the layered one for hero use
  above ~96 px on the purple field.
- Horns appear exactly once; whichever element is alone wears them.
- The wink is silent.

## Not included

Raster outputs. `icon.ico`, wizard art and README media all come from scripts
you already have, which read `brand/` — re-running them after the swap is the
whole job.
