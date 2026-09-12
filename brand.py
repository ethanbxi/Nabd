"""
Nab'd brand system: palette, type scale, and the logo drawn from its geometry.

The mark and wordmark are reproduced from the measurements in the brand
guidelines rather than by rasterising the SVGs, so they stay crisp at tray sizes
and need no image dependencies. brand/ holds the reference assets this is
measured against.

Geometry, read off nabd-mark-cream.svg and nabd-wordmark-cream.svg:

  Mark        100u box, centre (50,50), radius 34u, stroke 14u
              gap spans 30deg to 95deg - 65deg wide, centred on 1 o'clock
              lit segment 95deg to 160deg, the 65deg counter-clockwise of it
              main arc 160deg through 30deg, terminals butt, never rounded
  Wordmark    stroke 13u, round caps, x-height 48u, ascender 86u

The wordmark and the app tile are shown from brand/render/*.png, rasterised
from the supplied SVGs by render_assets.py. The geometry below still drives the
animated mark - a partial stroke cannot come from a bitmap - and stands in if
the renders are missing.
"""

import sys
from pathlib import Path

# -- palette ---------------------------------------------------------------

PURPLE = "#6C3BAA"        # the brand. Logo field, primary actions.
PURPLE_LIGHT = "#9B6BD8"  # dark UI only - PURPLE is 2.7:1 on SHELL
PURPLE_DEEP = "#4E2A7D"   # pressed, hover, shadow
CREAM = "#E8E4DC"         # the logo on purple; body text on near-black
INK = "#17161A"           # body text on light; raised surfaces on dark
SHELL = "#0A0A0C"         # the app itself

# Nabd Purple only ever appears as a *field* with cream on top (7.2:1). Any
# purple linework or text on a dark surface uses PURPLE_LIGHT instead.

# -- type ------------------------------------------------------------------

# Outfit ships its weights as separate families to GDI, so a weight is chosen
# by picking the right family rather than by asking Tk for "bold". Each entry
# degrades through the guidelines' own fallback: Outfit -> system-ui,
# JetBrains Mono -> ui-monospace.
_FALLBACKS = {
    "Outfit": ("Outfit", "Segoe UI Variable Text", "Segoe UI", "Arial"),
    "Outfit Medium": ("Outfit Medium", "Outfit SemiBold", "Outfit",
                      "Segoe UI Semibold", "Segoe UI", "Arial"),
    "Outfit SemiBold": ("Outfit SemiBold", "Outfit Medium", "Outfit",
                        "Segoe UI Semibold", "Segoe UI", "Arial"),
    "JetBrains Mono": ("JetBrains Mono", "Cascadia Mono", "Consolas",
                       "Courier New"),
}
_WEIGHTS = {400: "Outfit", 500: "Outfit Medium", 600: "Outfit SemiBold"}
_resolved = {}


def font(family):
    """First installed face in the family's fallback chain.

    Requires a Tk root to exist, so it is called lazily rather than at import.
    """
    if family in _resolved:
        return _resolved[family]
    chain = _FALLBACKS.get(family, (family,))
    pick = chain[-1]
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families())
        for name in chain:
            if name in available:
                pick = name
                break
    except Exception:
        pass
    _resolved[family] = pick
    return pick


def weight_font(weight):
    """The installed family carrying the requested Outfit weight."""
    return font(_WEIGHTS.get(weight, "Outfit"))


# -- the mark --------------------------------------------------------------

CENTRE = 50.0
RADIUS = 34.0
STROKE = 14.0
BOX = 82.0            # visible extent: (RADIUS + STROKE/2) * 2

# The published artwork is two path elements, but the second ends exactly where
# the first begins (160deg), so the mark is a single unbroken stroke with one
# gap. Drawing it as two arcs leaves a seam at the join; drawing it as one also
# makes the stroke order obvious when it is animated.
STROKE_START, STROKE_EXTENT = 95.0, 295.0   # Tk angles: ccw from 3 o'clock
GAP_START, GAP_EXTENT = 30.0, 65.0          # the bite, centred on 1 o'clock

MAIN_START, MAIN_EXTENT = 160.0, 230.0      # the two published sub-paths,
LIT_START, LIT_EXTENT = 95.0, 65.0          # kept for reference


