"""Composite the save banner at chosen instants, straight to a PNG.

    python _test/banner_preview.py

No window is ever created, so this can run while a game is in the foreground.
It reads the same frame assets and the same layout constants the live banner
uses, and samples nabd_banner for the values, so what it shows is what the
banner draws - short of Tk's own text rasterisation.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from PIL import Image, ImageDraw, ImageFont     # noqa: E402

import banner as B                              # noqa: E402
import nabd_banner as M                         # noqa: E402
from nabd_mark_frames import index_for          # noqa: E402

FONTS = HERE.parent / "vendor" / "fonts"
TITLE_F = ImageFont.truetype(str(FONTS / "Outfit-Medium.ttf"), 15)
DETAIL_F = ImageFont.truetype(str(FONTS / "JetBrainsMono-Regular.ttf"), 12)


def compose(t, title, detail, kind="ok", backdrop=(24, 24, 28)):
    """One frame, on a backdrop so the chroma-keyed corners are visible.

    Takes the time, not a sampled frame: the mark is a flipbook indexed by t
    now, so sampling here keeps the card and the mark on the same instant.
    """
    f = M.sample(t)
    field = B.FIELD[kind]
    d = B.asset_dir(1.0, kind)
    w, h = max(1, f.w), max(1, f.h)

    plate = Image.new("RGB", (M.CARD_W + 40, M.CARD_H + 40), backdrop)
    even = max(4, min(76, int(round(h / 2.0)) * 2))
    card = Image.open(d / f"card_h{even:02d}.png").convert("RGBA")
    if card.width != w:
        card = card.resize((w, card.height), Image.BILINEAR)

    # bottom-right anchored, exactly as the live geometry is
    ox = plate.width - 20 - w
    oy = plate.height - 20 - h
    plate.paste(card, (ox, oy), card)

    # the asset is at the nearest even height, which can differ from f.h by a
    # pixel; draw on the asset's own size so the mask matches
    w, h = card.size
    layer = Image.new("RGB", (w, h), B._rgb(field))
    draw = ImageDraw.Draw(layer)
    if f.copy > 0.001:
        rise = int(round(B.COPY_RISE * (1.0 - f.copy)))
        if f.ring > 0.0 or f.horns > 0.0 or f.eyes > 0.0:
            mark = Image.open(
                d / f"mark_{index_for(t):04d}.png").convert("RGB")
            if f.copy < 1.0:
                mark = Image.blend(Image.new("RGB", mark.size, B._rgb(field)),
                                   mark, f.copy)
            layer.paste(mark, (int(B.PAD_X),
                               int(B.MARK_CY - B.MARK / 2) + rise))
        tx = int(B.TEXT_X)
        draw.text((tx, B.TITLE_CY + rise), title, anchor="lm",
                  fill=B.mix(field, B.CREAM, f.copy), font=TITLE_F)
        draw.text((tx, B.DETAIL_CY + rise), detail, anchor="lm",
                  fill=B.mix(field, B.DETAIL_FG, f.copy), font=DETAIL_F)

    # the rule is masked to the card's own bottom edge, so it follows the
    # 12px radius instead of overrunning it
    shown = 1.0 - f.line
    rule = B.mix(field, B.mix(field, B.RULE, B.RULE_ALPHA), shown)
    rw = int(w * f.drain)
    if rw > 0 and h >= M.CARD_H - 1:
        full = Image.open(d / "card_h76.png").convert("RGBA")
        strip = full.crop((0, full.height - B.RULE_H, full.width, full.height))
        bar = Image.new("RGB", strip.size, B._rgb(rule))
        mask = strip.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        layer.paste(bar.crop((0, 0, min(rw, bar.width), bar.height)),
                    (0, h - B.RULE_H),
                    mask.crop((0, 0, min(rw, bar.width), bar.height)))

    # keep the card's rounded silhouette when pasting the drawn layer back
    mask = card.getchannel("A") if card.mode == "RGBA" else None
    plate.paste(layer, (ox, oy), mask)
    return plate


def strip(times, title, detail, kind, name):
    frames = [compose(t, title, detail, kind) for t in times]
    cw, ch = frames[0].size
    sheet = Image.new("RGB", (cw, ch * len(frames)), (10, 10, 12))
    for i, fr in enumerate(frames):
        sheet.paste(fr, (0, i * ch))
    sheet.save(HERE / name)
    return sheet.size


if __name__ == "__main__":
    print("entry  ", strip([60, 200, 300, 400, 520, 700, 900],
                           "Nabbed", "5:00 · 1.2 GB", "ok",
                           "banner_entry.png"))
    # 1200 resting, then the gesture: anticipation, the turn-tilt-squash-wink
    # as one action, the hold, the eye reopening, and the unwind past level.
    print("rest   ", strip([1200, 1600, 1800, 1950, 2150, 2400, 3100],
                           "Nabbed", "5:00 · 1.2 GB", "ok",
                           "banner_rest.png"))
    print("exit   ", strip([3300, 3500, 3620, 3700, 3800, 3870, 4000, 4100],
                           "Nabbed", "5:00 · 1.2 GB", "ok",
                           "banner_exit.png"))
    print("fail   ", strip([1200], "Capture Lost", "Use Borderless Windowed",
                           "fail", "banner_fail.png"))
