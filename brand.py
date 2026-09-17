"""
Nab'd brand system: palette, type scale, and the logo as supplied artwork.

Everything here now resolves to the files in brand/, rasterised into
brand/render/*.png by render_assets.py. Nothing in this module redraws the
mark or the wordmark from measurements.

That is a change, and it is the point of it. The mark used to be transcribed
into arc geometry so it could be drawn on a Tk canvas at any size; the brand
overhaul replaced it with a horned head whose horns and eyes are bezier paths,
and a transcription of that would be a second, drifting copy of the artwork -
exactly what OVERHAUL.md section 8 warns about. The numbers below are read from
the artwork's own boxes (see nabd_mark.py, which holds the paths) and are used
only to place and scale it, never to draw it.

  Mark        artwork box 268u inside the tile's 384u frame
  Tile        22.5% corner radius; the mark sits centred, 3u above centre
  Wordmark    box 466.6 x 152.5u, ascender-to-baseline 129u, stroke 19.5u

THE HORN RULE (OVERHAUL.md section 2). The horns appear exactly once, on
whichever element is alone. Every lockup this module composes puts the mark
next to the type, so every one of them asks for the PLAIN wordmark - which is
why wordmark_image() defaults to plain and horned is opt-in.
"""

import sys
from pathlib import Path

# The paths and the artwork's own measurements. stdlib-only, so this adds no
# runtime dependency - which is the constraint the whole brand system is built
# under.
import nabd_mark as _art

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


# -- the artwork's measurements --------------------------------------------

# The tile's frame and the mark's box within it, straight off nabd_mark.
TILE_UNITS = _art.FULL[2]                       # 384
_MARK_X, _MARK_Y, MARK_UNITS = _art.TIGHT[0], _art.TIGHT[1], _art.TIGHT[2]

TILE_RADIUS = 86.4 / TILE_UNITS                 # 0.225, off the tile path
MARK_RATIO = MARK_UNITS / TILE_UNITS            # 0.698 of the tile
# The mark is centred horizontally but sits 3u above centre - the horns need
# the headroom. Placing it dead centre drops the head and reads as a slump.
MARK_OFFSET = (_MARK_X / TILE_UNITS, _MARK_Y / TILE_UNITS)

# Wordmark, from nabd_mark.WORD_BOX ('-2 -2 466.6 152.5').
_WB = [float(v) for v in _art.WORD_BOX.split()]
WORD_BOX_W, WORD_BOX_H = _WB[2], _WB[3]
WORD_STROKE = _art.WORD_SW                      # 19.5
# Ascender to baseline: the stems run y 9.75 -> 138.75 (OVERHAUL.md section 1).
WORD_HEIGHT = 129.0
# The rendered PNG carries the stroke's padding, so a request for an ascender
# height scales by the full box.
_WORD_BOX_RATIO = WORD_BOX_H / WORD_HEIGHT

# The primary lockup, from nabd-lockup-cream.svg's viewBox, and the stacked
# one, from nabd-stacked-cream.svg's. Both pair the mark with the PLAIN
# wordmark, as supplied.
LOCK_WIDTH, LOCK_HEIGHT = 258.4, 116.0
STACK_WIDTH, STACK_HEIGHT = 138.8, 171.0

# Minimum sizes from the guidelines, in screen pixels at 1x.
MIN_LOCKUP_WIDTH = 120     # below this the bite in the ring closes up
MIN_TILE = 16              # holds at tray size
MIN_MARK = 20              # the unlidded mark needs more room than the tile

