# -*- coding: utf-8 -*-
"""nab'd mark -- geometry and posing.

The paths are lifted unmodified from the supplied artwork. Everything else in
here is the arithmetic that poses them: the head tilt, the turn, the squash,
the horn growth and the wink.

Coordinates are the artwork's own 384 x 384 box. TIGHT is the artwork bounds
with no tile; ANIM is the box the posed mark needs, which is wider because the
tilt swings the horn tips about 60 px sideways.
"""
from __future__ import annotations

# ── colour ───────────────────────────────────────────────────────────────
FIELD = "#6C3BAA"
CREAM = "#E8E4DC"
INK   = "#0A0A0C"

# ── boxes ────────────────────────────────────────────────────────────────
FULL  = (0, 0, 384, 384)          # with the rounded tile
TIGHT = (58, 55, 268, 268)        # artwork only
ANIM  = (-8, -10, 400, 400)       # artwork with room for the pose

# ── the ring ─────────────────────────────────────────────────────────────
CX, CY   = 191.8, 206.9             # head centre
R, SW    = 100.2, 22.5             # ring centreline radius, stroke
SWEEP    = 295.3                   # degrees of ring -- unchanged from the old mark
GAP      = 64.7                   # the bite
A_START, A_END = 355.1, 59.8       # gap edges, deg clockwise from 3 o'clock

# ── pose anchors ─────────────────────────────────────────────────────────
PIVOT      = (191.8, 318.0)         # neck. the head tilts about this, not its centre
HORN_ROOT  = {"l": (115.0, 130.0), "r": (269.0, 130.0)}
EYE_C      = {"l": (156.9, 217.1), "r": (227.3, 217.7)}

# ── pose constants. the three dials are TILT_MAX, TURN_MAX and SQUASH. ───
EYE_TRAVEL   = 30.0     # px the eyes slide across the head at full turn
RING_SQUEEZE = 0.05     # the silhouette barely changes -- a head is not a card
EYE_FAR      = 0.35     # far eye compresses to 1 - this
EYE_NEAR     = 0.04     # near eye widens by this
HORN_FAR     = 0.30
HORN_NEAR    = 0.06
HORN_MIN     = 0.15     # horns grow from this scale, rooted on the rim
LAG_MS       = 45.0     # horns trail the head by this
LAG_K        = 0.55
DIR          = 1        # +1 = the winking eye turns toward the viewer

# ── paths (supplied artwork, unmodified) ─────────────────────────────────
TILE = (
    "M 86.4,0 L 297.6,0 C 345.32,0 384,47.72 384,86.4 L 384,297.6 C 384,345.32 345.31,384 297.6,384 L"
    " 86.4,384 C 38.68,384 0,336.28 0,297.6 L 0,86.4 C 0,38.68 38.68,0 86.4,0 Z"
)

