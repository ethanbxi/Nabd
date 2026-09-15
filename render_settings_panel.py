"""Draw the nab'd settings panel, and its open, from the app's own modules.

`nabd_paint` is plain Pillow and `nabd_tokens` holds every colour and metric,
so this is the real widget set at the real geometry - not a redraw of it.
`nabd_panel_open` supplies the motion.

    python render_settings_panel.py docs/media --fonts vendor/fonts
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from PIL import Image, ImageChops, ImageDraw, ImageFont

import nabd_tokens as T
import nabd_paint as P
import nabd_panel_open as M
import brand

from render_readme_media import Fonts, rgb, mix

HEAD_BG = "#0E0E11"
PANEL_H = 2600                     # scratch height; trimmed to the content

# What the still says. Plausible, and internally consistent with the figures
# the README quotes for 1440p60 on High.
CFG = dict(
    status="Buffering", window="last 5 minutes", per_nab="1.2 GB",
    free="412 GB free", hotkey="Alt + Insert", open_hotkey="Ctrl + Alt + N",
    length_index=2, reset=False, sound="Pip", folder=r"C:\Users\you\Videos\Nabd",
    monitor="1 · DELL U2723QE  2560×1440", quality="High  ·  CQ 23",
    fps="60 fps", speakers="Speakers (Realtek USB Audio)",
    mic="Microphone (HyperX QuadCast)", spk_vol=100, mic_vol=78, sync=-150,
    nabs=[("23:07:14", "2026-09-15", "1.2 GB"),
          ("22:41:02", "2026-09-15", "1.2 GB"),
          ("21:58:37", "2026-09-15", "704 MB")],
    recent_count="12 · 14.8 GB",
)


class Canvas:
    """A Pillow surface with the panel's own px() and text helpers."""

    def __init__(self, w, h, bg):
        self.img = Image.new("RGB", (w, h), rgb(bg))
        self.d = ImageDraw.Draw(self.img)
        self.fonts = None

    def f(self, role, medium=False):
        fam, size, _ = T.TYPE[role]
        which = "mono" if fam == T.FONT_MONO else ("med" if medium else "ui")
        return self.fonts.load(which, T.px(size))

    def text(self, xy, s, font, fill, anchor="lm"):
        self.d.text(xy, s, font=font, fill=rgb(fill), anchor=anchor)

    def w(self, s, font):
        return self.d.textlength(s, font=font)

    def paste(self, im, x, y):
        if im.mode == "RGBA":
            self.img.paste(im, (int(x), int(y)), im)
        else:
            self.img.paste(im, (int(x), int(y)))

    def rect(self, x0, y0, x1, y1, fill):
        self.d.rectangle([int(x0), int(y0), int(x1), int(y1)], fill=rgb(fill))


# --------------------------------------------------------------- controls ---
def box(w, h, fill=T.RAISED, outline=T.LINE_STRONG, bg=T.SURFACE, r=None):
    return P.rounded_rect(int(w), int(h), T.px(T.R_CONTROL if r is None else r),
                          fill, outline, T.px(1), bg)


def select(c, x_right, y, w, label):
    """36px select: raised fill, strong line, value left, chevron right."""
    h = T.px(T.CONTROL_H)
    c.paste(box(w, h), x_right - w, y)
    c.text((x_right - w + T.px(13), y + h / 2), label, c.f("value"), T.TEXT)
    chev = P.chevron(T.px(16), T.TEXT_FAINT, T.RAISED)
    c.paste(chev, x_right - T.px(11) - chev.width, y + (h - chev.height) / 2)
    return h


def button(c, x_right, y, text, variant="ghost", small=False, bg=T.SURFACE):
    fill, line, fg, _, _ = {
        "primary": (T.PURPLE, T.PURPLE, T.TEXT_ON_PURPLE, None, None),
        "ghost": (T.RAISED, T.LINE_STRONG, T.TEXT, None, None),
        "quiet": (None, T.LINE_STRONG, T.TEXT_MUTED, None, None),
    }[variant]
    h = T.px(T.CONTROL_H_SM if small else T.CONTROL_H)
    pad = T.px(12 if small else 14)
    f = c.f("value")
    w = int(c.w(text, f) + pad * 2)
    c.paste(P.rounded_rect(w, h, T.px(T.R_CONTROL), fill or bg, line, T.px(1), bg),
            x_right - w, y)
    c.text((x_right - w / 2, y + h / 2), text, f, fg, anchor="mm")
    return w, h


