# Prompt for Claude Code

Copy everything below the line into Claude Code with the repo open, after
dropping this folder in at `docs/overhaul/`.

---

Read `docs/overhaul/OVERHAUL.md` in full before changing anything, and look at
the SVGs in `docs/overhaul/brand/`. Then read the parts of the repo it is a diff
against:

- `nabd_banner.py`, `nabd_banner_frames.py`, `banner.py` — the save banner
- `brand/` and `brand/README.txt` — the current artwork
- `make_banner_assets.py`, `render_assets.py`, `make_ico.py`,
  `make_wizard_art.py`, `render_readme_media.py` — the asset builds
- `nabd_sound.py` and `SOUND.md` — to confirm for yourself that §7 is right
  before you trust it

This is a brand overhaul: a new mark, a new wordmark, and a save-banner
animation where the mark assembles and performs. The rules that matter most:

1. **Take the artwork as given.** The paths in `brand/` and in `nabd_mark.py`
   were lifted from the designer's files. Do not redraw, simplify, re-export or
   "clean up" any path data.

2. **The horn rule, §2.** Wordmark alone → horned `n`. Mark present → plain `n`.
   The mark is never modified. Every lockup in `brand/` already follows this;
   apply the same rule anywhere you generate a lockup in code.

3. **`nabd_banner.py` replaces the existing file wholesale.** Do not merge the
   old TRACKS into it. `nabd_banner_frames.py` is deleted and superseded by
   `nabd_mark_frames.py`.

4. **The mark is a flipbook now, §6.** `banner.py` stops compositing a ring
   overlay and blits `frames[index_for(t)]`. Frames are generated at build time
   by `nabd_mark_frames.py`; nothing rasterises at launch.

5. **Do not change `TOTAL_MS` or touch the sound.** It is 4,120 ms, the WAVs
   already match it, and `nabd_sound.verify()` asserts the length. §7 shows why
   every cue still lands.

6. **Wire both `assert_invariants()` into the build** — the one in
   `nabd_banner.py` and the one in `nabd_mark_frames.py`. They encode the things
   that have already gone wrong once.

Work in this order and stop after each step so I can run it:

1. Drop the new `brand/` in, delete the superseded SVGs, and update
   `brand/README.txt`. Nothing else changes yet.
2. Re-run the asset builds — `make_ico.py`, `render_assets.py`,
   `make_wizard_art.py`, `render_readme_media.py` — and show me the diff in
   what they produced.
3. Swap `nabd_banner.py`, add `nabd_mark.py` and `nabd_mark_frames.py`, delete
   `nabd_banner_frames.py`. Run both invariant checks.
4. Generate the flipbook and wire `banner.py` to it.
5. Update the mark and wordmark wherever the UI draws them — the settings panel
   header, the window rail, first-run.

Do not change capture behaviour, the config schema, or `nabd_sound.py`. If a
spec instruction conflicts with what the code actually does, tell me rather than
guessing — the spec was written by reading the repo, but at one point in time.
