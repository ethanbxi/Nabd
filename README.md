# Nab'd

A minimal instant-replay buffer for Windows. It continuously records your
screen in the background; pressing a hotkey writes the last few minutes to an
mp4. That's the whole feature set.

**Press `Alt + Insert` to save a nab.** A banner confirms it in the bottom-right
corner: *Nabbed — 5:00 · 1.2 GB*.

---

## Install

Run **`NabdSetup-2.1.0.exe`** and click through the wizard.

Nothing else is needed — no Python, no ffmpeg, no fonts, no account. It is a
per-user install, so there is **no admin prompt**, and everything lands in
your own profile:

| | |
|---|---|
| The app | `%LOCALAPPDATA%\Programs\Nabd` |
| Settings, buffer, log | `%LOCALAPPDATA%\Nabd` |
| Your nabs | your **Videos\Nabd** folder |

The wizard offers a desktop shortcut and *start when I sign in* — both on by
default. Uninstall from **Settings → Apps** like anything else; it removes the
app and the buffer and **leaves your saved nabs alone**.

> **Windows will warn you the first time.** The installer isn't code-signed
> (a certificate costs a few hundred dollars a year), so SmartScreen shows
> *"Windows protected your PC"*. Click **More info → Run anyway**. This is the
> one way it doesn't behave like a store-bought download; there is no way
> around it short of buying a signing certificate.

### First run picks up your hardware

Defaults ship as whatever suited the machine it was built on, so anything the
local hardware can answer for itself is resolved on first launch instead:

| Setting | How it is chosen |
|---|---|
| Nabs folder | Your real Videos folder, via the shell's known-folder API — so a OneDrive-redirected Videos still resolves correctly |
| Resolution | Whatever the monitor is; capture is always native |
| Frame rate | 60, stepped **down** if the display can't sustain it (a 240 Hz panel still starts at 60 — that's a file-size judgement, not a hardware limit) |
| Encoder | Probed with a real test encode: NVENC → AMF → QuickSync → x264 |
| Speakers / microphone | The Windows defaults |
| Monitor | The primary one |

Everything is changeable afterwards in Settings.

## How it works

```
ddagrab (GPU desktop capture) ──┐
                                ├─→ h264_nvenc ─→ 2s .ts segments ─→ ring buffer
WASAPI loopback + mic ──────────┘                                         │
                                                                          │
              hotkey ─────────────────→ concat -c copy ─→ nab.mp4 ←───────┘
```

The screen is *always* being encoded into small MPEG-TS segments, and old ones
are deleted. Saving a nab just concatenates the newest segments with a stream
copy — no re-encoding, so it finishes near-instantly and causes no CPU spike
in the middle of your game.

Two details that make it cheap:

- **Zero-copy capture.** `ddagrab` hands D3D11 textures straight to NVENC.
  Frames never leave the GPU — no PCIe readback, no CPU colour conversion. On
  machines without NVENC the encoder probe falls back and inserts the one
  `hwdownload` that those encoders need.
- **Desktop audio without drivers.** ffmpeg has no WASAPI loopback input, and
  many machines expose no "Stereo Mix" DirectShow device, so desktop audio is
  captured in-process via WASAPI loopback and piped to ffmpeg as raw PCM. No
  VB-Cable or virtual audio driver to install.

## Settings

**Click the tray icon** to open Settings. It slides in from the right and docks
there as a full-height panel spanning the whole screen, taskbar included — no
system title bar, just an ✕ in its corner. Escape closes it, and so does
clicking on anything else: it slides back out on its own. Dropdowns and the
folder picker do not count as clicking away. Right-clicking gives the full menu,
and the *Nab'd Settings* Start Menu shortcut works as well. Opening it again
raises the panel you already have rather than stacking copies.

```
Recording - 5 min buffered        (status)
-----------------------------------
Save last 5 min  (Alt + Insert)
[x] Recording                     <- turn capture on or off
-----------------------------------
Open nabs folder
Settings...                       <- what clicking the icon does
View log
-----------------------------------
Quit
```

**`Ctrl+Alt+N` opens the panel** without going near the tray.

The panel is a 640px drawer with one repeated grammar: a label on the left, a
fixed 344px control column on the right, and anything secondary — a disk meter,
a volume slider, helper text — stacked *inside* that column so it stays attached
to its control and every control lines up down the page.

