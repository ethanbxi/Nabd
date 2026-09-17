# -*- coding: utf-8 -*-
"""Render the error banner to an MP4 with its sound, for looking at.

    python make_example_mp4.py out.mp4 [--save]

A GIF cannot carry audio and the two halves of this were designed together, so
the only honest way to show the thing is a video. Frames come from
banner_frames(), audio from the shipped WAV -- the same two assets the app
uses, not a re-recording.

Lead-in and tail are padded on BOTH streams by the same amount, so the sound
still starts on the frame the line starts sliding.
"""
from __future__ import annotations

import pathlib, subprocess, sys, tempfile, wave

LEAD_MS, TAIL_MS = 400, 700
SCALE = 2.5


def render(dst, which="error"):
    if which == "save":
        sys.path.insert(0, "/home/claude/nabd/banner1to1")
        import make_reference_gif as G
        wav = pathlib.Path("/home/claude/nabd/sfx/wav4/nabd-sound-pip.wav")
    else:
        import make_reference_gif_error as G
        wav = pathlib.Path("assets/sound/nabd-sound-error.wav")

    frames = G.banner_frames(scale=SCALE)
    w, h = frames[0].size
    w, h = w - (w % 2), h - (h % 2)                  # h264 needs even dimensions
    fps = round(1000 / G.FPS_MS)
    lead = round(LEAD_MS / G.FPS_MS)
    tail = round(TAIL_MS / G.FPS_MS)
    seq = [frames[0]] * lead + frames + [frames[-1]] * tail

    tmp = pathlib.Path(tempfile.mkdtemp())
    for i, f in enumerate(seq):
        f.crop((0, 0, w, h)).save(tmp / ("f%05d.png" % i))

    # pad the audio by exactly LEAD_MS so cue 0 lands on the first moving frame
    with wave.open(str(wav), "rb") as r:
        p = r.getparams()
        data = r.readframes(r.getnframes())
    silence = b"\x00" * (int(p.framerate * LEAD_MS / 1000) * p.sampwidth * p.nchannels)
    tailsil = b"\x00" * (int(p.framerate * TAIL_MS / 1000) * p.sampwidth * p.nchannels)
    padded = tmp / "audio.wav"
    with wave.open(str(padded), "wb") as o:
        o.setparams(p)
        o.writeframes(silence + data + tailsil)

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", str(tmp / "f%05d.png"),
        "-i", str(padded),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17",
        "-preset", "slow", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest", str(dst)], check=True)
    return dst, w, h, len(seq), fps


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else "reference/error-banner.mp4"
    which = "save" if "--save" in sys.argv else "error"
    p, w, h, n, fps = render(pathlib.Path(dst), which)
    print("%s  %dx%d  %d frames @ %d fps  %.0f kB"
          % (p, w, h, n, fps, p.stat().st_size / 1024))
