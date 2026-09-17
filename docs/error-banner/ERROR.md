# nab'd error banner — exact spec

The save banner's twin. Everything needed to reproduce it 1 for 1, and a way
to prove you have.

**Total 4,120 ms — the same as the save banner, deliberately.** The arrival and
the exit are not copies of the save banner's, they are *the same track objects*,
shared by reference. Only the performance in the hold differs.

---

## 1. Why it is built this way

An error notification has one job the success notification does not: it has to
be distinguishable at a glance, from the corner of a screen, while someone is
still playing a game. It has exactly two frames' worth of attention.

So the design does the opposite of what you might expect. It changes **as
little as possible**:

- the card arrives identically — same slide, same rise, same ring draw, same
  horns, same eyes landing on 900
- it leaves identically — same eye close, horn retract, ring wind, collapse
- the sound sits on the same six beats, at the same length and level
- only the **ground colour** and the **gesture in the middle** differ

That is what makes it read. A banner that arrived differently would just look
like a different app. A banner that arrives the way you have seen forty times
and then *refuses* is unmistakable.

---

## 2. The files

| File | What it is | Ships? |
|---|---|---|
| `nabd_ease.py` | the eight easing curves | **yes** — unchanged, shared |
| `nabd_mark.py` | **replaces** the save package's copy | **yes** — see §3 |
| `nabd_banner.py` | the save timeline | **yes** — unchanged, imported |
| `nabd_banner_error.py` | the error timeline | **yes** — new |
| `nabd_mark_frames_error.py` | build-time flipbook + `index_for(t)` | **yes** — new |
| `synth_error.py` | builds the WAV | no — dev tool |
| `assets/sound/nabd-sound-error.wav` | the cue | **yes** |
| `verify_error.py` | the 1-for-1 check | no — dev tool |
| `reference/save-poses.sha256` | the save banner's poses, from **before** the patch | no — but keep it |
| `make_reference_gif_error.py` | renders the GIFs | no — dev tool |
| `make_example_mp4.py` | renders the videos, with sound | no — dev tool |
| `reference/` | ground truth | no |

`nabd_banner_error.py` imports `nabd_banner` and reuses its tracks. Do not
break that import by copying the tracks across — an invariant fails if you do,
on purpose.

---

## 3. `nabd_mark.py` gains one channel

`pose_svg` now understands `shut`, which closes **both** eyes. `wink` still
closes the right one only.

```python
sh  = getattr(f, "shut", 0.0)
w   = 1 - max(f.wink, sh) * 0.94     # right eye
w_l = 1 - sh * 0.94                  # left eye
```

`getattr` is load-bearing: the save banner's `Frame` has no `shut` field at
all, so its output is unchanged — **byte-for-byte across all 2,060 poses**.

`verify_error.py` re-checks that every run, against a sha256 taken from the
*original* module and stored in `reference/save-poses.sha256`. It deliberately
does not diff against a copy of the old file: the check matters most once the
patched file has replaced it in the repo, which is exactly when a file-diff
would silently skip.

Replace the save package's `nabd_mark.py` with this one. They are the same file
plus this change.

---

## 4. Look at it first

- **`reference/error-banner.mp4`** — the banner with its sound, in sync. This
  is the one to judge it by; the two halves were designed together and a GIF
  cannot carry audio.
- **`reference/save-banner.mp4`** — the same treatment of the save banner, for
  an A/B. Play them back to back: the first 900 ms should feel the same.
- **`reference/error-4120ms.gif`** — the whole banner, real time, silent.
- **`reference/error-mark-closeup.gif`** — the mark at 220 px. Watch the horn
  follow-through and the eye slits sweeping.
- **`reference/sound-comparison.png`** — the two waveforms above each other.

- **`reference/sync-page.html`** — an interactive version: play, scrub the beat
  ruler, A/B against the save banner, watch the channels live. Open it in a
  browser; it is self-contained, both WAVs included.
  **It is a demo, not a source of truth.** It re-implements the timeline in
  JavaScript for the browser. The shipping numbers live in
  `nabd_banner_error.py`, and `verify_error.py` is what proves a build matches
  them. The two agree today — the tracks were ported across directly — but if
  they ever disagree, the Python is right. Change the Python first.

The videos are built by `make_example_mp4.py` from `banner_frames()` and the
shipped WAV — the same two assets the app uses, not a re-recording. Lead-in and
tail are padded on both streams by the same amount, so cue 0 still lands on the
frame the line starts sliding. The copy is placeholder, but it is set in Outfit
Medium and JetBrains Mono, so the card is as crowded as it will really be.

---

## 5. The ground

```
FIELD      #8E3229      the card
FIELD_EDGE #D2695C      the lit 4 px edge, as purple-light is to purple
```

**Not `--danger` #B4483E.** Cream on that measures **4.21:1** — which would
make the failure copy *harder* to read than the success copy, which is
backwards. Deepened to `#8E3229`, cream lands at **6.28:1**, better than the
save banner's own 5.82:1 on purple.

The mark itself does not change colour. It is cream, as it is everywhere. This
adds one approved ground to the brand; it does not recolour the logo.

---

## 6. The gesture