def segmented(c, x_right, y, options, index, bg=T.SURFACE):
    h = T.px(T.CONTROL_H_SM + 6 + 2)
    pad = T.px(3)
    cell_h = T.px(T.CONTROL_H_SM)
    f = c.f("value")
    widths = [int(c.w(o, f) + T.px(32)) for o in options]
    w = sum(widths) + T.px(3) * (len(options) - 1) + pad * 2
    c.paste(P.rounded_rect(w, h, T.px(8), T.RAISED, T.LINE_STRONG, T.px(1), bg),
            x_right - w, y)
    x = x_right - w + pad
    for i, (opt, ow) in enumerate(zip(options, widths)):
        on = i == index
        if on:
            c.paste(P.rounded_rect(ow, cell_h, T.px(T.R_SEG_CELL), T.PURPLE,
                                   None, 1, T.RAISED), x, y + (h - cell_h) / 2)
        c.text((x + ow / 2, y + h / 2), opt, f,
               T.TEXT_ON_PURPLE if on else T.TEXT_MUTED, anchor="mm")
        x += ow + T.px(3)
    return w, h


def slider(c, x_left, x_right, y, frac, bg=T.SURFACE):
    h = T.px(20)
    k = T.px(T.KNOB_D)
    th = T.px(T.TRACK_H)
    cy = y + h // 2
    x0, x1 = x_left + k // 2, x_right - k // 2
    c.rect(x0, cy - th // 2, x1, cy + th // 2, T.LINE_STRONG)
    fx = x0 + (x1 - x0) * frac
    if fx > x0:
        c.rect(x0, cy - th // 2, fx, cy + th // 2, T.PURPLE_LIGHT)
    knob = P.knob(k, T.TEXT_ON_PURPLE, bg)
    c.paste(knob, fx - k / 2, cy - k / 2)
    return h


def hotkey_field(c, x_right, y, text, min_w, bg=T.SURFACE):
    h = T.px(T.KBD_H)
    f = c.f("mono")
    w = max(T.px(min_w), int(c.w(text, f) + 2 * T.px(13)))
    c.paste(box(w, h, bg=bg), x_right - w, y)
    c.text((x_right - w / 2, y + h / 2), text, f, T.TEXT, anchor="mm")
    # the lip: a 1px lighter edge along the bottom, inside the radius
    c.rect(x_right - w + T.px(7), y + h - T.px(1),
           x_right - T.px(7), y + h - T.px(1), "#3C3C44")
    return w, h


# ------------------------------------------------------------------ panel ---
class Panel:
    def __init__(self, fonts, w=T.PANEL_W, h=PANEL_H):
        self.W, self.H = T.px(w), T.px(h)
        self.c = Canvas(self.W, self.H, T.PANEL)
        self.c.fonts = fonts
        self.pad = T.px(T.PANEL_PAD)
        self.content_w = self.W - 2 * self.pad
        self.right = self.W - self.pad          # control column right edge
        self.col = T.px(T.CONTROL_COL)
        self.blocks = {}                        # name -> (y0, y1)

    # -- chrome ------------------------------------------------------------
    def header(self):
        c = self.c
        tile = T.px(T.LOGO_TILE)
        h = T.px(14) + tile + T.px(13)
        c.rect(0, 0, self.W, h - 1, HEAD_BG)
        lock = brand.tile_lockup_image(tile, field=T.PURPLE, ring=T.TEXT,
                                       word=T.TEXT)
        c.paste(lock, T.px(16), T.px(14))
        c.text((T.px(16) + lock.width + T.px(10), T.px(14) + tile / 2),
               "Settings", c.f("value"), T.TEXT_FAINT)
        # Drawn, not typed: Outfit has no U+2715.
        cx, cy2, a = self.W - T.px(16) - T.px(6), T.px(14) + tile / 2, T.px(5)
        lw = max(1, T.px(1.2))
        c.d.line([cx - a, cy2 - a, cx + a, cy2 + a], fill=rgb(T.TEXT_FAINT), width=lw)
        c.d.line([cx - a, cy2 + a, cx + a, cy2 - a], fill=rgb(T.TEXT_FAINT), width=lw)
        c.rect(0, h, self.W, h, T.LINE)
        return h + 1

    def footer(self):
        c = self.c
        fh = T.px(T.FOOTER_H)
        y = self.H - fh
        c.rect(0, y - 1, self.W, y - 1, T.LINE)
        c.rect(0, y, self.W, self.H, HEAD_BG)
        c.text((T.px(16), y + fh / 2), "No changes", c.f("mono_sm"),
               T.TEXT_FAINT)
        # Save is disabled until something changes: the spec's 40% blend.
        f = c.f("value")
        bw, bh = T.px(78), T.px(T.CONTROL_H)
        img = P.rounded_rect(bw, bh, T.px(T.R_CONTROL), T.PURPLE, T.PURPLE,
                             T.px(1), HEAD_BG)
        img = Image.blend(Image.new("RGB", img.size, rgb(HEAD_BG)), img, 0.4)
        c.paste(img, self.W - T.px(16) - bw, y + (fh - bh) / 2)
        c.text((self.W - T.px(16) - bw / 2, y + fh / 2), "Save", f,
               T.TEXT_FAINT, anchor="mm")
        cw = int(c.w("Close", f) + T.px(28))
        cx = self.W - T.px(16) - bw - T.px(9)
        c.paste(P.rounded_rect(cw, bh, T.px(T.R_CONTROL), HEAD_BG,
                               T.LINE_STRONG, T.px(1), HEAD_BG), cx - cw,
                y + (fh - bh) / 2)
        c.text((cx - cw / 2, y + fh / 2), "Close", f, T.TEXT_MUTED, anchor="mm")
        return y - 1

    def scrollbar(self, top, bottom, frac=0.82):
        c = self.c
        w = T.px(6)
        x = self.W - T.px(5) - w
        h = int((bottom - top) * frac)
        c.paste(P.scroll_thumb(w, h, T.LINE_HOVER, T.PANEL), x, top + T.px(6))

    # -- pieces ------------------------------------------------------------
    def eyebrow(self, y, text, trailing=None, arrows=False):
        """Mono uppercase, letter-spaced by hand, with a hairline to the right."""
        c = self.c
        f = c.f("eyebrow")
        x = self.pad + T.px(3)
        gap = max(1, T.px(1.6) - T.px(1))
        cy = y + T.px(7)
        for ch in text.upper():
            c.text((x, cy), ch, f, T.TEXT_FAINT, anchor="lm")
            x += c.w(ch, f) + gap
        x_end = self.W - self.pad
        if trailing:
            ft = c.f("mono_xs")
            tw = c.w(trailing, ft)
            extra = T.px(15) * 2 + T.px(3) * 4 + T.px(10) if arrows else 0
            c.text((x_end - extra, cy), trailing, ft, T.TEXT_FAINT, anchor="rm")
            if arrows:
                fa = c.fonts.load("ui", T.px(15))
                c.text((x_end - T.px(18), cy), "\u2039", fa, T.TEXT_FAINT, anchor="mm")
                c.text((x_end - T.px(3), cy), "\u203a", fa, T.TEXT_FAINT, anchor="mm")
            x_end -= extra + tw + T.px(12)
        c.rect(x + T.px(12), cy, x_end - T.px(12) if not trailing else x_end,
               cy, T.LINE)
        return T.px(15)

    def card(self, y, h):
        self.c.paste(P.rounded_rect(self.content_w, int(h), T.px(T.R_CARD),
                                    T.SURFACE, T.LINE, T.px(1), T.PANEL),
                     self.pad, y)

    def label(self, y, text):
        self.c.text((self.pad + T.px(T.ROW_PAD_X),
                     y + T.px(T.ROW_PAD_Y + T.LABEL_TOP_PAD) + T.px(7)),
                    text, self.c.f("label"), T.TEXT)

    def sep(self, y):
        self.c.rect(self.pad + 1, y, self.pad + self.content_w - 2, y, T.LINE)

    def helper(self, y, text, colour=T.TEXT_FAINT):
        self.c.text((self.right - self.col, y), text, self.c.f("helper"),
                    colour, anchor="lt")
        return T.px(14)

    # -- blocks ------------------------------------------------------------
    def hero(self, y):
        c = self.c
        w, h = self.content_w, T.px(170)
        c.paste(P.hero_bg(w, h, T.PANEL), self.pad, y)
        x0 = self.pad
        pad = T.px(17)
        cy = y + T.px(26)
        c.d.ellipse([x0 + pad, cy - T.px(4), x0 + pad + T.px(7), cy + T.px(3)],
                    fill=rgb(T.PURPLE_LIGHT))
        fm = c.f("label", medium=True)
        c.text((x0 + pad + T.px(16), cy), CFG["status"], fm, T.TEXT)
        c.text((x0 + pad + T.px(16) + c.w(CFG["status"], fm) + T.px(9), cy),
               CFG["window"], c.f("mono_sm"), T.TEXT_MUTED)
        c.text((x0 + w - pad, cy), f"{CFG['per_nab']} \u00b7 {CFG['free']}",
               c.f("mono_sm"), T.TEXT_MUTED, anchor="rm")

        ty, th = y + T.px(49), T.px(34)
        c.paste(P.timeline(w - pad * 2, th), x0 + pad, ty)
        ey = ty + th + T.px(16)
        c.text((x0 + pad, ey), "\u22125:00", c.f("mono_xs"), T.TEXT_FAINT)
        c.text((x0 + w - pad, ey), "NOW", c.f("mono_xs"), T.PURPLE_LIGHT,
               anchor="rm")

        hy = y + T.px(119)
        f = c.f("mono")
        kw = int(c.w(CFG["hotkey"], f) + T.px(32))
        kh = T.px(T.KBD_H)
        c.paste(P.rounded_rect(kw, kh, T.px(T.R_CONTROL), T.RAISED,
                               T.LINE_STRONG, T.px(1), T.SURFACE), x0 + pad, hy)
        c.text((x0 + pad + kw / 2, hy + kh / 2), CFG["hotkey"], f, T.TEXT,
               anchor="mm")
        c.text((x0 + pad + kw + T.px(13), hy + kh / 2),
               "Press any time to keep what just happened.", c.f("helper"),
               T.TEXT_MUTED)
        return h

    def recent(self, y):
        c = self.c
        y0 = y
        y += self.eyebrow(y, "recent nabs", CFG["recent_count"], arrows=True)
        y += T.px(10)
        total = self.content_w
        gap = T.px(T.THUMB_GAP)
        tw = (total - gap * 2) // 3
        spare = total - tw * 3 - gap * 2
        ph = T.px(T.THUMB_POSTER_H)
        meta_h = T.px(8) + T.px(10) + T.px(3) + T.px(10) + T.px(9) + T.px(4)
        th = ph + meta_h
        x = self.pad
        for i, (tm, dt, size) in enumerate(CFG["nabs"]):
            c.paste(P.rounded_rect(tw, th, T.px(8), T.SURFACE, T.LINE, T.px(1),
                                   T.PANEL), x, y)
            plate = Image.new("RGB", (tw, ph), (0x20, 0x20, 0x2A))
            glyph = P.play_glyph(T.px(22), T.TEXT, "#20202A", 0.4)
            plate.paste(glyph, ((tw - glyph.width) // 2, (ph - glyph.height) // 2))
            # the poster reaches the card's top corners, so re-cut them
            card_top = P.rounded_rect(tw, ph, T.px(8), T.SURFACE, T.LINE,
                                      T.px(1), T.PANEL)
            mask = Image.new("L", (tw, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, tw - 1, ph * 2], radius=T.px(8), fill=255)
            c.img.paste(plate, (x, int(y)), mask)
            fx = c.f("mono_xs")
            c.text((x + T.px(10), y + ph + T.px(8) + T.px(5)), tm, fx, T.TEXT)
            c.text((x + T.px(10), y + ph + T.px(8) + T.px(10) + T.px(3) + T.px(5)),
                   dt, fx, T.TEXT_FAINT)
            c.text((x + tw - T.px(10),
                    y + ph + T.px(8) + T.px(10) + T.px(3) + T.px(5)),
                   size, fx, T.TEXT_FAINT, anchor="rm")
            x += tw + gap + (1 if i < spare else 0)
        y += th + T.px(10)
        # "Open nabs folder" icon button
        f = c.f("value")
        icon = P.folder_icon(T.px(15), T.TEXT, T.RAISED)
        bh = T.px(T.CONTROL_H)
        bw = int(T.px(14) * 2 + icon.width + T.px(7) + c.w("Open nabs folder", f)
                 + T.px(2))
        c.paste(P.rounded_rect(bw, bh, T.px(T.R_CONTROL), T.RAISED,
                               T.LINE_STRONG, T.px(1), T.PANEL), self.pad, y)
        c.paste(icon, self.pad + T.px(14), y + (bh - icon.height) / 2)
        c.text((self.pad + T.px(14) + icon.width + T.px(7), y + bh / 2),
               "Open nabs folder", f, T.TEXT)
        return (y + bh) - y0

    def capture(self, y):
        c, y0 = self.c, y
        y += self.eyebrow(y, "capture") + T.px(10)
        top = y
        rows = []
        pv = T.px(T.ROW_PAD_Y)

        # Nab length: segmented + meter + two figures
        ry = y + pv
        _, sh = segmented(c, self.right - T.px(T.ROW_PAD_X), ry,
                          ["1 min", "3 min", "5 min"], CFG["length_index"])
        my = ry + sh + T.px(9)
        mx = self.right - T.px(T.ROW_PAD_X) - self.col
        c.paste(P.meter(self.col, 0.27, "ok"), mx, my)
        fy = my + T.px(T.METER_H) + T.px(7)
        c.text((mx, fy + T.px(5)), "5 min \u00b7 1.2 GB", c.f("mono_xs"),
               T.TEXT_MUTED)
        c.text((mx + self.col, fy + T.px(5)), "412 GB free", c.f("mono_xs"),
               T.TEXT_FAINT, anchor="rm")
        h = (fy + T.px(10) + pv) - y
        rows.append(("Nab length", y, h))
        y += h

        # Buffer: label + toggle
        self.sep(y)
        ry = y + pv
        tg = P.toggle(CFG["reset"])
        c.paste(tg, self.right - T.px(T.ROW_PAD_X) - tg.width,
                ry + (T.px(T.CONTROL_H) - tg.height) / 2)
        f = c.f("value")
        c.text((self.right - T.px(T.ROW_PAD_X) - tg.width - T.px(9),
                ry + T.px(T.CONTROL_H) / 2), "Start fresh after each nab", f,
               T.TEXT, anchor="rm")
        hy = ry + T.px(T.CONTROL_H) + T.px(8)
        self.helper(hy, "Each nab keeps the five minutes before it.")
        h = (hy + T.px(14) + pv) - y
        rows.append(("Buffer", y, h))
        y += h

        # Nab sound: select + Preview
        self.sep(y)
        ry = y + pv
        bw, bh = button(c, self.right - T.px(T.ROW_PAD_X), ry, "Preview",
                        small=True)
        select(c, self.right - T.px(T.ROW_PAD_X) - bw - T.px(9), ry,
               self.col - bw - T.px(9), CFG["sound"])
        hy = ry + T.px(T.CONTROL_H) + T.px(8)
        self.helper(hy, "A short pip when a nab is written.")
        h = (hy + T.px(14) + pv) - y
        rows.append(("Nab sound", y, h))
        y += h

        # Save nabs to: field + Browse
        self.sep(y)
        ry = y + pv
        bw, bh = button(c, self.right - T.px(T.ROW_PAD_X), ry, "Browse")
        fw = self.col - bw - T.px(9)
        fx = self.right - T.px(T.ROW_PAD_X) - bw - T.px(9) - fw
        c.paste(box(fw, T.px(T.CONTROL_H)), fx, ry)
        c.text((fx + T.px(13), ry + T.px(T.CONTROL_H) / 2), CFG["folder"],
               c.f("value"), T.TEXT)
        h = (ry + T.px(T.CONTROL_H) + pv) - y
        rows.append(("Save nabs to", y, h))
        y += h

        self.card_behind(top, y - top, rows)
        return y - y0

    def hotkeys(self, y):
        c, y0 = self.c, y
        y += self.eyebrow(y, "hotkeys") + T.px(10)
        top = y
        rows, pv = [], T.px(T.ROW_PAD_Y)

        ry = y + pv
        _, kh = hotkey_field(c, self.right - T.px(T.ROW_PAD_X), ry,
                             CFG["hotkey"], 110)
        h = (ry + kh + pv) - y
        rows.append(("Save nab", y, h))
        y += h

        self.sep(y)
        ry = y + pv
        _, kh = hotkey_field(c, self.right - T.px(T.ROW_PAD_X), ry,
                             CFG["open_hotkey"], 150)
        hy = ry + kh + T.px(8)
        self.helper(hy, "Click a field, then press the")
        self.helper(hy + T.px(16), "combination you want. Esc cancels.")
        h = (hy + T.px(30) + pv) - y
        rows.append(("Open Nab'd", y, h))
        y += h

        self.card_behind(top, y - top, rows)
        return y - y0

    def video(self, y):
        c, y0 = self.c, y
        y += self.eyebrow(y, "video") + T.px(10)
        top = y
        rows, pv = [], T.px(T.ROW_PAD_Y)

        ry = y + pv
        bw, _ = button(c, self.right - T.px(T.ROW_PAD_X), ry, "Identify")
        select(c, self.right - T.px(T.ROW_PAD_X) - bw - T.px(9), ry,
               self.col - bw - T.px(9), CFG["monitor"])
        h = (ry + T.px(T.CONTROL_H) + pv) - y
        rows.append(("Monitor", y, h))
        y += h

        self.sep(y)
        ry = y + pv
        select(c, self.right - T.px(T.ROW_PAD_X), ry, self.col, CFG["quality"])
        h = (ry + T.px(T.CONTROL_H) + pv) - y
        rows.append(("Quality", y, h))
        y += h

        self.sep(y)
        ry = y + pv
        select(c, self.right - T.px(T.ROW_PAD_X), ry, self.col, CFG["fps"])
        hy = ry + T.px(T.CONTROL_H) + T.px(8)
        self.helper(hy, "Your display runs at 165 Hz.")
        h = (hy + T.px(14) + pv) - y
        rows.append(("Frame rate", y, h))
        y += h

        self.card_behind(top, y - top, rows)
        return y - y0

    def audio(self, y):
        c, y0 = self.c, y
        y += self.eyebrow(y, "audio") + T.px(10)
        top = y
        rows, pv = [], T.px(T.ROW_PAD_Y)
        rx = self.right - T.px(T.ROW_PAD_X)

        for name, device, vol in (("Speakers", CFG["speakers"], CFG["spk_vol"]),
                                  ("Microphone", CFG["mic"], CFG["mic_vol"])):
            if rows:
                self.sep(y)
            ry = y + pv
            select(c, rx, ry, self.col, device)
            sy = ry + T.px(T.CONTROL_H) + T.px(9)
            c.text((rx - self.col, sy + T.px(9)), f"{vol}%", c.f("mono_sm"),
                   T.TEXT_MUTED, anchor="lm")
            slider(c, rx - T.px(268), rx, sy, vol / 100.0)
            h = (sy + T.px(20) + pv) - y
            rows.append((name, y, h))
            y += h

        self.sep(y)
        ry = y + pv
        bw, _ = button(c, rx, ry, "Test", small=True)
        c.text((rx - bw - T.px(9), ry + T.px(10)), f"{CFG['sync']} ms",
               c.f("mono_sm"), T.TEXT_MUTED, anchor="rm")
        slider(c, rx - bw - T.px(9) - T.px(62) - T.px(190),
               rx - bw - T.px(9) - T.px(62), ry, (CFG["sync"] + 500) / 1000.0)
        hy = ry + T.px(20) + T.px(8)
        self.helper(hy, "Negative pulls audio earlier. Test records a")
        self.helper(hy + T.px(16), "timing pattern and measures the offset.")
        h = (hy + T.px(30) + pv) - y
        rows.append(("A/V sync", y, h))
        y += h

        self.card_behind(top, y - top, rows)
        return y - y0

    # A card is drawn *under* rows that are already on the canvas, so the card
    # is composited first and the row content replayed over it. Cheaper than
    # deferring every row: snapshot, draw the card, paste the rows back.
    def card_behind(self, top, h, rows):
        region = (self.pad, int(top), self.pad + self.content_w, int(top + h))
        content = self.c.img.crop(region)
        panel = Image.new("RGB", content.size, rgb(T.PANEL))
        mask = ImageChops.difference(content, panel).convert("L").point(
            lambda v: 255 if v else 0)
        self.card(top, h)
        self.c.img.paste(content, (self.pad, int(top)), mask)
        for name, ry, rh in rows:
            self.label(ry, name)

    # -- assembly ----------------------------------------------------------
    def build(self):
        top = self.header()
        y = top + self.pad
        for name, fn in (("hero", self.hero), ("recent", self.recent),
                         ("capture", self.capture), ("hotkeys", self.hotkeys),
                         ("video", self.video), ("audio", self.audio)):
            if name != "hero":
                y += T.px(T.GROUP_GAP)
            h = fn(y)
            self.blocks[name] = (y, y + h)
            y += h
        # The panel is full-height on the display it docks to; size the still
        # to the content so nothing is cut off mid-row.
        self.H = int(y + T.px(20) + T.px(T.FOOTER_H) + 1)
        self.c.img = self.c.img.crop((0, 0, self.W, self.H))
        self.c.d = ImageDraw.Draw(self.c.img)
        bottom = self.footer()
        return self.c.img, top, bottom


# -------------------------------------------------------------------- open ---
def open_gif(out, panel_img, blocks, top, bottom, fps=30, tail_ms=900,
             shrink=0.5):
    """The panel dealing in, off nabd_panel_open.sample_open()."""
    W, H = panel_img.size
    shell_bg = Image.new("RGB", (W, H), rgb(T.SHELL))
    body_pad = T.px(T.PANEL_PAD)
    block_w = W - 2 * body_pad
    slip = T.px(M.SLIP)
    order = list(M.BLOCKS)

    # the panel with every block blanked out: header, footer, empty body
    shell_only = panel_img.copy()
    d = ImageDraw.Draw(shell_only)
    for name in order:
        y0, y1 = blocks[name]
        d.rectangle([0, int(y0) - 1, W, int(y1) + 1], fill=rgb(T.PANEL))

    frames, step = [], 1000.0 / fps
    t = 0.0
    while t <= M.OPEN_MS:
        f = M.sample_open(t)
        frame = shell_bg.copy()
        # the window slides right into its dock and is clipped at the dock edge
        vis = int(round(W * f.shell))
        if vis > 0:
            src = shell_only.crop((W - vis, 0, W, H))
            stage = Image.new("RGB", (W, H), rgb(T.SHELL))
            stage.paste(src, (0, 0))
            for i, name in enumerate(order):
                if not f.mapped(i):
                    continue
                y0, y1 = blocks[name]
                strip = panel_img.crop((body_pad, int(y0), body_pad + block_w,
                                        int(y1)))
                edge = f.clip_w(i, block_w)
                dx = f.dx(i) * (slip / max(1, M.SLIP))
                clip = strip.crop((0, 0, edge, strip.height))
                x = body_pad + int(dx) - (W - vis)
                if x + clip.width > 0:
                    stage.paste(clip, (int(x), int(y0)))
            frame.paste(stage, (0, 0))
        if f.alpha < 1.0:
            frame = Image.blend(shell_bg, frame, f.alpha)
        frames.append(frame)
        t += step
    frames += [frames[-1]] * max(1, int(tail_ms / step))

    if shrink != 1.0:
        size = (int(W * shrink), int(H * shrink))
        frames = [f.resize(size, Image.LANCZOS) for f in frames]
    pal = frames[-1].convert("P", palette=Image.ADAPTIVE, colors=96)
    conv = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    conv[0].save(out, save_all=True, append_images=conv[1:], loop=0,
                 duration=int(step), optimize=True, disposal=2)
    return out


def split_columns(img, split_y, gutter=40, bg=T.SHELL):
    """The full-height drawer as two columns, so a README can show all of it."""
    W = img.width
    a = img.crop((0, 0, W, split_y))
    b = img.crop((0, split_y, W, img.height))
    h = max(a.height, b.height)
    out = Image.new("RGB", (W * 2 + gutter * 3, h + gutter * 2), rgb(bg))
    out.paste(a, (gutter, gutter))
    out.paste(b, (gutter * 2 + W, gutter))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--fonts", default=None)
    ap.add_argument("--dpi", type=int, default=192)
    a = ap.parse_args()
    T.set_scale(a.dpi)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(Path(a.fonts) if a.fonts else None)
    if not fonts.ok:
        print("!! Outfit / JetBrains Mono missing - using stand-ins")

    panel = Panel(fonts)
    img, top, bottom = panel.build()
    img.save(out / "settings-full.png")
    split = panel.blocks["hotkeys"][0] - T.px(T.GROUP_GAP)
    split_columns(img, int(split)).save(out / "settings.png")
    open_gif(out / "panel-open.gif", img, panel.blocks, top, bottom,
             shrink=0.5 if a.dpi >= 192 else 1.0)
    for f in sorted(out.glob("*")):
        print(f"  {f.name:22s} {f.stat().st_size/1024:8.0f} KB  ")


if __name__ == "__main__":
    main()
