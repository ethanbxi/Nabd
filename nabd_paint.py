"""Pillow helpers for the shapes Tk cannot draw.

Tk has no rounded corners, no gradients, no shadows and no alpha compositing on
widgets. Everything in that category is pre-rendered here and shown in a Label or
Canvas image.

Two rules that will bite otherwise:

1. FLATTEN, don't rely on alpha. A Tk widget cannot be transparent, so every
   image is composited onto the parent's background colour before it is handed to
   Tk. Always pass `bg`.
2. KEEP A REFERENCE. PhotoImage is garbage collected the moment nothing points at
   it and the widget silently renders blank. `photo()` below stores the reference
   on the widget itself, which is the usual fix.
"""
from __future__ import annotations
from functools import lru_cache
import math

from PIL import Image, ImageDraw

import nabd_tokens as T


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _flatten(img: Image.Image, bg: str) -> Image.Image:
    base = Image.new("RGB", img.size, _rgb(bg))
    base.paste(img, (0, 0), img)
    return base


@lru_cache(maxsize=512)
def rounded_rect(w: int, h: int, r: int, fill: str, outline: str | None = None,
                 width: int = 1, bg: str = T.PANEL, ss: int = 4) -> Image.Image:
    """Antialiased rounded rectangle, flattened onto `bg`.

    Drawn at `ss`x and downsampled -- Pillow's rounded_rectangle is not
    antialiased on its own and the corners look chewed at 1x.
    """
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, w * ss - 1, h * ss - 1], radius=r * ss,
        fill=_rgb(fill) + (255,),
        outline=(_rgb(outline) + (255,)) if outline else None,
        width=width * ss if outline else 0,
    )
    return _flatten(img.resize((w, h), Image.LANCZOS), bg)


@lru_cache(maxsize=32)
def _corner_alpha(r: int, width: int, ss: int = 4):
    """(inside, outline) alpha for a rounded box, as four r x r corner pairs.

    Cut from one rounded rectangle so the arc matches rounded_rect exactly.
    """
    size = r * 2 * ss
    inside = Image.new("L", (size, size), 0)
    ImageDraw.Draw(inside).rounded_rectangle([0, 0, size - 1, size - 1],
                                             radius=r * ss, fill=255)
    ring = Image.new("L", (size, size), 0)
    ImageDraw.Draw(ring).rounded_rectangle([0, 0, size - 1, size - 1],
                                           radius=r * ss, outline=255,
                                           width=width * ss)
    inside = inside.resize((r * 2, r * 2), Image.LANCZOS)
    ring = ring.resize((r * 2, r * 2), Image.LANCZOS)
    boxes = ((0, 0, r, r), (r, 0, r * 2, r),
             (0, r, r, r * 2), (r, r, r * 2, r * 2))
    return [(inside.crop(b), ring.crop(b)) for b in boxes]


def corner_over(patch: Image.Image, r: int, index: int,
                outline: str | None, bg: str, width: int = 1) -> Image.Image:
    """One corner of a rounded box whose inside is `patch`, not a flat colour.

    corner_masks assumes the pixels under a corner are the frame's own fill.
    Where they are not - a poster filling a nab card, the selected cell of a
    segmented control reaching the end of its track - that assumption paints a
    square notch out of whatever is really there.
    """
    inside, ring = _corner_alpha(r, width)[index]
    out = Image.new("RGB", (r, r), _rgb(bg))
    out.paste(patch.convert("RGB").resize((r, r)) if patch.size != (r, r)
              else patch.convert("RGB"), (0, 0), inside)
    if outline:
        out.paste(Image.new("RGB", (r, r), _rgb(outline)), (0, 0), ring)
    return out