| Section | What you can change |
|---|---|
| **Buffer card** | Live status, how much the buffer holds and how much disk is free, the retained window as a timeline, and the save hotkey shown large |
| **Recent nabs** | The newest nabs as poster thumbnails — click one to play it, arrows to page back — and a button to open the nabs folder |
| **Capture** | Nab length (1/3/5 min) with a live size estimate and disk meter, whether to start a fresh buffer after each nab, and the nabs folder |
| **Video** | Which monitor (**Identify** outlines it in purple), quality, frame rate |
| **Audio** | Which speakers to record, which microphone, a volume slider for each, A/V sync and a **Test** button that saves a five-second nab |
| **Hotkeys** | Save a nab, and open this panel. Click a field, press the combo; it tells you if it's already taken |

Three things the panel works out rather than states:

- **The size estimate is measured, not guessed.** The ring buffer is sitting on
  disk in 2-second segments written by the encoder that actually won the probe,
  so the byte rate is one `stat` away and tracks scene complexity live. Only
  when the buffer is cold — or stale, because the recorder is stopped — does it
  fall back to a bits-per-pixel model.
- **The frame-rate list comes from the display.** You cannot capture more
  distinct frames than the monitor presents, and a rate that is not an even
  division paces unevenly, so the list is derived from the refresh rate and a
  non-divisor is flagged rather than blocked.
- **Disk pressure is guarded.** Past 60% of free space the meter goes amber;
  past 85% it goes red, explains the numbers, and blocks Save on that field.

Save stays disabled until something actually changes, and the discard button
reads **Close** when there is nothing to lose and **Cancel** when there is.

Saving applies within a couple of seconds — **no restart**. The running app
watches `config.json`, rebuilds the capture pipeline, and rebinds the hotkey in
place. Editing `config.json` by hand works the same way.

Choosing **1 minute** buffers only 1 minute, so it also uses proportionally
less disk.

A few things are only in `config.json`, not the window:

| Key | Default | Notes |
|---|---|---|
| `save_delay` | `3.0` | Settle time before assembling. The segment being written when you press the key is still open, so a nab assembled instantly ends *before* the keypress. This waits for it to close, and picks up a couple of seconds of aftermath. Lower it for a snappier banner, but not below `segment_seconds`. |
| `segment_seconds` | `2` | Ring granularity, and what nab length rounds to |
| `banner_delay` | `0.2` | Beat between the keypress and the banner sliding in. Set to `0` for instant. |
| `preset` | `p5` | NVENC preset. `p4`/`p3` cost less GPU time if capture struggles under load |
| `encoder` | `auto` | Force one of `h264_nvenc`, `h264_amf`, `h264_qsv`, `libx264` instead of probing |
| `hotkey_alt` | `""` | A second combo that also saves a nab. `RegisterHotKey` is first-come-first-served, so a key another app claimed first can never be taken from it - set the key you actually want as `hotkey` and a free one here, and Nab'd keeps asking for the first in the background while the second works. |
| `draw_mouse` | `true` | Include the cursor |

`audio_offset_ms` starts at `-150`, measured against a flash/tone reference.
Capture latency accounts for only part of that, so it is a starting point
rather than a constant — the Audio section exposes it as a slider. Save a nab,
watch it, and nudge until speech lines up.

## Is capture healthy?

Every minute, Nab'd logs what the encoder is really doing (tray → *View log*):

```
capture health: 59.8 fps, +3 duplicated, 0 dropped
```

- **fps** should sit near your target. Much lower means capture is being starved.
- **duplicated** is the number that matters. Desktop Duplication only hands over
  a frame when the screen *changes*, so a large count means the capture is
  frozen — almost always exclusive fullscreen. On an idle desktop a high count
  is normal and harmless.
- **dropped** should stay near zero.

If duplicates climb during a game, that is the fullscreen problem below, not a
performance problem.

## Fullscreen games — important

**Run your game in Borderless Windowed (sometimes "Windowed Fullscreen").**

Nab'd captures the screen with DXGI Desktop Duplication. When a game takes
*exclusive* fullscreen, Windows hands the display to that game and Desktop
Duplication is cut off with `DXGI_ERROR_ACCESS_LOST` (`887a0026`). You get
frozen frames and repeated capture restarts. This is a limitation of the
Windows API, not something a setting here can fix.

Borderless costs essentially nothing on a modern GPU and makes capture work
perfectly. Most games default to it.

If capture keeps losing the display, Nab'd shows a red banner saying so rather
than letting you find out when a nab turns out to be frozen.