RING = (
    "M 303.03,197.27 L 303.03,197.28 L 280.88,199.22 C 279.41,182.31 273.17,166.26 262.84,152.79 C 25"
    "2.5,139.32 238.61,129.14 222.66,123.32 C 193.94,112.87 162.29,117.74 138.04,136.34 C 113.77,154."
    "95 100.88,184.25 103.55,214.72 C 106.21,245.19 123.99,271.79 151.12,285.92 C 178.23,300.04 210.2"
    "4,299.33 236.73,284.04 L 247.93,303.44 L 247.92,303.45 C 230.98,313.31 211.6,318.53 191.9,318.53"
    " C 190.94,318.53 189.98,318.52 189.03,318.49 L 188.93,318.49 C 188.21,318.47 187.5,318.45 186.79"
    ",318.4 C 186.46,318.39 186.12,318.37 185.78,318.35 C 127.1,315.17 80.35,266.43 80.35,206.97 C 80"
    ".35,174.65 94.16,145.5 116.2,125.12 C 117.59,123.81 119.02,122.55 120.48,121.35 C 121.94,120.12 "
    "123.42,118.94 124.94,117.8 C 125.7,117.23 126.47,116.67 127.24,116.12 C 128.01,115.57 128.79,115"
    ".02 129.58,114.49 C 131.31,113.32 133.08,112.19 134.89,111.12 C 135.53,110.73 136.17,110.36 136."
    "81,109.99 C 136.9,109.94 136.99,109.89 137.08,109.84 C 137.8,109.43 138.53,109.02 139.27,108.63 "
    "C 139.42,108.55 139.57,108.47 139.72,108.39 C 140.4,108.02 141.09,107.67 141.79,107.32 C 141.98,"
    "107.22 142.17,107.12 142.37,107.03 C 142.91,106.75 143.46,106.49 144.01,106.23 C 144.49,105.99 1"
    "44.97,105.77 145.46,105.55 C 145.78,105.4 146.1,105.25 146.43,105.11 C 146.89,104.9 147.35,104.7"
    " 147.81,104.5 C 148.4,104.24 148.99,103.99 149.59,103.75 C 149.72,103.7 149.85,103.64 149.98,103"
    ".59 C 150.79,103.26 151.61,102.93 152.44,102.63 C 152.48,102.61 152.52,102.59 152.57,102.58 C 15"
    "3.22,102.33 153.88,102.08 154.54,101.85 C 154.91,101.71 155.28,101.58 155.65,101.46 C 156.39,101"
    ".21 157.13,100.96 157.88,100.72 C 157.93,100.7 157.98,100.69 158.04,100.67 C 158.91,100.39 159.7"
    "9,100.12 160.68,99.86 C 160.72,99.85 160.75,99.84 160.79,99.83 C 166.16,98.26 171.71,97.09 177.3"
    "8,96.36 C 177.89,96.29 178.4,96.23 178.91,96.17 C 179.44,96.1 179.98,96.04 180.51,95.99 C 184.26"
    ",95.61 188.06,95.41 191.9,95.41 C 220,95.41 246.86,105.9 267.51,124.95 C 288.03,143.87 300.64,16"
    "9.55 303.03,197.27 Z"
)

HORN_L = (
    "M 160.8,99.83 C 130.84,108.54 106.08,129.49 92.29,156.91 L 90.24,154.57 L 85.79,149.03 C 80.71,1"
    "42.02 75.39,132.28 72.78,119.91 C 69.11,102.46 72.34,87.68 75.7,78.34 L 80.32,65.47 L 90.96,74.0"
    "8 C 99.31,80.85 108.62,86.33 118.63,90.42 C 125.95,93.39 133.58,95.6 141.33,96.93 C 142.29,97.11"
    " 143.24,97.26 144.2,97.4 L 160.8,99.83 Z"
)

HORN_R = (
    "M 223.2,99.83 C 253.16,108.54 277.92,129.49 291.7,156.91 L 293.75,154.57 L 298.21,149.03 C 303.2"
    "8,142.02 308.61,132.28 311.21,119.91 C 314.88,102.46 311.66,87.68 308.3,78.34 L 303.68,65.47 L 2"
    "93.03,74.08 C 284.68,80.85 275.37,86.33 265.36,90.42 C 258.04,93.39 250.41,95.6 242.66,96.93 C 2"
    "41.7,97.11 240.75,97.26 239.79,97.4 L 223.2,99.83 Z"
)

EYE_L = (
    "M 179.6,207.45 C 179.6,231.74 169.4,251.43 156.83,251.43 C 144.24,251.43 134.05,231.74 134.05,20"
    "7.45 C 134.05,198.32 135.49,189.84 137.96,182.81 L 179.6,207.45 Z"
)

EYE_R = (
    "M 250.02,207.45 C 250.02,231.74 239.82,251.43 227.25,251.43 C 214.66,251.43 204.47,231.74 204.47"
    ",207.45 L 246.47,183.87 C 248.72,190.69 250.02,198.78 250.02,207.45 Z"
)

