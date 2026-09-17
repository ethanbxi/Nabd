# -*- coding: utf-8 -*-
"""Render the ERROR banner to a GIF, for looking at rather than for shipping.

    python make_reference_gif_error.py reference

Two files land in the output directory:

  error-4120ms.gif    the whole banner on the shell backdrop, actual timeline
  error-mark-closeup.gif  the mark alone, large, so the shut eyes and the
                          horn follow-through are actually visible

Both are driven by nabd_banner.sample() and nabd_mark.pose_svg() - the same
two calls the real build uses - so if the GIF and the app ever disagree, the
app is wrong. This is a reference, not an asset: nothing in nab'd ships a GIF.

Layout note: the card's interior proportions are taken from the approved
preview, which laid out at 252x64, and are scaled here to nabd_banner's
canonical CARD_W x CARD_H of 308x76 (k = 308/252). The copy block is set in
DejaVu rather than Outfit/JetBrains Mono, which are not installed here; the
text is placeholder either way. Everything that MOVES is exact.
"""
from __future__ import annotations

import io, pathlib, sys

import nabd_banner_error as B
import nabd_mark as M

# ── colour ───────────────────────────────────────────────────────────────
PURPLE = (0x8E, 0x32, 0x29)          # the ERROR field, not the brand purple
PURPLE_LIGHT = (0xD2, 0x69, 0x5C)    # the lit edge
CREAM = (0xE8, 0xE4, 0xDC)
META = (0xF2, 0xD8, 0xD4)

# ── the approved preview's interior, in its own 252x64 units ─────────────
REF_W, REF_H = 252.0, 64.0
K = B.CARD_W / REF_W          # 1.2222 -- preview units to canonical units
MARK_BOX = 44.0               # .m is 44px with margin 0 -7px
MARK_X = 8.0                  # 15 padding - 7 negative margin
COPY_X = 57.0                 # 15 + (44-14) + 12 gap
TITLE_PX, META_PX = 13.5, 10.5
EDGE_H, RULE_H = 4.0, 3.0
INSET = 16.0                  # banner sits 16px off the corner of the shell

FPS_MS = 20                   # GIF delays are centiseconds; 20 ms = 2 cs


def _font(mono, px):
    """The real faces when they are present, DejaVu only as a last resort.

    The copy block is placeholder text either way, but Outfit Medium and
    JetBrains Mono are what the app actually sets it in, and a reference that
    substitutes the type misrepresents how crowded the card is.
    """
    from PIL import ImageFont
    for root, name in (("/tmp/fonts/ttf/", "JetBrainsMono-Regular.ttf" if mono
                        else "Outfit-Medium.ttf"),
                       ("/usr/share/fonts/truetype/dejavu/",
                        "DejaVuSansMono.ttf" if mono else "DejaVuSans-Bold.ttf")):
        try:
            return ImageFont.truetype(root + name, int(round(px)))
        except Exception:
            continue
    return ImageFont.load_default()


def _mark(size, art=CREAM, bg=PURPLE, f=None):
    """One posed mark, rasterised at `size` px on a solid field."""
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    svg = M.pose_svg(f, size=size, art="#%02X%02X%02X" % art,
                     bg="#%02X%02X%02X" % bg)
    d = svg2rlg(io.BytesIO(svg.encode("utf-8")))
    # svglib reads the SVG width as POINTS, so a 60 px request returns 45 px.
    k = float(size) / float(d.width)
    d.width = d.height = size
    d.scale(k, k)
    return renderPM.drawToPIL(d, bg=(bg[0] << 16) | (bg[1] << 8) | bg[2])