The only way to capture exclusive fullscreen is to inject into the game and
hook its present calls, which is what OBS Game Capture does — and precisely the
behaviour anti-cheat systems flag. Nab'd deliberately does not do this.

## Things worth knowing

- **Disk.** The buffer holds exactly your chosen length. At 1440p60 on High
  with real motion that is roughly **1.1 GB for 5 minutes**, 225 MB for 1
  minute; a still desktop compresses to a small fraction of that. Capped and
  self-pruning, not growing. The settings window estimates it live. Drop to
  Medium if you want it smaller.
- **Audio is mixed before ffmpeg sees it.** Desktop and mic are combined
  in-process into one PCM stream. Handing ffmpeg two audio inputs puts `amix`
  on the same filtergraph thread as `ddagrab` and costs roughly two thirds of
  the video frame rate.
- **Two ways to handle overlap**, set in Settings → Nab length:
  - *Rolling buffer* (default): always keeps the most recent footage. A nab is
    the last N minutes ending at the keypress, so nabs taken close together
    share most of their footage. While the app has been running for less than
    the buffer length there is simply less footage than that, so early nabs are
    shorter and all start at the moment you launched it.
  - *Start a fresh buffer after each nab*: the footage a nab used is discarded,
    so the next one begins where the last ended and nothing repeats. The
    segment ffmpeg is mid-way through writing cannot be deleted on Windows, so
    expect up to about four seconds of carry-over.
- **Nab length rounds to 2s.** Segments are the unit of assembly, so a nab is
  ~300s ± 2s rather than exactly 300.
- **The banner confirms right away; the nab finishes a moment later.** The
  helper that draws it stays resident and watches a trigger file, so trigger to
  first pixel is 5-7ms once its frames are loaded.

  The motion is 4,120ms in eight beats: a 4px line slides out of the corner,
  holds, the card stands up out of it, the mark draws itself on and the copy
  fades up, the dismiss rule drains for 2.6s, then the mark winds back, the card
  collapses onto the line, holds, and the line withdraws into the corner. Three
  things carry it and all three are easy to undo by accident — **one axis at a
  time** (horizontal and vertical never move in the same millisecond, or the two
  read as a diagonal), **the 60ms and 70ms holds** that separate the beats, and
  **asymmetric easing**: the collapse decelerates because it comes to rest on the
  line, and only the final slide accelerates, because it actually leaves.

  The size is not known when the banner opens - assembly is still running - so
  it appears with the nab length and the figure is filled in afterwards, in
  place, without restarting the timeline. If the save fails, a red banner
  corrects it.
- **A nab covers slightly past the keypress.** By design — see `save_delay`.
  Encoding runs with no B-frames and no lookahead so footage reaches disk
  promptly, and ffmpeg runs at above-normal priority so a busy game cannot
  starve it below its target frame rate.
- **`alt+f9` and `alt+f10` belong to NVIDIA ShadowPlay.** Avoid them. If a
  hotkey is taken at launch, Nab'd warns in the tray and keeps retrying in the
  background — recording is never blocked by a hotkey problem.
- **Anti-cheat.** The hotkey uses Win32 `RegisterHotKey`, the official system
  API. It installs no keyboard hook and does not inject into games, which is the
  behaviour anti-cheat systems object to.
- **The banner never steals focus.** It is marked `WS_EX_NOACTIVATE`, so it
  cannot pull input out of a game. It may not draw over *exclusive* fullscreen
  (borderless is fine).
- **The buffer survives a capture crash.** If ffmpeg dies (display lost, driver
  reset), it restarts in 0.4s and *keeps* everything already recorded. Segments
  are written under a per-session prefix, and a nab can span the seam.
- **ffmpeg can't be orphaned.** The capture process is held in a Win32 job
  object with kill-on-close, so it dies with the app even on a Task Manager kill
  or a crash.
- **Only one instance runs.** Guarded by a named mutex, so autostart plus a
  manual launch won't produce two recorders fighting over the buffer.
- **HDR.** If you turn on Windows HDR, `ddagrab` output will need tone-mapping
  and nabs may look washed out. Not currently handled.

## Building the installer

```powershell
python build.py
```

Three stages — gather the payload, freeze, package — ending at
`dist\NabdSetup-2.1.0.exe` (~70 MB).

Needs on the build machine:

| | |
|---|---|
| ffmpeg | on `PATH`, or a winget `Gyan.FFmpeg` package — 212 MB of it gets bundled |
| PyInstaller | `pip install pyinstaller` |
| Inno Setup 6 | `winget install JRSoftware.InnoSetup` |
| Fonts | Outfit + JetBrains Mono installed per-user, copied into `vendor\fonts` |
| Artwork | `brand\render\*.png` — run `render_assets.py` if missing |

