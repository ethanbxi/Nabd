# nab'd — capture sound

Handoff spec for Claude Code. Adds a confirmation sound to the save banner.
Build exactly what is here.

Reference: the motion artifact plays this against the banner animation, driven
off the audio clock, so the sync on that page is the real thing rather than a
depiction of it.

---

## 1. Files

| File | What it is |
|---|---|
| `assets/sound/nabd-sound-pip.wav` | The sound. 48 kHz, 16-bit mono PCM, 4,120 ms, mastered at −12 dBFS. |
| `nabd_sound.py` | Playback. Stdlib only. `play(choice)` and a `verify()` for CI. |
| `synth5.py` | The generator, with the invariants asserted. Needs numpy + scipy; **build-time or never**, not a runtime dependency. |

---

## 2. What it is

Three sound events, each on a beat the banner already has, and then the same
three in reverse as it leaves:

| At | Motion | Sound |
|---|---|---|
| 0 | line slides out of the corner | air — a breath, barely there |
| 320 | card stands up | **E3**, the gesture |
| 900 | ring completes its 295° draw | **B3**, the resolve |
| 620–3200 | banner holds, rule draining | *silence* |
| 3200 | ring winds back | **B3** |
| 3630 | card collapses onto the line | **E3**, falling |
| 3890 | line withdraws | air |

Read the entry down and the exit up: **air · E3 · B3 | B3 · E3 · air.** The
entry climbs a fifth and the exit walks back down it, and the breath that opened
the banner is the last thing you hear. Each exit beat answers the entry beat it
physically mirrors — the ring unwinding answers the ring drawing, the card
collapsing answers the card rising.

The exit sits 9–12 dB under the entry. It is an answer, not a second
announcement.

**Character.** E3 over an E2, nothing above 1.2 kHz, spectral centre 169 Hz.
Every attack is 30–70 ms of raised cosine — nothing in the file is struck, which
is most of why it reads as smooth rather than as an alert. Energy above 2 kHz is
at −75 dB; that band is where the ear is most sensitive and it is what makes a
sound feel sharp long before it is loud.

---

## 3. Where it goes

In the **banner** process, on the line immediately before the animation clock
starts:

```python
from nabd_sound import play

play(settings.capture_sound)          # returns immediately
start = time.perf_counter()

def tick():
    t = (time.perf_counter() - start) * 1000.0
    ...
```

That is the whole integration. `play()` hands off to `winsound` with
`SND_ASYNC` and returns; it never blocks the UI thread and never raises.

### Why the file is exactly 4,120 ms

Because that is the banner's `TOTAL_MS`. Async playback belongs to the process
that started it, and the banner is a fresh process per nab that calls
`root.destroy()` at `TOTAL_MS` — so a file even slightly longer than the
animation gets its tail cut off, and a shorter one leaves the exit unscored.
`nabd_sound.DURATION_MS` and `verify()` exist to keep the two locked together.
If `TOTAL_MS` ever changes, the sound has to be regenerated, not trimmed.

### Why one file instead of scheduled cues

The gaps are *in* the file — two and a half seconds of literal silence sit
between the resolve and the exit. One buffer, one clock, started once. There is
nothing to schedule and no second timer to drift, which is the same reasoning
that put the banner on a wall clock instead of chained callbacks. It also means
the exit cannot fall out of sync with the entry, because they are the same file.

### Sync tolerance

Windows shared mode adds roughly 10–30 ms of latency to `PlaySound`. Every
attack here is 30–70 ms of raised cosine, so a 20 ms slip is inaudible. This is
the practical reason, on top of the aesthetic one, that nothing has a transient
— a click would have exposed exactly this.

---

## 4. The setting

Goes in the **CAPTURE** group of the settings panel, under the hotkey rows:

```
Capture sound     [ Off | pip | settle | bloom | Custom… ]
```

Default **pip**. Store the bare string; `nabd_sound.resolve()` treats anything
ending in `.wav` as a path to the user's own file and anything else as a
built-in name, and returns `None` for `"off"`, an empty value, or a file that is
not there. Ship the other two built-ins as well — they are the same score with
different bodies (`settle` is warmer with longer tails, `bloom` has no attack at
all), and they cost 400 kB each.

A preview button next to the row is worth it: `play(choice)` is the entire
handler, and nobody wants to nab something to audition a sound.

