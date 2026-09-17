# nab'd error banner — 1-for-1 package

The save banner's twin. Arrives and leaves identically; shuts both eyes and
shakes its head in the middle.

```
nabd_ease.py                 unchanged, shared            -> repo root
nabd_mark.py                 REPLACES the existing one    -> repo root
nabd_banner.py               unchanged, imported          -> repo root
nabd_banner_error.py         the error timeline           -> repo root
nabd_mark_frames_error.py    build-time flipbook          -> repo root
assets/sound/nabd-sound-error.wav                         -> beside the others

synth_error.py               rebuilds the WAV             stays in docs/
verify_error.py              the 1-for-1 check            stays in docs/
make_reference_gif_error.py  regenerates the GIFs         stays in docs/
make_example_mp4.py          regenerates the videos       stays in docs/

reference/error-banner.mp4        the target, WITH SOUND
reference/save-banner.mp4         the save banner, for an A/B
reference/error-4120ms.gif        the target, real time, silent
reference/error-mark-closeup.gif  the mark at 220 px
reference/sound-comparison.png    both waveforms, aligned
reference/sync-page.html          interactive: play, scrub, A/B (a DEMO -- see ERROR.md 4)
reference/timeline.csv            sample(t) every 4 ms, all 16 channels
reference/save-poses.sha256       the save banner, from before the patch -- keep it
```

Start with `ERROR.md`. Watch the GIFs before writing anything.

```
python verify_error.py
```

Must end `OK -- 1 for 1 with the reference.`