The app freezes to **onedir**, not onefile: onefile unpacks to a temp folder on
every launch, and the banner helper is launched on every nab. One binary plays
three roles — the tray app, `--settings`, and `--banner` — because frozen there
is no interpreter to hand a script to. That is why `settings`, `banner`,
`theme` and `brand` are forced in as hidden imports despite nothing importing
them at module scope, and why **`banner.py` takes its trigger path from
`nabd`** rather than from `__file__`: inside the bundle `__file__` points into
`_internal`, so a locally derived path would leave the daemon watching a file
nobody ever writes.

Two generated-asset scripts, both build-time only:

```powershell
python render_assets.py      # brand/*.svg  -> brand/render/*.png
python make_wizard_art.py    # brand assets -> installer/wizard*.bmp
```

`render_assets.py` needs `svglib`, `reportlab` and `rlPyCairo`; the app itself
does not.

## Files

| File | Purpose |
|---|---|
| `nabd.py` | The application, and the frozen entry point for all three modes |
| `settings.py` | Settings window (own process — tkinter can't share the tray's thread) |
| `banner.py` | The confirmation banner: window, assets and drawing |
| `nabd_banner.py` | Its motion, as data. `sample(ms)` -> every animated value |
| `nabd_ease.py` | CSS-identical cubic-bezier easing, because Tk has none |
| `nabd_banner_frames.py` | Build-time frame generation, with the assertion that frame 16 is the mark |
| `make_banner_assets.py` | Runs the above for both field colours |
| `assets/banner/` | 432 pre-rendered frames: 4 DPI scales x 2 fields |
| `brand.py` | Palette, type scale, and the logo drawn from its published geometry |
| `nabd_tokens.py` | Every colour and metric in the panel, with DPI scaling |
| `nabd_paint.py` | Pillow renderers for what Tk cannot draw — rounded rects, gradients, the toggle, the meter |
| `nabd_ui.py` | The panel's widget set, built on those two |
| `brand/` | The supplied logo assets, and the PNGs rendered from them |
| `build.py` | Gather → freeze → package |
| `nabd.spec` | PyInstaller spec |
| `installer.iss` | Inno Setup script |
| `make_wizard_art.py` | Wizard BMPs from the brand assets |
| `render_assets.py` | Rasterises `brand/*.svg` |
| `vendor/` | Bundled ffmpeg and font faces (build input) |
| `_test/` | Test + benchmark scripts used to validate the pipeline |

Installed, the app's own data lives apart from its program files: `config.json`,
`buffer/` (cleared on every start) and `nabd.log` (rolling, capped at 1 MB,
reachable from the tray) are all under `%LOCALAPPDATA%\Nabd`. Run from source,
they sit next to the scripts instead.

## Brand

The interface follows the Nabd visual identity. Three rules shaped the code:

- **The contrast rule.** Nabd Purple `#6C3BAA` measures 2.7:1 on the near-black
  shell, under the 3:1 floor for UI shapes. So purple appears as linework only
  in Purple Light `#9B6BD8`; full-strength purple is used exclusively as a
  *field* with cream on top, which clears 7.2:1. `theme.FIELD` and
  `theme.ACCENT` keep the two roles separate, and the UI tests assert it. The
  installer's wizard panel is the same rule at a larger size — a purple field,
  cream lockup.
- **The artwork comes from the supplied SVGs.** `render_assets.py` rasterises
  `brand/*.svg` into `brand/render/*.png` once; the app loads those and scales
  them down, so the wordmark and mark are the real artwork rather than geometry
  transcribed into code.

  Two things are still built from the published measurements: the **app tile**
  (its SVG nests an inner `<svg>` with its own viewBox, which the rasteriser
  mis-places — the ring came out off-centre with a 7% stroke) and the
  **animated mark** in the banner, whose 17 sweep frames are generated at build
  time from the same 295 degree geometry and asserted against it - at the last
  frame the sweep *is* the mark, gap open at 1 o'clock, or the build fails. Both are checked against the spec: ring extent 47.5% of the tile,
  stroke 8.0%, optically centred.
- **The mark is one stroke, and it never rotates.** The artwork ships as two
  paths, but the second ends exactly where the first begins, so it is a single
  295° stroke from 95° with one 65° gap — drawing it as two arcs leaves a seam
  at the join. The banner traces that stroke on as it arrives and retraces it
  away as it leaves. Rotating it would turn a ring buffer into a loading
  spinner, so nothing spins.