# Smallest lockup height that still clears the minimum width.
MIN_LOCKUP_HEIGHT = int(-(-MIN_LOCKUP_WIDTH * LOCK_HEIGHT // LOCK_WIDTH))


# -- tile lockup -----------------------------------------------------------

# The "tile on shell" treatment: the purple tile keeps the brand at full
# strength on a dark ground, where bare purple linework would fall under the
# contrast floor. The wordmark is a little under half the tile's height, set a
# fifth of a tile away, optically centred on it.
#
# These two ratios survive the overhaul unchanged, and deliberately: the new
# wordmark's width-to-ascender is 3.617 against the old 3.616, so the header
# these drive lands within a pixel of where it always did.
TILE_WORD_RATIO = 0.42
TILE_GAP_RATIO = 0.20

_TILE_LOCKUP_RATIO = (1 + TILE_GAP_RATIO) + TILE_WORD_RATIO * (
    WORD_BOX_W / WORD_HEIGHT)
MIN_TILE_LOCKUP = int(-(-MIN_LOCKUP_WIDTH // _TILE_LOCKUP_RATIO))


def wordmark_width(height):
    """Width of the wordmark whose ascender-to-baseline span is `height`."""
    return WORD_BOX_W * (height / WORD_HEIGHT)


def lockup_width(height):
    return LOCK_WIDTH * (height / LOCK_HEIGHT)


def tile_lockup_width(tile):
    return tile * (1 + TILE_GAP_RATIO) + wordmark_width(
        tile * TILE_WORD_RATIO)


# -- loading the rendered artwork ------------------------------------------

def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


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
_warned = set()


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


def _require(name):
    """The artwork, or a blank of the right shape plus one warning.

    There is deliberately no geometry fallback any more. The old one drew the
    retired mark - a ring with the bite at 1 o'clock, no horns, no eyes - which
    meant a missing render silently shipped last year's logo. A hole is
    obvious; a plausible wrong mark is not.

    In practice this never fires in a shipped build: nabd.spec bundles
    brand/render/*.png and build.py refuses to freeze without them. It fires
    when someone runs from source before render_assets.py.
    """
    img = asset(name)
    if img is None and name not in _warned:
        _warned.add(name)
        # Frozen with console=False there is no stderr to write to, and an
        # AttributeError here would take down the tray icon over a missing
        # PNG. The warning is for someone running from source; the shipped
        # build cannot reach it.
        try:
            sys.stderr.write(
                f"brand: {name}.png is missing - run render_assets.py\n")
        except Exception:
            pass
    return img


def _scaled(img, height):
    from PIL import Image
    if img.height == height:
        return img
    width = max(1, round(img.width * height / img.height))
    return img.resize((width, max(1, height)), Image.LANCZOS)


def _tinted(img, colour):
    """Recolour flat artwork, keeping its antialiasing.

    The mark and the wordmark are each a single flat colour over an alpha
    channel, so replacing the colour and keeping the alpha is exact - not an
    approximation of a retint.
    """
    from PIL import Image
    out = Image.new("RGBA", img.size, _rgb(colour) + (255,))
    out.putalpha(img.getchannel("A"))
    return out


# -- the mark --------------------------------------------------------------

def mark_image(size, colour=CREAM):
    """The mark alone on transparency, from the supplied artwork.

    Square: the artwork's box is 268u on both axes, and the pose the banner
    plays is baked separately by nabd_mark_frames.
    """
    from PIL import Image
    size = max(1, int(size))
    name = "nabd-mark-ink" if colour == INK else "nabd-mark-cream"
    art = _require(name)
    if art is None:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    art = art.resize((size, size), Image.LANCZOS)
    if colour not in (CREAM, INK):
        art = _tinted(art, colour)
    return art


# The mark is no longer a ring, but make_wizard_art and _test/render_brand.py
# reach for it by the old name.
ring_image = mark_image


# -- the wordmark ----------------------------------------------------------

def wordmark_image(height, colour=CREAM, horned=False):
    """The wordmark, from the supplied artwork.

    `height` is the ascender-to-baseline span, matching the units the rest of
    this module speaks in; the rendered PNG carries the stroke's padding, so it
    is scaled by its full box.

    `horned` follows the horn rule: leave it False whenever the mark is also on
    screen, which is every lockup this module composes. Set it only for the
    wordmark standing alone - a README title, an installer header.
    """
    from PIL import Image
    variant = "horned" if horned else "plain"
    tone = "ink" if colour == INK else "cream"
    art = _require(f"nabd-wordmark-{variant}-{tone}")
    want = max(1, int(round(height * _WORD_BOX_RATIO)))
    if art is None:
        return Image.new("RGBA", (max(1, int(want * WORD_BOX_W / WORD_BOX_H)),
                                  want), (0, 0, 0, 0))
    art = _scaled(art, want)
    if colour not in (CREAM, INK):
        art = _tinted(art, colour)
    return art


# -- the tile --------------------------------------------------------------

def tile_image(size, field=PURPLE, ring=CREAM, supersample=8):
    """The app tile: purple field, 22.5% corner radius, the mark on top.

    At brand colours this IS nabd-app-tile-512.svg, resized - the supplied
    artwork, not a reconstruction. The overhaul's tile is a flat SVG, so the
    nested-viewBox mis-placement that used to force this to compose the tile by
    hand no longer applies.

    A recoloured tile - the paused tray icon - still has to be composed, since
    a PNG cannot be retinted field and mark independently.
    """
    from PIL import Image, ImageDraw
    size = max(1, int(size))
    if field == PURPLE and ring == CREAM:
        art = _require("nabd-app-tile-512")
        if art is not None:
            return art.resize((size, size), Image.LANCZOS)

    big = size * supersample
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=big * TILE_RADIUS, fill=field)
    extent = int(round(big * MARK_RATIO))
    glyph = mark_image(extent, ring)
    img.alpha_composite(glyph, (int(round(big * MARK_OFFSET[0])),
                                int(round(big * MARK_OFFSET[1]))))
    return img.resize((size, size), Image.LANCZOS)


# -- lockups ---------------------------------------------------------------

def lockup_image(height, colour=CREAM):
    """The primary lockup - mark beside the plain wordmark - as supplied.

    `height` is the artwork's full box, not the wordmark's ascender.
    """
    from PIL import Image
    name = "nabd-lockup-ink" if colour == INK else "nabd-lockup-cream"
    art = _require(name)
    height = max(1, int(height))
    if art is None:
        return Image.new("RGBA",
                         (max(1, int(height * LOCK_WIDTH / LOCK_HEIGHT)),
                          height), (0, 0, 0, 0))
    art = _scaled(art, height)
    if colour not in (CREAM, INK):
        art = _tinted(art, colour)
    return art


def stacked_image(height, colour=CREAM):
    """The stacked lockup - mark over the plain wordmark - as supplied.

    Used below the primary lockup's 120px minimum width, and for the installer
    wizard panel, which is a tall column.
    """
    from PIL import Image
    name = "nabd-stacked-ink" if colour == INK else "nabd-stacked-cream"
    art = _require(name)
    height = max(1, int(height))
    if art is None:
        return Image.new("RGBA",
                         (max(1, int(height * STACK_WIDTH / STACK_HEIGHT)),
                          height), (0, 0, 0, 0))
    art = _scaled(art, height)
    if colour not in (CREAM, INK):
        art = _tinted(art, colour)
    return art


def tile_lockup_image(tile, field=PURPLE, ring=CREAM, word=CREAM):
    """Tile plus wordmark as one antialiased image, for the panel header.

    The wordmark is the plain one: the mark is present, inside the tile.
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
