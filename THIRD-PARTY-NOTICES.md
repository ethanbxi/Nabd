# Third-party components

Nab'd itself is MIT-licensed (see `LICENSE`). The installer bundles the
following, each under its own terms.

## FFmpeg — GPL v3

`NabdSetup.exe` ships an **unmodified** FFmpeg binary from the Gyan.dev
Windows builds (`winget install Gyan.FFmpeg`). Those builds are configured
with `--enable-gpl` and `--enable-nonfree`-adjacent codec libraries, which
places the binary under the **GNU General Public License v3**.

- Upstream source: <https://ffmpeg.org/download.html>
- Build configuration and scripts: <https://github.com/GyanD/codexffmpeg>
- License text: <https://www.gnu.org/licenses/gpl-3.0.html>

Nab'd invokes `ffmpeg.exe` as a **separate process** over a pipe and links
against no FFmpeg library, so the two are aggregated rather than combined into
one work — which is why Nab'd's own source can be MIT while the bundled binary
stays GPL. If you redistribute the installer, you carry FFmpeg's GPL
obligations for that binary: keep it unmodified, keep this notice with it, and
point recipients at the source above.

If you would rather not ship it, delete `vendor/ffmpeg.exe` before running
`build.py`. The app falls back to any `ffmpeg` on `PATH`.

## Outfit — SIL Open Font License 1.1

Interface typeface. Copyright The Outfit Project Authors.
<https://github.com/Outfitio/Outfit-Fonts> · <https://openfontlicense.org>

## JetBrains Mono — SIL Open Font License 1.1

Monospace typeface, used for hotkeys, paths and timestamps. Copyright
JetBrains s.r.o. <https://github.com/JetBrains/JetBrainsMono>

Both are installed per-user by the installer. The OFL permits bundling and
redistribution; neither font is modified.

## Python runtime and libraries

Frozen into the application by PyInstaller:

| Component | License |
|---|---|
| CPython | Python Software Foundation License |
| Pillow | MIT-CMU |
| pystray | LGPL v3 |
| PyAudioWPatch | MIT (PortAudio: MIT) |
| PyInstaller (build tool) | GPL v2 with a bootloader exception permitting proprietary frozen apps |

`pystray` is LGPL: it is used unmodified as an importable module. If you modify
it, LGPL requires you publish those modifications.

## Inno Setup

The installer is produced by Inno Setup, which is free for commercial and
non-commercial use; the generated installer carries no license obligation of
its own. <https://jrsoftware.org/isinfo.php>
