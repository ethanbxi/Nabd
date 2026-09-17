# nab'd — brand overhaul

Handoff spec for Claude Code. Swaps the mark, the wordmark and the save-banner
motion. Build exactly what is here.

Everything in `brand/` is generated from the two PDFs you supplied — the paths
are lifted unmodified, not redrawn. The measurements below were taken off those
files rather than assumed.

---

## 1. What changed

**The mark** is now a horned head: the ring with a bite, plus horns and eyes.

| | old | new |
|---|---|---|
| Ring sweep | 295° | 295.3° |
| Bite | 65° | 64.7° |
| Bite position | 1 o'clock | **4 o'clock** |
| Stroke ÷ radius | 0.41 | 0.23 |
| Tones | 2 | 2 |

The sweep and the bite survive to within a third of a degree. The bite rotated
to 4 o'clock to give the horns the top, which is the only place they could go —
and because the sweep is unchanged, **the ring still draws and winds along the
same path it always did.**

**The wordmark** is redrawn heavier, with horns on the `n`. Same stem-and-circle
construction, still stroked rather than outlined.

| | old | new |
|---|---|---|
| Stroke | 13 | 19.5 |
| Ascender | 86 | 129 |
| x-height | 61 | 72 |
| Stroke ÷ x-height | 0.21 | 0.27 |

**The motion** now has the mark assemble and perform inside the existing
4,120 ms timeline. Nothing about the card, the line or the ring changed.

---

## 2. The horn rule

> **The horns appear exactly once. Whichever element is alone wears them.**

- Wordmark on its own → **horned** `n`. README titles, the installer header,
  a site header.
- Mark present → **plain** `n`. The mark is never modified; the type steps back.

That is why `brand/` ships `nabd-wordmark-horned-*` and
`nabd-wordmark-plain-*`, and why every lockup uses the plain one. De-horning the
*mark* instead would create a second mark, and the mark is the asset most likely
to end up somewhere it shouldn't — a tray icon, a favicon.

---

## 3. Files in this package

| File | What it is |
|---|---|
| `brand/` | 15 SVGs. Mark, wordmark (both), lockups, stacked, tile, tray. |
| `nabd_mark.py` | The artwork as paths, plus `pose_svg(frame)` — the arithmetic that tilts, turns, squashes and winks it. |
| `nabd_banner.py` | The motion as data. Replaces the existing file. `assert_invariants()` is the CI check. |
| `nabd_mark_frames.py` | Build-time flipbook. Replaces `nabd_banner_frames.py`. |
| `nabd_ease.py` | Unchanged. Included so the folder runs standalone. |

---

## 4. The swap list

These are the places the old artwork reaches. Work down it; do not assume the
list is complete without grepping for the old filenames.

| Replace | With |
|---|---|
| `brand/nabd-mark-*.svg` | the new `nabd-mark-*.svg` |
| `brand/nabd-wordmark-*.svg` | `nabd-wordmark-horned-*` / `-plain-*` (two variants now) |
| `brand/nabd-lockup-*.svg`, `nabd-stacked-*.svg` | the new ones — full mark, plain `n` |
| `brand/nabd-app-tile-512.svg` | the new tile |
| `brand/nabd-tray-template.svg` | the new tray glyph — **the silhouette has horns now** |
| `nabd_banner.py` | the one in this package |
| `nabd_banner_frames.py` | **delete**; `nabd_mark_frames.py` supersedes it |
| `icon.ico` | re-run `make_ico.py` against the new tile |
| `assets/banner/*` | re-run the banner asset build |
| `make_banner_assets.py` | point it at `nabd_mark_frames.render()` |
| `render_assets.py`, `make_wizard_art.py`, `render_readme_media.py` | re-run; they read `brand/` |
| `banner.py` | see §6 — it blits a mark flipbook now, not ring frames |
| `settings.py`, `nabd_ui.py` | wherever the mark or wordmark is drawn: panel header, window rail, first-run |
| `installer.iss` | wizard art is regenerated, path unchanged |

---

## 5. The motion

Total **4,120 ms**, unchanged.

| At | For | What moves | Ease |
|---|---|---|---|
| 0 | 260 ms | Line slides out of the corner | `SLIDE` |
| 320 | 260 ms | Card stands up | `RISE` |
| 440 | 460 ms | Ring draws counter-clockwise, 2:50 → the bite at 5:00 | `DRAW` |
| 660 | 150 ms | **Horns grow** out of the rim | `RISE` |
| 760 | 140 ms | **Eyes open**, landing on 900 as the ring closes | `RISE` |
| 620 | 2580 ms | Hold. Dismiss rule drains | linear |
| 1500 | 200 ms | Anticipation — stretches up, leans and turns slightly the wrong way | `RISE` |
| 1700 | 170 ms | **Turns, tilts, squashes and winks — one action** | `COLLAPSE` |
| 1870 | 210 ms | Held. Squash releases over the first 130 ms | `RISE` |
| 2080 | 160 ms | Eye opens, overlapping the return | `RISE` |
| 2150 | 230 ms | Unwinds, overshooting 4.5° past level | `RISE` |
| 3030 | 120 ms | Eyes close — first out, having been last in | `LEAVE` |
| 3075 | 120 ms | Horns retract | `LEAVE` |
| 3200 | 340 ms | Ring winds back along the same path | `WIND` |
| 3630 | 200 ms | Card collapses onto the line | `COLLAPSE` |
| 3900 | 220 ms | Line slides off right | `LEAVE` |

