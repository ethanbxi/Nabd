# Prompt for Claude Code — save banner only

Drop this folder in at `docs/banner/`, then paste everything below the line.

---

Read `docs/banner/BANNER.md` in full, and open
`docs/banner/reference/banner-4120ms.gif` and `mark-closeup.gif` so you know
what you are building toward. Then read what it is a diff against:
`nabd_banner.py`, `nabd_banner_frames.py`, `banner.py`, `make_banner_assets.py`,
and `nabd_sound.py` + `SOUND.md` (to satisfy yourself that §7 is right before
you trust it).

Scope: the save banner only. Do not touch the tile, the wordmark, the tray
glyph, `brand.py`, the asset builds, capture behaviour, the config schema or
`nabd_sound.py`.

The rules that matter most:

1. **Take the artwork as given.** The paths in `nabd_mark.py` were lifted from
   the designer's files. Do not redraw, simplify, re-export or clean up any
   path data.
2. **`nabd_banner.py` replaces the existing file wholesale.** Do not merge the
   old `TRACKS` into it. `nabd_banner_frames.py` is deleted and superseded by
   `nabd_mark_frames.py`.
3. **The mark is a flipbook now, §5.** `banner.py` stops compositing a ring
   overlay and blits `frames[index_for(t)]`. Frames are generated at build
   time; nothing rasterises at launch.
4. **Do not change `TOTAL_MS`** and do not regenerate the WAVs. §7 shows why
   every cue still lands.
5. **Wire all three checks into the build** — `assert_invariants()` in
   `nabd_banner.py`, and `assert_invariants()` + `assert_raster()` in
   `nabd_mark_frames.py`.
6. **Do not "simplify" `ring_arc()` or `_mix()` back into dash offsets or
   opacity, §5a.** svglib drops both silently and the flipbook goes static
   with every assertion still passing. This already happened once.

Work in this order and stop after each step so I can run it:

1. Copy in `nabd_ease.py`, `nabd_banner.py`, `nabd_mark.py`,
   `nabd_mark_frames.py`. Delete `nabd_banner_frames.py`. Run
   `python docs/banner/verify_banner.py` from the repo root and paste me the
   output — it must end `OK -- 1 for 1 with the reference.`
2. Generate the flipbook (`python nabd_mark_frames.py assets/mark --scale
   1 1.25 1.5 2`) and show me the frame count and total size.
3. Wire `banner.py` to the flipbook per §6, and point `make_banner_assets.py`
   at `nabd_mark_frames.render()`.
4. Run the banner on screen and tell me what you see at 900 ms, 1,800 ms and
   3,320 ms so I can check it against the GIF.

If a spec instruction conflicts with what the code actually does, tell me
rather than guessing — the spec was written by reading the repo, but at one
point in time. `verify_banner.py` is the tiebreak for anything about timing.