def draw_mark(canvas, x, y, box, colour, stroke_scale=1.0, progress=1.0,
              tags=()):
    """Draw the ring with its visible extent filling `box` pixels at (x, y).

    `progress` below 1 draws the mark part-way along its own stroke: the main
    arc grows counter-clockwise from 160deg toward the gap, and the lit segment
    lands last. Nothing is ever rotated - the gap stays at 1 o'clock, which is
    what separates a ring buffer from a loading spinner.
    """
    s = box / BOX
    cx, cy = x + box / 2, y + box / 2
    r = RADIUS * s
    width = max(1, round(STROKE * s * stroke_scale))
    bounds = (cx - r, cy - r, cx + r, cy + r)

    extent = STROKE_EXTENT * max(0.0, min(1.0, progress))
    if extent > 0.5:
        canvas.create_arc(*bounds, start=STROKE_START, extent=extent,
                          style="arc", outline=colour, width=width, tags=tags)


# -- the wordmark ----------------------------------------------------------

WORD_STROKE = 13.0
WORD_TOP, WORD_BASE = 12.0, 98.0          # ascender to baseline
WORD_HEIGHT = WORD_BASE - WORD_TOP        # 86u
WORD_LEFT, WORD_RIGHT = 8.0, 306.0

# n, a, b, apostrophe, d - the apostrophe is a clipped ascender stem, and the
# d sits 16u further right than it did before it was added.
_STEMS = ((8, 98, 8, 74), (56, 74, 56, 98), (134, 50, 134, 98),
          (164, 12, 164, 98), (232, 12, 232, 36), (306, 12, 306, 98))
_BOWLS = (110, 188, 282)                  # centres, y=74, r=24
_ARCH = (32, 74, 24)                      # n's shoulder: centre, radius


def draw_wordmark(canvas, x, y, height, colour, tags=()):
    """Draw 'nabd' with its ascender-to-baseline span equal to `height`.

    Never substitute type here: the wordmark is artwork, and a typed stand-in
    reads as a knock-off.
    """
    s = height / WORD_HEIGHT
    width = max(1, round(WORD_STROKE * s))

    def px(ux, uy):
        return x + (ux - WORD_LEFT) * s, y + (uy - WORD_TOP) * s

    for x1, y1, x2, y2 in _STEMS:
        a, b = px(x1, y1), px(x2, y2)
        canvas.create_line(*a, *b, fill=colour, width=width,
                           capstyle="round", tags=tags)
    for cx in _BOWLS:
        left, top = px(cx - 24, 74 - 24)
        right, bottom = px(cx + 24, 74 + 24)
        canvas.create_oval(left, top, right, bottom, outline=colour,
                           width=width, tags=tags)
    ax, ay, ar = _ARCH
    left, top = px(ax - ar, ay - ar)
    right, bottom = px(ax + ar, ay + ar)
    canvas.create_arc(left, top, right, bottom, start=0, extent=180,
                      style="arc", outline=colour, width=width, tags=tags)


def wordmark_width(height):
    s = height / WORD_HEIGHT
    return (WORD_RIGHT - WORD_LEFT + WORD_STROKE) * s


# -- the lockup ------------------------------------------------------------

# Proportions from nabd-lockup-cream.svg: the wordmark sits at translate(120,
# 10.8) scale(0.712) inside the mark's 100u coordinate system.
LOCK_WORD_X, LOCK_WORD_Y, LOCK_WORD_SCALE = 120.0, 10.8, 0.712
LOCK_LEFT, LOCK_TOP = 9.0, 9.0
LOCK_WIDTH = 334.0
LOCK_HEIGHT = 82.0


def draw_lockup(canvas, x, y, height, colour, tags=()):
    """Mark plus wordmark, at the spacing the guidelines specify."""
    s = height / LOCK_HEIGHT
    draw_mark(canvas, x + (CENTRE - RADIUS - STROKE / 2 - LOCK_LEFT) * s,
              y + (CENTRE - RADIUS - STROKE / 2 - LOCK_TOP) * s,
              BOX * s, colour, tags=tags)

    word_height = WORD_HEIGHT * LOCK_WORD_SCALE * s
    wx = x + (LOCK_WORD_X + LOCK_WORD_SCALE * WORD_LEFT - LOCK_LEFT) * s
    wy = y + (LOCK_WORD_Y + LOCK_WORD_SCALE * WORD_TOP - LOCK_TOP) * s
    draw_wordmark(canvas, wx, wy, word_height, colour, tags=tags)


def lockup_width(height):
    return LOCK_WIDTH * (height / LOCK_HEIGHT)


# Minimum sizes from the guidelines, in screen pixels at 1x.
MIN_LOCKUP_WIDTH = 120     # below this the gap in the ring closes up
MIN_TILE = 16              # holds at tray size
MIN_MARK = 20              # the unlidded ring needs more room than the tile