### The rules that make it work

**The horns never translate.** They scale about their own roots on the ring's
rim, and the only rotation applied to them pivots at the head's *centre* — so
the roots travel along the rim rather than off it. A translate, or a pivot
anywhere else, visibly tears them off the head. This was got wrong twice.

**The turn is a head turn, not a rotation.** A flat shape rotated with
`rotateY` foreshortens uniformly and reads as a squash. A head keeps its
silhouette and moves its *features*: the ring barely changes (scaleX 0.95),
the near eye slides toward the **centre** of the outline — where it faces the
viewer squarest — and the far eye runs out to the edge and compresses to 65%.
Pushing the features the other way, card-style, stops it being a turn.

**The horns lag the head by 45 ms and overshoot.** Computed from where the head
was, not keyframed, so it stays correct if `TILT_MAX` changes.

**The head pivots at the neck, not its centre.** Rotating about the centre is a
spin — the thing the guidelines forbid, and the thing that turns a ring buffer
into a loading indicator.

**Three dials.** `TILT_MAX` 14°, `TURN_MAX` 1.0, `SQUASH` 0.88. Everything else
is computed from them.

---

## 6. The flipbook

The mark now has a pose, so it can no longer be a single cached PNG with a ring
overlay. Bake the whole thing.

```
python nabd_mark_frames.py assets/mark --scale 1 1.25 1.5 2
```

254 frames per scale: one resting frame plus three motion windows
(440–908, 1500–2528, 3030–3548). At 30 px these are tiny — the full four-scale
build is about 1,000 PNGs, 610 kB, and 21 seconds.

Two things about the render, both found by running it rather than assuming:

- **The purple field is baked into the frames.** The mark only ever appears on
  the solid card, and baking the background gives clean antialiased edges
  instead of the white fringing you get compositing a keyed-transparent PNG.
  `render(bg=...)` takes a different colour for the rail or the tray.
- **svglib reads the SVG's width as points, not pixels**, so a 60 px request
  comes back 45 px. `render()` rescales the drawing explicitly. If you rebuild
  this path yourself, that is the bug you will hit.

`index_for(t)` is the contract between the build and the runtime — it is pure
and stdlib-only, so `banner.py` imports it without pulling in svglib:

```python
from nabd_mark_frames import index_for
img = frames[index_for(t)]          # already loaded, indexed by int
```

`assert_invariants()` walks the whole timeline at 4 ms and fails if the mark
changes anywhere outside a declared window — which is what catches a retimed
beat that would otherwise silently freeze on screen.

---

## 7. The sound does not change

Every cue still lands on a beat that did not move:

| Cue | ms | Beat |
|---|---|---|
| air | 0 | line slides out |
| E3 | 320 | card rises |
| **B3** | 900 | ring closes **and the eyes finish opening** |
| B3 | 3200 | ring winds back |
| E3 | 3630 | card collapses |
| air | 3890 | line withdraws |

`nabd_sound.DURATION_MS` stays 4,120 and the WAVs are untouched. The eyes were
deliberately timed to land on 900 so the resolve marks the ring closing *and*
the daemon arriving — one event, one note.

**The wink is silent on purpose.** The sound marks structural events; the wink
is character. Scoring it would need a new 4,120 ms render and would make a
one-second gesture into a second announcement.

---

## 8. What will break it

1. Translating the horns, or flexing them about anything but the head's centre.
2. Replacing the head turn with `rotateY` + perspective. It reads as a squash.
3. Rendering pose frames at launch instead of at build time.
4. Changing `TOTAL_MS`. The sound file is exactly 4,120 ms and `verify()`
   asserts it.
5. Using the horned wordmark in a lockup. See §2.
6. Shipping the old `nabd-tray-template.svg`. The silhouette changed.
7. Letting the mark change outside a motion window — `assert_invariants()` in
   `nabd_mark_frames.py` catches this, so run it in the build.

---

## 9. Not covered

The raster outputs. `icon.ico`, the installer wizard art and the README media
are all generated by scripts you already have; they read `brand/`, so re-running
them after the swap is the whole job. I have not touched those scripts.