def _backdrop(w, h):
    """The shell, with the preview's soft radial so the card has something to
    sit on. Flat near-black makes the purple card look like a sticker."""
    from PIL import Image
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy = w * 0.72, h * 0.16
    far = ((max(cx, w - cx)) ** 2 + (max(cy, h - cy)) ** 2) ** 0.5
    stops = ((0.00, (0x23, 0x23, 0x2C)), (0.52, (0x14, 0x14, 0x19)),
             (1.00, (0x0B, 0x0B, 0x0E)))
    for y in range(h):
        for x in range(w):
            t = min(1.0, (((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) / far)
            for i in range(len(stops) - 1):
                a, ca = stops[i]
                b, cb = stops[i + 1]
                if t <= b or i == len(stops) - 2:
                    u = 0.0 if b == a else (t - a) / (b - a)
                    u = max(0.0, min(1.0, u))
                    px[x, y] = tuple(int(round(p + (q - p) * u))
                                     for p, q in zip(ca, cb))
                    break
    return img


def banner_frames(scale=2.0):
    """-> [PIL.Image] for the whole banner, one every FPS_MS."""
    from PIL import Image, ImageDraw

    def s(v):
        return v * K * scale

    stage_w = int(round(s(REF_W) + 2 * s(INSET)))
    stage_h = int(round(s(REF_H) + 2 * s(INSET)))
    back = _backdrop(stage_w, stage_h)
    inner_w, inner_h = int(round(s(REF_W))), int(round(s(REF_H)))
    right = stage_w - int(round(s(INSET)))
    bottom = stage_h - int(round(s(INSET)))

    mark_px = int(round(s(MARK_BOX)))
    title_f, meta_f = _font(False, s(TITLE_PX)), _font(True, s(META_PX))

    out = []
    t = 0
    while t < B.TOTAL_MS:
        f = B.sample(float(t))
        # f.w / f.h are already in canonical units (CARD_W x CARD_H); only
        # the preview-unit layout constants go through s().
        w = int(round(f.w * scale))
        h = int(round(f.h * scale))
        frame = back.copy()

        if w > 0 and h > 0 and f.alpha > 0.002:
            # the full interior, anchored bottom-left of the card
            inner = Image.new("RGB", (inner_w, inner_h), PURPLE)
            if f.ring > 0 or f.horns > 0 or f.eyes > 0:
                glyph = _mark(mark_px, CREAM, PURPLE, f)
                inner.paste(glyph, (int(round(s(MARK_X))),
                                    (inner_h - mark_px) // 2))
            d = ImageDraw.Draw(inner)
            if f.copy > 0.002:
                def mix(c):
                    return tuple(int(round(p + (q - p) * f.copy))
                                 for p, q in zip(PURPLE, c))
                x = int(round(s(COPY_X)))
                block = s(TITLE_PX) * 1.2 + s(META_PX) * 1.35
                y = (inner_h - block) / 2
                d.text((x, y), "Couldn't save", font=title_f, fill=mix(CREAM))
                d.text((x, y + s(TITLE_PX) * 1.2), "disk full - 0 bytes free",
                       font=meta_f, fill=mix(META))
            # the 4 px lit edge, and the dismiss rule draining over it
            eh = max(1, int(round(s(EDGE_H))))
            if f.line > 0.002:
                d.rectangle([0, inner_h - eh, inner_w, inner_h],
                            fill=tuple(int(round(p + (q - p) * f.line))
                                       for p, q in zip(PURPLE, PURPLE_LIGHT)))
            if f.line < 0.998 and f.drain > 0:
                rh = max(1, int(round(s(RULE_H))))
                o = (1 - f.line) * 0.75
                d.rectangle([0, inner_h - rh, int(round(inner_w * f.drain)),
                             inner_h],
                            fill=tuple(int(round(p + (q - p) * o))
                                       for p, q in zip(PURPLE, CREAM)))

            card = inner.crop((0, inner_h - h, min(w, inner_w), inner_h))
            if card.width < w:     # card wider than the interior: pad purple
                pad = Image.new("RGB", (w, h), PURPLE)
                pad.paste(card, (0, 0))
                card = pad

            # border-radius: 2 + 9 * min(1, (h-4)/60) in preview units, where
            # 60 spanned LINE_H..REF_H. Expressed against the canonical card.
            grow = (f.h - B.LINE_H) / float(B.CARD_H - B.LINE_H)
            r = (2 + 9 * min(1.0, grow)) * K * scale
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, w - 1, h - 1], radius=max(0, r), fill=255)
            if f.alpha < 0.998:
                mask = mask.point(lambda v: int(v * f.alpha))
            frame.paste(card, (right - w, bottom - h), mask)

        out.append(frame)
        t += FPS_MS
    return out


def mark_frames(px=220):
    """-> [PIL.Image] of the mark alone, big enough to read the mechanics."""
    out = []
    t = 0
    while t < B.TOTAL_MS:
        out.append(_mark(px, CREAM, PURPLE, B.sample(float(t))))
        t += FPS_MS
    return out


def save_gif(frames, path):
    """Write every frame, on one shared palette.

    Pillow merges runs of identical frames and SUMS their durations, so the
    file reports fewer frames than were passed in (206 -> 170 here) while the
    wall clock still adds up to TOTAL_MS. That is fine and is checked below.
    `optimize=True` is off because it reorders that merging in ways that do
    not preserve the total.
    """
    from PIL import Image
    strip = Image.new("RGB", (frames[0].width,
                              frames[0].height * len(frames[::12])))
    for i, f in enumerate(frames[::12]):
        strip.paste(f, (0, i * frames[0].height))
    palette = strip.quantize(colors=128, method=Image.MEDIANCUT)
    conv = [f.quantize(palette=palette, dither=Image.Dither.NONE)
            for f in frames]
    conv[0].save(path, save_all=True, append_images=conv[1:],
                 duration=[FPS_MS] * len(conv), loop=0, optimize=False,
                 disposal=1)
    return path


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "reference")
    out.mkdir(parents=True, exist_ok=True)
    a = save_gif(banner_frames(), out / "error-4120ms.gif")
    b = save_gif(mark_frames(), out / "error-mark-closeup.gif")
    from PIL import Image
    for p in (a, b):
        im = Image.open(p)
        total, n = 0, 0
        try:
            while True:
                total += im.info.get("duration", 0); n += 1; im.seek(im.tell() + 1)
        except EOFError:
            pass
        assert abs(total - B.TOTAL_MS) <= FPS_MS, \
            "%s runs %d ms, should be %d" % (p.name, total, B.TOTAL_MS)
        print("%-30s %6.0f kB  %3d stored frames  %d ms total  OK"
              % (p.name, p.stat().st_size / 1024, n, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