# Smallest lockup height that still clears the minimum width.
MIN_LOCKUP_HEIGHT = int(-(-MIN_LOCKUP_WIDTH * LOCK_HEIGHT // LOCK_WIDTH))



# -- tile lockup -----------------------------------------------------------

# The "tile on shell" treatment: the purple tile keeps the brand at full
# strength on a dark ground, where bare purple linework would fall under the
# contrast floor. Proportions taken from the supplied artwork - the wordmark is
# half the tile's height, set a third of a tile away, optically centred on it.
TILE_RADIUS = 0.225        # corner radius as a fraction of the tile
TILE_RING = 0.58           # ring diameter as a fraction of the tile
# Measured off the supplied lockup artwork: with a 143px tile the wordmark is
# 216px wide and sits 28px away, so its ascender height is 0.42 of the tile and
# the gap is 0.20 of it.
TILE_WORD_RATIO = 0.42
TILE_GAP_RATIO = 0.20


def draw_tile(canvas, x, y, size, field=PURPLE, ring=CREAM, tags=()):
    """Purple tile with the cream ring, drawn natively (no image needed)."""
    r = size * TILE_RADIUS
    pts = [x + r, y, x + size - r, y, x + size, y, x + size, y + r,
           x + size, y + size - r, x + size, y + size, x + size - r, y + size,
           x + r, y + size, x, y + size, x, y + size - r, x, y + r, x, y]
    canvas.create_polygon(pts, smooth=True, fill=field, outline=field,
                          tags=tags)
    inset = size * (1 - TILE_RING) / 2
    draw_mark(canvas, x + inset, y + inset, size * TILE_RING, ring, tags=tags)


def draw_tile_lockup(canvas, x, y, tile, field=PURPLE, ring=CREAM,
                     word=CREAM, tags=()):
    """Tile plus wordmark, as the supplied lockup artwork sets it."""
    draw_tile(canvas, x, y, tile, field, ring, tags)
    word_h = tile * TILE_WORD_RATIO
    wx = x + tile + tile * TILE_GAP_RATIO
    draw_wordmark(canvas, wx, y + (tile - word_h) / 2, word_h, word, tags)


def tile_lockup_width(tile):
    return tile * (1 + TILE_GAP_RATIO) + wordmark_width(
        tile * TILE_WORD_RATIO)


# The tile lockup's width is a fixed multiple of the tile, so the guidelines'
# 120px minimum converts straight into a smallest usable tile.
_TILE_LOCKUP_RATIO = (1 + TILE_GAP_RATIO) + TILE_WORD_RATIO * (
    (WORD_RIGHT - WORD_LEFT + WORD_STROKE) / WORD_HEIGHT)
MIN_TILE_LOCKUP = int(-(-MIN_LOCKUP_WIDTH // _TILE_LOCKUP_RATIO))


# -- raster output for icons ----------------------------------------------

def _pil_angles(tk_start, tk_extent):
    """Tk measures counter-clockwise from 3 o'clock; PIL measures clockwise."""
    return -(tk_start + tk_extent), -tk_start


def ring_image(size, colour, stroke_scale=1.0, progress=1.0, supersample=8):
    """The mark alone on transparency, antialiased.

    `progress` below 1 stops the stroke part-way, for the banner's draw-on.
    """
    from PIL import Image, ImageDraw
    big = size * supersample
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big / BOX
    cx = cy = big / 2
    r = RADIUS * s
    width = max(1, round(STROKE * s * stroke_scale))
    box = (cx - r, cy - r, cx + r, cy + r)
    extent = STROKE_EXTENT * max(0.0, min(1.0, progress))
    if extent > 0.5:
        a, b = _pil_angles(STROKE_START, extent)
        d.arc(box, start=a, end=b, fill=colour, width=width)
    return img.resize((size, size), Image.LANCZOS)


def _asset_root():
    """Where the rendered artwork lives.

    Frozen, PyInstaller unpacks data beside the binary rather than beside this
    source file.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


RENDER_DIR = _asset_root() / "brand" / "render"
_asset_cache = {}


def asset(name):
    """A rasterised brand asset, or None if it has not been rendered.

    These come from the supplied SVGs via render_assets.py, so the artwork is
    the artwork rather than geometry transcribed into code.
    """
    if name in _asset_cache:
        return _asset_cache[name]
    from PIL import Image
    path = RENDER_DIR / f"{name}.png"
    try:
        img = Image.open(path).convert("RGBA")
        img.load()
    except Exception:
        img = None
    _asset_cache[name] = img
    return img


def _scaled(img, height):
    from PIL import Image
    if img.height == height:
        return img
    width = max(1, round(img.width * height / img.height))
    return img.resize((width, max(1, height)), Image.LANCZOS)


def wordmark_image(height, colour=CREAM):
    """The wordmark, from the supplied artwork.

    `height` is the ascender-to-baseline span, matching the units the rest of
    this module speaks in; the rendered PNG carries half a stroke of padding on
    each side, so it is scaled by its full box.
    """
    name = "nabd-wordmark-ink" if colour == INK else "nabd-wordmark-cream"
    art = asset(name)
    if art is None:
        return _wordmark_fallback(height, colour)
    box = (WORD_HEIGHT + WORD_STROKE) / WORD_HEIGHT
    return _scaled(art, max(1, int(round(height * box))))


def _wordmark_fallback(height, colour, supersample=8):
    """Drawn from geometry, used only when the PNGs are missing."""
    from PIL import Image, ImageDraw
    span_x = WORD_RIGHT - WORD_LEFT + WORD_STROKE
    span_y = WORD_HEIGHT + WORD_STROKE
    out_h = max(1, int(round(height * span_y / WORD_HEIGHT)))
    out_w = max(1, int(round(out_h * span_x / span_y)))

    w, h = out_w * supersample, out_h * supersample
    s = h / span_y
    pad = WORD_STROKE / 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(1, round(WORD_STROKE * s))
    cap = stroke / 2

    def px(ux, uy):
        return ((ux - WORD_LEFT + pad) * s, (uy - WORD_TOP + pad) * s)

    for x1, y1, x2, y2 in _STEMS:
        a, b = px(x1, y1), px(x2, y2)
        d.line([a, b], fill=colour, width=stroke)
        # PIL has no round caps; a disc at each end supplies them.
        for point in (a, b):
            d.ellipse([point[0] - cap, point[1] - cap,
                       point[0] + cap, point[1] + cap], fill=colour)
    for cx in _BOWLS:
        x0, y0 = px(cx - 24, 74 - 24)
        x1, y1 = px(cx + 24, 74 + 24)
        d.ellipse([x0, y0, x1, y1], outline=colour, width=stroke)
    ax, ay, ar = _ARCH
    x0, y0 = px(ax - ar, ay - ar)
    x1, y1 = px(ax + ar, ay + ar)
    d.arc([x0, y0, x1, y1], start=180, end=360, fill=colour, width=stroke)

    return img.resize((out_w, out_h), Image.LANCZOS)


def tile_lockup_image(tile, field=PURPLE, ring=CREAM, word=CREAM):
    """Tile plus wordmark as one antialiased image, for the panel header.

    Refuses to go under the lockup's minimum width: below it the strokes stop
    holding together, which is exactly what the 120px rule is protecting.
    """
    from PIL import Image
    tile = int(tile)
    glyph = wordmark_image(tile * TILE_WORD_RATIO, word)
    gap = int(round(tile * TILE_GAP_RATIO))
    width = tile + gap + glyph.width
    img = Image.new("RGBA", (width, max(tile, glyph.height)), (0, 0, 0, 0))
    img.alpha_composite(tile_image(tile, field, ring), (0, 0))
    img.alpha_composite(glyph, (tile + gap, (img.height - glyph.height) // 2))
    return img


def tile_image(size, field=PURPLE, ring=CREAM, supersample=8):
    """The app tile: purple field, 22.5% corner radius, ring at 58%.

    Uses the supplied artwork at brand colours; only a recoloured tile (the
    paused tray icon) is drawn, since the PNG cannot be retinted.
    """
    from PIL import Image, ImageDraw
    big = size * supersample
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * TILE_RADIUS,
                        fill=field)

    # The tile is composed here rather than taken from nabd-app-tile-512.svg:
    # that file nests an inner <svg> with its own viewBox, which the rasteriser
    # mis-places - the ring came out off-centre with a 7% stroke instead of 8%.
    # The ring's visible box is BOX of the inner 100u frame, and that frame is
    # TILE_RING of the tile.
    extent = int(round(big * TILE_RING * BOX / 100.0))
    art = asset("nabd-mark-ink" if ring == INK else "nabd-mark-cream")
    if art is not None and ring in (CREAM, INK):
        glyph = art.resize((extent, extent), Image.LANCZOS)
    else:   # a recoloured tile (the paused tray icon) has to be drawn
        glyph = ring_image(extent, ring, supersample=2)
    pos = (big - extent) // 2
    img.alpha_composite(glyph, (pos, pos))
    return img.resize((size, size), Image.LANCZOS)