---

## 5. Bundling

The WAV has to reach the onedir bundle. In the spec file:

```python
datas=[('assets/sound/*.wav', 'assets/sound')]
```

`nabd_sound.asset_dir()` resolves `sys._MEIPASS` when frozen and the module's
own directory when running from source, so the same code path works either way.
Do not add numpy or scipy to the bundle — `synth5.py` is a build-time tool and
the runtime module is stdlib only.

`python nabd_sound.py` verifies every asset it finds: format, length against
`DURATION_MS`, mastering level, and that both edges land on zero. Worth a line
in the build.

---

## 6. The sound will be inside the next clip

You capture desktop audio through WASAPI loopback, which takes the whole
endpoint mix — including anything nab'd itself plays. The ring buffer keeps
running after a save, so a nab taken within the buffer window contains the
previous nab's confirmation sound.

**Measure before you fix it.** At −32 dBFS RMS and centred at 169 Hz this is a
long way down under game audio, and it may well be inaudible in practice. Record
a clip with the sound playing and listen before spending anything on it.

If it does bother you, the fix is cheap and your architecture already supports
it: desktop and mic are mixed in-process with `audioop` before being piped to
FFmpeg, so the loopback stream can be attenuated for a fixed window. Two
qualifications:

- **The duck belongs in the main process, not the banner.** The mixer lives in
  the main process; the banner is a separate process that does not own the
  stream. Set the deadline where you spawn the banner.
- **Duck the entry only — about 1,200 ms.** The exit is 9–12 dB quieter again
  and will not be heard under gameplay. Ducking the whole 4.1 seconds would
  punch a four-second hole in the desktop audio of the *next* clip, which is a
  worse artefact than the one you are removing.

```python
# main process, where the banner is spawned
_duck_until = 0.0

def spawn_banner(...):
    global _duck_until
    _duck_until = time.perf_counter() + 1.25      # launch slack + the entry
    subprocess.Popen([...])

# in the mixer, per chunk
if time.perf_counter() < _duck_until:
    desktop = audioop.mul(desktop, 2, 0.0)
```

---

## 7. What will break it

1. Changing the banner's `TOTAL_MS` without regenerating the sound. The exit
   goes out of sync or gets cut. `verify()` catches it.
2. Normalising the WAV louder. `winsound` has **no volume control** — the file
   level *is* the playback level, which is why it is mastered at −12 dBFS
   rather than hot. A volume setting would mean rendering each sound at several
   levels, or moving playback to PyAudioWPatch, which puts app audio next to the
   capture path.
3. Calling `play()` after the first `draw()` instead of before `start`. The
   sound then trails the animation by however long the first frame took.
4. Converting the file to MP3 or a non-PCM WAV. `PlaySound` will silently fail.
5. Re-rendering with the lowpass raised or the register lifted. The assertions
   in `synth5.py` fail if it goes back into the band that was too sharp.

---

## 8. Retuning

Everything is one number in `synth5.py`:

| Want | Change |
|---|---|
| Higher or lower | `ROOT` / `FIFTH` / `SUB` |
| Brighter or darker | `lp(y, 1200)` in `finish()` |
| Louder or quieter | `PEAK` |
| Softer or harder arrival | `g_a` / `r_a` in the `K` table |
| Longer or shorter tails | `g_d` / `r_d` |
| More or less of the exit | `x` (the exit's scale factor) |

`python synth5.py` regenerates all three and asserts the invariants: the loudest
moment falls inside the card rise, the still section stays 36 dB down, the
dominant frequency in all four tone windows is the note it should be, the
closing breath matches the opening one, and nothing has a transient. The pitch
assertions are the mirror — they are what stops someone quietly breaking the
palindrome later.

---

## 9. Open questions

1. **Default on or off?** Shipped as on with `pip`. A sound that defaults off is
   a sound nobody finds.
2. **Does it survive exclusive-fullscreen?** Audio does, unlike the banner
   overlay itself (BANNER-MOTION.md §8) — so on those games the sound may end up
   being the *only* confirmation. Worth knowing before deciding the default.
3. **Second nab inside 4.1 seconds.** `PlaySound` preempts itself, so the new
   one cuts the old one off. That is almost certainly right, and it matches
   restarting the banner timeline.