Type is Outfit for interface and JetBrains Mono for hotkeys, paths, durations
and nab timestamps, at the published px scale. The installer places both
per-user (open-licensed, no admin needed). Outfit exposes each weight as its
own family to Windows, so weights 400/500/600 are selected by family rather
than by asking Tk for "bold". If a face is ever missing, `brand.font()`
degrades along the guidelines' own chain to system-ui and ui-monospace.

The tray and the shortcuts both use the purple app tile, rendered per size so
the 22.5% corner radius and 58% ring hold down to 16px; pausing desaturates the
field and keeps the silhouette. (The guidelines prefer a monochrome template in
a tray, on the grounds that Windows draws it over unknown wallpaper — the tile
was the explicit choice here, and the same document argues the field treatment
is what survives at small sizes.)

## Verified

| Check | Result |
|---|---|
| End-to-end nab via real `Alt + Insert` | Pass — 2560×1440, 59.3 fps, AAC 48kHz stereo |
| Banner appears on save | Pass |
| Rebinding the hotkey while running | Pass — old combo released, new one live, no restart |
| Config hot-reload | Pass — applied in ~2s |
| Settings window | Pass — 67/67 checks |
| Buffer survives an ffmpeg crash | Pass — all pre-crash segments kept, nab spans the seam |
| Hotkey capture with NumLock / ScrollLock on | Pass — no phantom Alt |
| Monitor identify overlay | Pass — covers 2560×1440+0+0 exactly |
| Nab reaches the keypress | Pass — +2.1s past it (was −0.8s before the fix) |
| Banner latency after keypress | 52 ms (was ~890 ms with a cold helper) |
| Real frame delivery, mic on, against live motion | 59.3 fps — 98.9% of target (was 18.6 fps) |
| Cost of enabling the microphone | −0.1 fps |
| Two WASAPI endpoints on one PyAudio instance | No crash (separate instances fault with 0xc0000005) |
| Consecutive nabs are distinct windows | Pass — same length, different start frames |
| Reset-after-nab mode | Pass — 2nd nab 15.0s vs 21.0s rolling, covering only the gap |
| Settings docks full-height, flush right | Pass — 496×1400 at x=2064 against a 2560 edge |
| Opening Settings twice | Pass — raises the existing window, one process |
| Panel dismisses on click-away, stays put otherwise | Pass |
| Brand conformance: shell, cream, contrast roles, px scale | Pass |
| A/V trim shifts audio on the timeline | Pass — −150 ms setting withheld 154 ms |
| A/V drift over a 3-minute run | 27 ms |
| Ring buffer cap | Held exactly at its limit; ffmpeg RSS flat at ~288 MB |
| Audio recovery after a dead endpoint | Rebuilt in 2.1s, resumed with 0 padding |
| Orphan cleanup after a hard kill | No surviving ffmpeg |
| **Frozen build: all three modes** | Pass — tray records, `--settings` renders, `--banner` daemon fires |
| **Frozen build: bundled ffmpeg + artwork + fonts** | Pass — encoder probed to NVENC, panel drew from `_MEIPASS` |
| **Wizard pages** | Pass — welcome, destination, tasks, ready all render |
| **Silent + interactive install** | Pass — exit 0, 1009 files, 4 shortcuts, Add/Remove entry |
| **Reinstall over an existing copy** | Pass — running app closed first, exit 0 |
| **Uninstall** | Pass — app, buffer, log, shortcuts, registry all gone; **76/76 nabs preserved** |
| **First run on a wiped profile** | Pass — Videos folder, encoder, both audio devices resolved with no config |

Tested in a real game: exclusive fullscreen loses the display (see above) —
use Borderless Windowed. Still unverified: autostart across an actual reboot,
HDR, non-NVIDIA encoder fallback on real AMD/Intel hardware (the probe is
exercised, the fallback path is not), and the exact `audio_offset_ms` value —
the measurement rig's correlation was too weak to confirm it, so it is set from
a reference measurement and exposed as a slider.

## Running from source

```powershell
pip install PyAudioWPatch pystray Pillow
winget install Gyan.FFmpeg
python nabd.py
```

Python 3.10+. From source the app keeps its config, buffer and log beside the
scripts rather than in `%LOCALAPPDATA%`, so a source checkout and an installed
copy don't share state.