# ── wordmark. letters are STROKED; the horns on the n are filled. ───────
WORD_BOX = '-2 -2 466.6 152.5'
WORD_SW = 19.5
WORD_PARTS = [
    (0, 'f', 0, 'M 36.98,61.25 C 24.62,64.84 14.41,73.49 8.72,84.8 L 7.87,83.83 L 6.04,81.54 C 3.94,78.65 1.75,74.63 0.67,69.53 C -0.84,62.33 0.49,56.24 1.87,52.39 L 3.78,47.07 L 8.17,50.63 C 11.62,53.42 15.46,55.68 19.58,57.37 C 22.6,58.59 25.75,59.5 28.95,60.05 C 29.35,60.13 29.74,60.19 30.13,60.25 L 36.98,61.25 Z'),
    (1, 'f', 0, 'M 64.72,61.25 C 77.08,64.84 87.29,73.49 92.98,84.8 L 93.82,83.83 L 95.66,81.54 C 97.75,78.65 99.95,74.63 101.02,69.53 C 102.54,62.33 101.21,56.24 99.82,52.39 L 97.92,47.07 L 93.52,50.63 C 90.08,53.42 86.24,55.68 82.11,57.37 C 79.09,58.59 75.94,59.5 72.75,60.05 C 72.35,60.13 71.96,60.19 71.56,60.25 L 64.72,61.25 Z'),
    (2, 's', 19.5, 'M 14.85,138.75 L 14.85,102.75 C 14.85,89.89 21.71,78 32.85,71.57 C 43.98,65.14 57.71,65.14 68.85,71.57 C 79.98,78 86.85,89.89 86.85,102.75 L 86.85,138.75'),
    (3, 's', 19.5, 'M 203.85,102.75 C 203.85,122.63 187.73,138.75 167.85,138.75 C 147.96,138.75 131.85,122.63 131.85,102.75 C 131.85,82.87 147.96,66.75 167.85,66.75 C 187.73,66.75 203.85,82.87 203.85,102.75'),
    (4, 's', 19.5, 'M 203.85,66.75 L 203.85,138.75'),
    (5, 's', 19.5, 'M 248.85,9.75 L 248.85,138.75'),
    (6, 's', 19.5, 'M 320.85,102.75 C 320.85,122.63 304.73,138.75 284.85,138.75 C 264.96,138.75 248.85,122.63 248.85,102.75 C 248.85,82.87 264.96,66.75 284.85,66.75 C 304.73,66.75 320.85,82.87 320.85,102.75'),
    (7, 's', 19.5, 'M 350.85,9.75 L 350.85,45.75'),
    (8, 's', 19.5, 'M 452.85,102.75 C 452.85,122.63 436.73,138.75 416.85,138.75 C 396.96,138.75 380.85,122.63 380.85,102.75 C 380.85,82.87 396.96,66.75 416.85,66.75 C 436.73,66.75 452.85,82.87 452.85,102.75'),
    (9, 's', 19.5, 'M 452.85,9.75 L 452.85,138.75'),
]


def _mix(fg, bg, a):
    """`fg` composited onto solid `bg` at alpha `a`, as a hex string.

    Opacity has to be baked into the colour because **svglib honours no form
    of transparency**: group `opacity`, path `opacity`, `fill-opacity`,
    8-digit hex and `rgba()` all rasterise fully opaque (measured, all five).
    The browser preview faded the horns and the eyes in with `opacity`, so
    porting that verbatim left them on screen for the whole 4,120 ms -- the
    horns as permanent 15% stubs, the eyes never opening. Nothing caught it:
    the timeline was correct, and the bug was entirely in the rasteriser.

    The mark only ever sits on a solid field, which is why `render()` bakes the
    background in anyway, so mixing is exact rather than an approximation.
    """
    a = max(0.0, min(1.0, a))
    f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(
        int(round(y + (x - y) * a)) for x, y in zip(f, b))


def _about(ox, oy, t):
    return "translate(%.3f,%.3f) %s translate(%.3f,%.3f)" % (ox, oy, t, -ox, -oy)


