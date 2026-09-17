# Prompt for Claude Code — the error banner

Drop this folder in at `docs/error-banner/`, then paste everything below.

---

Read `docs/error-banner/ERROR.md` in full, and open
`docs/error-banner/reference/error-4120ms.gif` and `error-mark-closeup.gif` so
you know what you are building toward. Then read what it is a diff against:
`nabd_banner.py`, `nabd_mark.py`, `nabd_mark_frames.py`, `banner.py` and
`nabd_sound.py`.

This is the save banner's twin: an error notification that arrives and leaves
exactly like the save banner and refuses in the middle. The rules that matter
most:

1. **`nabd_mark.py` in this folder replaces the one in the repo root.** It is
   the same file plus a `shut` channel. It does not change a single frame of
   the save banner and `verify_error.py` proves that on every run — do not
   "merge" the two by hand.
2. **`nabd_banner_error.py` imports `nabd_banner` and shares its tracks by
   reference.** Do not copy the entry and exit tracks across. An invariant
   fails on purpose if you do.
3. **Do not change `TOTAL_MS`** and do not re-render either WAV. Both are
   exactly 4,120 ms and `nabd_sound.verify()` asserts it.
4. **The field is `#8E3229`, not `--danger` #B4483E.** §5 says why, with the
   contrast numbers.
5. **Take the artwork and the timing as given.** Do not redraw path data, and
   do not retune the shake because it looks strong in a still — it is tuned for
   motion.

Work in this order and stop after each step so I can run it:

1. Copy in `nabd_mark.py` (replacing the existing one), `nabd_banner_error.py`
   and `nabd_mark_frames_error.py`, and the WAV to wherever the sound assets
   live. Run `python docs/error-banner/verify_error.py` from the repo root and
   paste me the output — it must end `OK -- 1 for 1 with the reference.`, and
   step 3 of it must report **0** changed save-banner frames.
2. Re-run the save banner's own `verify_banner.py` and show me it still passes.
3. Generate the error flipbook and show me the frame count and total size.
4. Wire `banner.py` so it can run either timeline — the error path should be a
   parameter, not a second copy of the banner. Tell me how you have structured
   that before you write it.
5. Run both banners on screen and tell me what you see at 900 ms, 1,915 ms and
   3,300 ms in the error one.

If a spec instruction conflicts with what the code actually does, tell me
rather than guessing. `verify_error.py` is the tiebreak for anything about
timing.