| At | For | What moves | Ease |
|---|---|---|---|
| 1500 | 110 | A small sigh — squash to 0.955 and back | `COLLAPSE` |
| 1500 | 140 | **Both eyes close** | `COLLAPSE` |
| 1640 | 110 | Anticipation — turns 0.38 the wrong way | `RISE` |
| 1750 | 165 | Traverse 1 → **+1.35** | `WIND` |
| 1915 | 160 | Traverse 2 → −1.18 | `WIND` |
| 2075 | 150 | Traverse 3 → +0.82 | `WIND` |
| 2225 | 140 | Traverse 4 → −0.47 | `WIND` |
| 2365 | 130 | Traverse 5 → +0.19 | `WIND` |
| 2495 | 105 | Settles dead centre | `RISE` |
| 2600 | 220 | **Eyes open again**, slowly | `RISE` |

Five traverses at roughly 160 ms each — about 3 Hz, which is what a head
actually does. `WIND` is ease-in-**and**-out, so each traverse is fastest
crossing centre and slowest at the reversal, where the head changes direction.
Using an ease-out curve here makes it look like a windscreen wiper.

---

## 7. The four rules

**The amplitude goes past the save banner's.** `SHAKE_MAX` is **1.35**; the
wink never exceeds 1.0. With the eyes shut, the eye parallax that normally
carries a turn is gone, so the amplitude has to do that work. Pushing this one
dial scales the eye travel, the horn asymmetry and the silhouette squeeze
together, through the same physics, instead of bolting on a second effect. At
1.35 the far eye compresses to 0.53 and the far horn to 0.60; nothing inverts.

**Roll is computed from yaw, never keyframed.** `tilt = turn × 4.5`. The same
rule the horn lag follows. A shake that rolls a little reads as a head; one
that only yaws reads as a turntable. Deriving it means they cannot drift out of
phase, and changing `SHAKE_MAX` carries the roll with it.

**The eyes are shut before the first traverse and stay shut through all five.**
A shake with the eyes open is a different gesture — it reads as looking around,
not as refusing. They reopen slowly afterwards, which both reads as reluctance
and fills the hold, so nothing sits still. This is asserted.

**Everything the save banner's rules say still applies.** The horns never
translate. The head pivots at the neck. The mark is never rotated — a five-
traverse shake is still not a spin, because the ring's bite stays where it is
and the head returns to dead centre.

---

## 8. The sound

Same six beats, same length, same level, same instrument. Only the notes change,
and only after the point where things go wrong:

| | 0 | 320 | 900 | 3200 | 3630 | 3890 |
|---|---|---|---|---|---|---|
| save | air | E3 | **B3** | B3 | **E3** | air |
| error | air | E3 | **B♭3** | B♭3 | **D3** | air |

The first two events are the *same sound*, because at 320 ms nothing has failed
yet — the card is still arriving. It commits to being an error at 900, the same
instant the save banner commits to being a success, by putting a **tritone**
(1.413 × the root) where the perfect fifth was.

The exit mirrors the entry as the save sound's does, but walks down **past**
home instead of returning to it. A phrase that ends a whole tone under the note
it started on does not sound finished. Nothing was finished.

`nabd_sound.verify()` passes on this file unchanged: 48 kHz, 16-bit, mono,
4,120.00 ms, −12.00 dBFS peak, silent edges.

**It is not an alarm.** Centroid 174 Hz and −75.9 dB above 2 kHz — the same
band as the save sound, asserted in `synth_error.py`. An error is not an
emergency, and this plays while someone is still playing.

**The shake is silent**, for the same reason the wink is: the sound marks
structural events, the gesture is character.

---

## 9. The flipbook

```
python nabd_mark_frames_error.py assets/mark-error --scale 1 1.25 1.5 2
```

292 frames per scale: one resting frame plus three windows
(440–908, 1500–2828, 3030–3548). The gesture window is longer than the save
banner's because the eyes have to close first and open again after.

The entry and exit windows are the **same windows**, and
`assert_shared_with_save()` proves all **247** poses inside them render to the
identical picture. If that ever fails the two banners have stopped being the
same product, and nothing else would catch it — the tracks are shared by
reference, but `sample()` is not.

At runtime, exactly as the save banner:

```python
from nabd_mark_frames_error import index_for
img = frames[index_for(t)]
```

---

## 10. Proving it is 1 for 1

```
python verify_error.py
```

Five checks. It is sensitive: dropping `SHAKE_MAX` from 1.35 to 1.30 — a change
you would not see in a GIF — is caught at 1,752 ms.

---

## 11. What will break it

1. Copying the save banner's tracks instead of importing them. An invariant
   fails on purpose if `TRACKS["ring"] is not SAVE.TRACKS["ring"]`.
2. Changing `TOTAL_MS`. Both WAVs are exactly 4,120 ms.
3. Keyframing `tilt` instead of deriving it from `turn`.
4. Opening the eyes during the shake, or shortening it below four traverses —
   three reads as a flinch, not a refusal. Both are asserted.
5. Using `--danger` #B4483E for the field. See §5.
6. Re-introducing `stroke-dashoffset` or `opacity` into `pose_svg`. svglib drops
   both silently and the flipbook goes static with every test still green.
7. Scoring the shake.

Wire **all three** checks into the build: `assert_invariants()` in
`nabd_banner_error.py`, and `assert_invariants()` + `assert_shared_with_save()`
+ `assert_raster()` in `nabd_mark_frames_error.py`.
