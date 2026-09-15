"""nab'd design tokens for tkinter.

Every colour and metric in the settings panel comes from here. Metrics are given
in CSS pixels at 96 dpi; call scaled() / px() to get device pixels.

Tk gotcha: a POSITIVE font size is points, a NEGATIVE size is pixels. All the
sizes below are pixels, so they are stored positive and negated in font().
"""
from __future__ import annotations

# -- colour ----------------------------------------------------------------
SHELL          = "#0A0A0C"
PANEL          = "#121215"
SURFACE        = "#17171B"
RAISED         = "#1C1C21"
RAISED_HOVER   = "#22222A"

LINE           = "#26262B"
LINE_STRONG    = "#33333A"
LINE_HOVER     = "#3E3E47"

TEXT           = "#E8E4DC"
TEXT_MUTED     = "#9A958C"
TEXT_FAINT     = "#6B6760"
TEXT_ON_PURPLE = "#F3EFE9"

# PURPLE is a FILL ONLY -- 2.7:1 on SHELL. Anything that must be *seen*
# (text, icons, meter fills, focus rings, the status dot) uses PURPLE_LIGHT.
PURPLE         = "#6C3BAA"
PURPLE_HOVER   = "#7B45BF"
PURPLE_LIGHT   = "#9B6BD8"
PURPLE_DEEP    = "#4E2A7D"

WARN           = "#C8922E"
DANGER         = "#B4483E"

# -- type ------------------------------------------------------------------
FONT_UI   = "Outfit"
FONT_MONO = "JetBrains Mono"

#            family      px   weight
TYPE = {
    "title":    (FONT_UI,   16, "normal"),   # 500 -- see WEIGHT note below
    "heading":  (FONT_UI,   15, "normal"),
    "label":    (FONT_UI,   14, "normal"),   # 13.5 rounds to 14
    "value":    (FONT_UI,   13, "normal"),
    "helper":   (FONT_UI,   12, "normal"),
    "eyebrow":  (FONT_MONO, 10, "normal"),
    "mono":     (FONT_MONO, 12, "normal"),
    "mono_sm":  (FONT_MONO, 11, "normal"),
    "mono_xs":  (FONT_MONO, 10, "normal"),
}
# Tk exposes only normal/bold. Outfit 500 is not reachable through the weight
# flag, so register the Medium face under its own family name ("Outfit Medium")
# and use that where the spec asks for 500.
FONT_UI_MEDIUM = "Outfit Medium"

# -- metrics (CSS px @ 96dpi) ----------------------------------------------
PANEL_W        = 640
CONTROL_COL    = 344
CONTROL_H      = 36
CONTROL_H_SM   = 30
KBD_H          = 34
ROW_PAD_X      = 15
ROW_PAD_Y      = 13
PANEL_PAD      = 16
GROUP_GAP      = 18
LABEL_TOP_PAD  = 9          # centres a 14px label against a 36px control

R_PANEL        = 12
R_CARD         = 10
R_CONTROL      = 7
R_SEG_CELL     = 6
R_TOGGLE       = 12

METER_H        = 6
TRACK_H        = 4
KNOB_D         = 14
TOGGLE_W       = 40
TOGGLE_H       = 23
TOGGLE_KNOB    = 17
# The header lockup. Sized here rather than inline: the header's own height
# follows it, and the still is cut from whatever that comes out as.
LOGO_TILE      = 30
THUMB_GAP      = 10
THUMB_POSTER_H = 74
# Tile width is derived from the panel so the strip lands on the same edges as
# every card (see Panel._tile_metrics). The source frame is pulled wider than
# any tile so cropping it to fill never has to upscale.
THUMB_SRC_W    = 420
FOOTER_H       = 60
FOCUS_W        = 2

# -- dpi -------------------------------------------------------------------
_scale = 1.0


def set_scale(dpi: int) -> float:
    """Call once, after DPI awareness is set and before any layout."""
    global _scale
    _scale = dpi / 96.0
    return _scale


def scale() -> float:
    return _scale


def px(v: float) -> int:
    """CSS px -> device px."""
    return int(round(v * _scale))


def font(role: str, family: str | None = None):
    """-> (family, -pixels) tuple ready for a Tk `font=` option."""
    fam, size, _ = TYPE[role]
    return (family or fam, -px(size))