@lru_cache(maxsize=64)
def linear_gradient(w: int, h: int, angle: float, c0: str, c1: str) -> Image.Image:
    """`angle` in CSS terms: 0deg points up, 160deg is down-and-slightly-left.

    Evaluated on a coarse grid and scaled up. The function is linear, so
    interpolation reproduces it to within a rounding step, and a Python pixel
    loop over a full-size hero card costs about 130ms - which lands squarely in
    the pause before the panel animates.
    """
    a = math.radians(angle - 90.0)
    dx, dy = math.cos(a), math.sin(a)
    r0, g0, b0 = _rgb(c0)
    r1, g1, b1 = _rgb(c1)
    # Aspect matters: squashing to a square grid changes how the axis projects
    # onto the box and shifts the whole ramp. Scale both sides by one factor.
    if max(w, h) > 96:
        k = 96.0 / max(w, h)
        cw, ch = max(2, round(w * k)), max(2, round(h * k))
    else:
        cw, ch = w, h
    img = Image.new("RGB", (cw, ch))
    px = img.load()
    # project each pixel onto the gradient axis, normalised 0..1
    ext = abs(dx) * cw + abs(dy) * ch
    ox, oy = (cw if dx < 0 else 0), (ch if dy < 0 else 0)
    for y in range(ch):
        for x in range(cw):
            t = ((x - ox) * dx + (y - oy) * dy) / ext
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            px[x, y] = (round(r0 + (r1 - r0) * t),
                        round(g0 + (g1 - g0) * t),
                        round(b0 + (b1 - b0) * t))
    return img if (cw, ch) == (w, h) else img.resize((w, h), Image.BILINEAR)


@lru_cache(maxsize=16)
def hero_bg(w: int, h: int, bg: str = T.PANEL) -> Image.Image:
    """Hero card: 160deg purple-deep wash into SURFACE, rounded, 1px border."""
    grad = linear_gradient(w, h, 160.0, "#2A1B3D", T.SURFACE)   # deep wash, pre-blended
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * 4 - 1, h * 4 - 1], radius=T.px(T.R_PANEL) * 4, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    out = Image.new("RGB", (w, h), _rgb(bg))
    out.paste(grad, (0, 0), mask)
    ring = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle(
        [0, 0, w * 4 - 1, h * 4 - 1], radius=T.px(T.R_PANEL) * 4,
        outline=_rgb(T.LINE_STRONG) + (255,), width=T.px(1) * 4)
    out.paste(Image.new("RGB", (w, h), _rgb(T.LINE_STRONG)), (0, 0),
              ring.resize((w, h), Image.LANCZOS).split()[3])
    return out


@lru_cache(maxsize=8)
def toggle(on: bool, bg: str = T.SURFACE) -> Image.Image:
    w, h, k = T.px(T.TOGGLE_W), T.px(T.TOGGLE_H), T.px(T.TOGGLE_KNOB)
    track = rounded_rect(w, h, h // 2,
                         T.PURPLE if on else T.RAISED,
                         T.PURPLE if on else T.LINE_STRONG, T.px(1), bg)
    img = track.copy()
    pad = (h - k) // 2
    x = w - k - pad if on else pad
    knob = rounded_rect(k, k, k // 2, T.TEXT_ON_PURPLE, None, 1,
                        T.PURPLE if on else T.RAISED)
    img.paste(knob, (x, pad))
    return img