def pose_svg(f, size=None, art=CREAM, box=ANIM, ring_stroke_path=None,
             bg=FIELD):
    """One frame of the mark as an SVG string.

    `f` is a Frame from nabd_banner.sample(). Rasterise this with svglib at
    build time; never at launch.
    """
    from math import cos, sin, radians
    if ring_stroke_path is None:
        ring_stroke_path = ring_arc(f.ring)
    sy = f.squash
    sx = 1.0 + (1.0 - sy) * 0.62
    head = _about(PIVOT[0], PIVOT[1], "rotate(%.4f) scale(%.5f,%.5f)" % (f.tilt, sx, sy))
    tu = f.turn * DIR
    at = abs(tu)
    ring_t = _about(CX, CY, "scale(%.5f,1)" % (1 - RING_SQUEEZE * at))
    horn_t = _about(CX, CY, "rotate(%.4f)" % f.horn_lag)
    grow = HORN_MIN + (1 - HORN_MIN) * f.horns
    near = "r" if tu >= 0 else "l"
    kn, kf = 1 + HORN_NEAR * at, 1 - HORN_FAR * at
    dx = -EYE_TRAVEL * tu
    en, ef_ = 1 + EYE_NEAR * at, 1 - EYE_FAR * at
    eo = 0.25 + 0.75 * f.eyes
    w = 1 - f.wink * 0.94

    horn_fill = _mix(art, bg, min(1.0, f.horns * 2.2))
    eye_fill = _mix(art, bg, f.eyes)

    def horn(side, d):
        k = kn if side == near else kf
        return '<g transform="%s"><path d="%s" fill="%s"/></g>' % (
            _about(HORN_ROOT[side][0], HORN_ROOT[side][1],
                   "scale(%.5f,%.5f)" % (k * grow, grow)), d, horn_fill)

    def eye(side, d, shut):
        # `shut` is fixed per side, not derived from `near`: the wink belongs
        # to the RIGHT eye always. Deriving it from `near` made the left eye
        # squint for the 28 ms around 1704-1732 where `turn` is still slightly
        # negative from the anticipation, which reads as a flicker.
        k = en if side == near else ef_
        t = "translate(%.3f,0) %s" % (dx, _about(
            EYE_C[side][0], EYE_C[side][1],
            "scale(%.5f,%.5f)" % (k, eo * (w if shut else 1.0))))
        return '<g transform="%s"><path d="%s" fill="%s"/></g>' % (t, d, eye_fill)

    dim = ' width="%d" height="%d"' % (size, size) if size else ""
    return (
        # Horns are drawn UNDER the ring. With opacity baked into the fill,
        # a part-grown horn painted OVER the ring would show a mixed-with-field
        # patch where it crosses the rim (the roots sit on the stroke). Under
        # the ring, the rim covers that overlap with solid art -- which is what
        # true alpha compositing of two same-coloured shapes gives anyway.
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="%d %d %d %d"%s fill="none">'
        '<g transform="%s" fill="%s">'
        '<g transform="%s">%s%s</g>'
        '<g transform="%s"><path d="%s" fill="none" stroke="%s" stroke-width="%.1f" '
        'stroke-linecap="butt"/></g>'
        '%s%s</g></svg>'
        % (box[0], box[1], box[2], box[3], dim, head, art,
           horn_t, horn("l", HORN_L), horn("r", HORN_R),
           ring_t, ring_stroke_path, art, SW,
           eye("l", EYE_L, False), eye("r", EYE_R, True)))


def ring_arc(progress=1.0, r=None):
    """The drawn part of the ring, as an explicit partial arc.

    The ring starts at the gap's trailing edge (A_START) and sweeps SWEEP
    degrees the LONG way round, in the negative-angle direction -- which is
    counter-clockwise on screen, since SVG's y axis points down. `progress`
    below 1 shortens the arc; 0 draws nothing.

    This is deliberately NOT done with stroke-dasharray/stroke-dashoffset.
    The browser preview used a dash offset, and porting that verbatim produced
    a flipbook in which the ring was fully drawn in every single frame:
    **svglib silently ignores stroke-dashoffset**, so ring=0.0 and ring=1.0
    rasterised to byte-identical images. The draw-on and the wind-back had
    both quietly disappeared while every timeline assertion still passed,
    because the bug lived in the renderer, not in the data. Emitting the arc
    geometry itself is the only version that survives rasterisation.
    """
    from math import cos, sin, radians
    r = R if r is None else r
    progress = max(0.0, min(1.0, progress))
    if progress <= 0.0:
        return ""
    span = SWEEP * progress
    a0, a1 = A_START, A_START - span          # negative direction = ccw on screen
    p = lambda a: (CX + r * cos(radians(a)), CY + r * sin(radians(a)))
    (x0, y0), (x1, y1) = p(a0), p(a1)
    large = 1 if span > 180.0 else 0
    return "M %.3f,%.3f A %.3f,%.3f 0 %d 0 %.3f,%.3f" % (x0, y0, r, r, large, x1, y1)


from math import pi
RING_LEN = 2 * pi * R * SWEEP / 360.0