@lru_cache(maxsize=256)
def meter(w: int, pct: float, level: str = "ok", bg: str = T.SURFACE) -> Image.Image:
    h = T.px(T.METER_H)
    fill = {"ok": T.PURPLE_LIGHT, "warn": T.WARN, "danger": T.DANGER}[level]
    img = rounded_rect(w, h, h // 2, T.LINE, None, 1, bg)
    fw = max(h, int(w * max(0.0, min(1.0, pct))))
    img.paste(rounded_rect(fw, h, h // 2, fill, None, 1, T.LINE), (0, 0))
    return img


def photo(widget, img: Image.Image, attr: str = "_img"):
    """Make a PhotoImage and pin it to `widget` so it is not collected."""
    from PIL import ImageTk
    ph = ImageTk.PhotoImage(img)
    setattr(widget, attr, ph)
    return ph


@lru_cache(maxsize=64)
def chevron(size: int, colour: str, bg: str) -> Image.Image:
    """Down chevron, 1.6px stroke, round caps -- the icon spec in miniature."""
    ss = 4
    s = size * ss
    img = Image.new("RGB", (s, s), _rgb(bg))
    d = ImageDraw.Draw(img)
    w = max(1, int(round(1.6 * T.scale() * ss)))
    pts = [(s * 0.22, s * 0.40), (s * 0.50, s * 0.66), (s * 0.78, s * 0.40)]
    d.line(pts, fill=_rgb(colour), width=w, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2],
                  fill=_rgb(colour))
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=32)
def play_glyph(size: int, colour: str, bg: str, opacity: float = 1.0):
    """Filled play triangle for a nab's poster."""
    ss = 4
    s = size * ss
    img = Image.new("RGB", (s, s), _rgb(bg))
    d = ImageDraw.Draw(img)
    d.polygon([(s * 0.30, s * 0.18), (s * 0.82, s * 0.50), (s * 0.30, s * 0.82)],
              fill=_rgb(colour))
    out = img.resize((size, size), Image.LANCZOS)
    if opacity < 1.0:
        out = Image.blend(Image.new("RGB", out.size, _rgb(bg)), out, opacity)
    return out


@lru_cache(maxsize=128)
def knob(d: int, colour: str, bg: str) -> Image.Image:
    """Slider knob: a plain disc. The spec's soft shadow is dropped -- Tk has
    no alpha under the widget, so a baked shadow would show its own edges."""
    ss = 4
    img = Image.new("RGB", (d * ss, d * ss), _rgb(bg))
    ImageDraw.Draw(img).ellipse([0, 0, d * ss - 1, d * ss - 1], fill=_rgb(colour))
    return img.resize((d, d), Image.LANCZOS)


# ---------------------------------------------------------------------------
# icons: 16px, 1.6px stroke, round caps and joins, single colour
# ---------------------------------------------------------------------------

def _stroke(size, ss):
    return max(1, int(round(1.6 * T.scale() * ss)))


@lru_cache(maxsize=64)
def folder_icon(size: int, colour: str, bg: str) -> Image.Image:
    ss = 4
    s = size * ss
    img = Image.new("RGB", (s, s), _rgb(bg))
    d = ImageDraw.Draw(img)
    w = _stroke(size, ss)
    c = _rgb(colour)
    # tab + body, matching the reference's rounded folder path
    d.rounded_rectangle([s * 0.13, s * 0.26, s * 0.87, s * 0.76],
                        radius=s * 0.09, outline=c, width=w)
    d.line([(s * 0.13, s * 0.32), (s * 0.40, s * 0.32),
            (s * 0.50, s * 0.42), (s * 0.87, s * 0.42)],
           fill=c, width=w, joint="curve")
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=64)
def search_icon(size: int, colour: str, bg: str) -> Image.Image:
    ss = 4
    s = size * ss
    img = Image.new("RGB", (s, s), _rgb(bg))
    d = ImageDraw.Draw(img)
    w = _stroke(size, ss)
    c = _rgb(colour)
    d.ellipse([s * 0.16, s * 0.16, s * 0.76, s * 0.76], outline=c, width=w)
    d.line([(s * 0.70, s * 0.70), (s * 0.88, s * 0.88)], fill=c, width=w)
    for p in ((s * 0.70, s * 0.70), (s * 0.88, s * 0.88)):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2],
                  fill=c)
    return img.resize((size, size), Image.LANCZOS)


@lru_cache(maxsize=32)
def scroll_thumb(w: int, h: int, colour: str, bg: str) -> Image.Image:
    """The reference's scrollbar thumb: a rounded bar inset 3px from a
    transparent track, so it reads as floating over the panel."""
    inset = T.px(3)
    img = Image.new("RGB", (w, h), _rgb(bg))
    bar = rounded_rect(max(1, w - inset * 2), max(1, h),
                       max(1, (w - inset * 2) // 2), colour, None, 1, bg)
    img.paste(bar, (inset, 0))
    return img


@lru_cache(maxsize=16)
def timeline(w: int, h: int) -> Image.Image:
    """The buffer bar: rounded track, purple wash, bright NOW edge.

    One cached image rather than ~48 canvas rectangles - those cost about 45ms
    every time the hero is redrawn, which is on every open and every change of
    nab length.

    Deliberately not the ring mark: the brand guidelines forbid reusing the
    logo as a progress indicator, and a buffer is exactly the temptation they
    had in mind.
    """
    grad = linear_gradient(w, h, 90.0, "#231E2D", "#37264F")
    img = rounded_rect(w, h, T.px(8), T.RAISED, T.LINE_STRONG, T.px(1),
                       T.SURFACE)
    mask = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * 4 - 1, h * 4 - 1], radius=T.px(8) * 4, fill=255)
    inner = mask.resize((w, h), Image.LANCZOS)
    img.paste(grad, (0, 0), inner)
    d = ImageDraw.Draw(img)
    d.rectangle([w - T.px(3), 0, w - 1, h - 1], fill=_rgb(T.PURPLE_LIGHT))
    return img
