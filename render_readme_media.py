"""Render the README artwork, off the app's own motion data.

Everything here is driven by nabd_banner.py / nabd_banner_frames.py so the GIF
is the real 4,120 ms timeline, not an impression of it.

    python render_readme_media.py docs/media --fonts vendor/fonts
"""
from __future__ import annotations
import argparse, math, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from PIL import Image, ImageDraw, ImageFont, ImageFilter

import nabd_banner as M
import nabd_banner_frames as F

PURPLE      = "#6C3BAA"
PURPLE_LIGHT= "#9B6BD8"
PURPLE_DEEP = "#4E2A7D"
CREAM       = "#E8E4DC"
CARD_CREAM  = "#F3EFE9"
DETAIL_FG   = "#E3D8F5"
INK         = "#17161A"
SHELL       = "#0A0A0C"
DANGER      = "#B4483E"

RULE_ALPHA = 0.75
PAD_X, RING, GAP = 20, 30, 16
RING_CY, TITLE_CY, DETAIL_CY = 37, 28, 48
RULE_H, COPY_RISE = 3, 6
MARGIN_RIGHT, MARGIN_TOP = 24, 64

BRAND = REPO / "brand" / "render"


def rgb(h):
    if isinstance(h, (tuple, list)):
        return tuple(h)
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    a, b = rgb(a), rgb(b)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ---------------------------------------------------------------- fonts ----
class Fonts:
    def __init__(self, d: Path | None):
        self.dir = d
        self.ok = True
        self.ui = self._find(["Outfit-Regular", "Outfit[wght]", "Outfit-VariableFont_wght", "Outfit"])
        self.ui_med = self._find(["Outfit-Medium", "Outfit-SemiBold"]) or self.ui
        self.mono = self._find(["JetBrainsMono-Regular", "JetBrainsMono[wght]", "JetBrainsMono-VariableFont_wght", "JetBrainsMono"])
        if not self.ui:
            self.ok = False
            self.ui = self.ui_med = _sys("Poppins-Regular.ttf") or _sys("DejaVuSans.ttf")
            self.ui_med = _sys("Poppins-Medium.ttf") or self.ui
        if not self.mono:
            self.ok = False
            self.mono = _sys("DejaVuSansMono.ttf")

    def _find(self, stems):
        if not self.dir or not self.dir.is_dir():
            return None
        files = list(self.dir.rglob("*.ttf")) + list(self.dir.rglob("*.otf"))
        for stem in stems:
            for f in files:
                if f.stem.lower() == stem.lower():
                    return f
        for stem in stems:
            for f in files:
                if f.stem.lower().startswith(stem.lower().split("[")[0].split("-")[0]):
                    return f
        return None

    def load(self, which, size, weight=None):
        path = {"ui": self.ui, "med": self.ui_med, "mono": self.mono}[which]
        f = ImageFont.truetype(str(path), size)
        if weight:
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
        return f


def _sys(name):
    for root in ("/usr/share/fonts/truetype/google-fonts", "/usr/share/fonts/truetype/dejavu"):
        p = Path(root) / name
        if p.exists():
            return p
    return None


# ------------------------------------------------------------- backdrop ----
def backdrop(w, h, scale):
    """Near-black shell with one soft purple bloom behind the banner corner."""
    img = Image.new("RGB", (w, h), rgb(SHELL))
    glow = Image.new("L", (w // 4, h // 4), 0)
    d = ImageDraw.Draw(glow)
    cx, cy = int(w * 0.79) // 4, int(h * 0.42) // 4
    r = int(min(w, h) * 0.62) // 4
    for i in range(24):
        t = i / 23
        d.ellipse([cx - r * (1 - t * .96), cy - r * (1 - t * .96),
                   cx + r * (1 - t * .96), cy + r * (1 - t * .96)],
                  fill=int(4 + 30 * t ** 2))
    glow = glow.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(scale * 18))
    img = Image.composite(Image.new("RGB", (w, h), rgb(PURPLE_DEEP)), img, glow)
    return img


# ------------------------------------------------------------ the banner ----
def draw_banner(bg, frame, fonts, scale, title, detail, field=PURPLE,
                field_line=PURPLE_LIGHT, origin=None):
    """Paste one sampled frame of the banner onto `bg`, exactly as banner.py
    composites it: card, ring, two lines of copy, draining rule."""
    px = lambda v: int(round(v * scale))
    W, H = bg.size
    w, h = max(1, px(frame.w)), max(1, px(frame.h))
    if origin is None:
        x = W - px(MARGIN_RIGHT) - w
        y = px(MARGIN_TOP) + px(M.CARD_H) - h
    else:
        ox, oy = origin
        x = ox + px(M.CARD_W) - w
        y = oy + px(M.CARD_H) - h

    even = max(4, min(76, int(round(frame.h / 2.0)) * 2))
    r = 2 + (12 - 2) * (even - 4) / 72
    card = F.card(px(M.CARD_W), px(even), px(r), px(4),
                  1.0 if even <= 6 else 0.0, bg=field, line=field_line)
    if card.width != w:
        card = card.resize((w, card.height), Image.BILINEAR)
    if card.height != h:
        card = card.resize((w, h), Image.BILINEAR)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.alpha_composite(card)
    d = ImageDraw.Draw(layer)

    if frame.copy > 0.001:
        rise = px(COPY_RISE) * (1.0 - frame.copy)
        index = int(round(frame.ring * F.RING_FRAMES))
        if index > 0:
            step = round(max(0.0, min(1.0, frame.copy)) * 8) / 8.0
            ring = F.ring_frame(px(RING), index / F.RING_FRAMES,
                                color=CARD_CREAM, bg=field).convert("RGB")
            if step < 1.0:
                ring = Image.blend(Image.new("RGB", ring.size, rgb(field)), ring, step)
            layer.paste(ring, (px(PAD_X), int(px(RING_CY - RING / 2) + rise)))
        tx = px(PAD_X + RING + GAP)
        ft = fonts.load("med", px(15), weight=500)
        fd = fonts.load("mono", px(12))
        d.text((tx, px(TITLE_CY) + rise), title, font=ft,
               fill=mix(field, CARD_CREAM, frame.copy) + (255,), anchor="lm")
        d.text((tx, px(DETAIL_CY) + rise), detail, font=fd,
               fill=mix(field, DETAIL_FG, frame.copy) + (255,), anchor="lm")

    shown = 1.0 - frame.line
    rule_w = int(w * frame.drain) // 2 * 2
    if rule_w > 0 and frame.h >= M.CARD_H - 1:
        colour = mix(field, mix(field, CARD_CREAM, RULE_ALPHA),
                     round(shown * 8) / 8.0)
        rh = max(1, px(RULE_H))
        mask = card.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
        strip = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(strip).rectangle([0, h - rh, rule_w - 1, h - 1],
                                        fill=colour + (255,))
        strip.putalpha(Image.composite(strip.getchannel("A"),
                                       Image.new("L", (w, h), 0), mask))
        layer.alpha_composite(strip)

    if frame.alpha < 1.0:
        a = layer.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, frame.alpha))))
        layer.putalpha(a)
    out = bg.copy()
    out.paste(layer, (x, y), layer)
    return out


# ----------------------------------------------------------------- GIF -----
def banner_gif(out, fonts, title="Nabbed", detail="5:00 · 1.2 GB",
               scale=2.0, fps=25, css=(452, 176), field=PURPLE,
               field_line=PURPLE_LIGHT, tail_ms=520):
    # Flat shell, no bloom: a gradient survives a 128-colour GIF palette as
    # visible banding, and the banner is the subject anyway.
    w, h = int(css[0] * scale), int(css[1] * scale)
    bg = Image.new("RGB", (w, h), rgb(SHELL))
    frames, step = [], 1000.0 / fps
    t = 0.0
    while t < M.TOTAL_MS:
        frames.append(draw_banner(bg, M.sample(t), fonts, scale, title, detail,
                                  field, field_line,
                                  origin=(w - int(MARGIN_RIGHT * scale) - int(M.CARD_W * scale),
                                          int(38 * scale))))
        t += step
    hold = int(tail_ms / step)
    frames += [bg] * max(1, hold)

    pal = frames[len(frames) // 3].convert("P", palette=Image.ADAPTIVE, colors=64)
    conv = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    conv[0].save(out, save_all=True, append_images=conv[1:], loop=0,
                 duration=int(step), optimize=True, disposal=2)
    return out


# ----------------------------------------------------------------- hero ----
def fit(img, height):
    w = int(round(img.width * height / img.height))
    return img.resize((w, height), Image.LANCZOS)


def hero(out, fonts, w=1280, h=440, scale=2):
    W, H = w * scale, h * scale
    img = backdrop(W, H, scale)
    lock = fit(Image.open(BRAND / "nabd-lockup-cream.png").convert("RGBA"), int(108 * scale))
    x0 = int(84 * scale)
    y0 = int(96 * scale)
    img.paste(lock, (x0, y0), lock)

    d = ImageDraw.Draw(img)
    f_tag = fonts.load("ui", int(30 * scale), weight=400)
    f_sub = fonts.load("ui", int(18 * scale), weight=400)
    f_key = fonts.load("mono", int(17 * scale))

    d.text((x0 + int(2 * scale), y0 + lock.height + int(38 * scale)),
           "Instant replay for Windows.", font=f_tag, fill=rgb(CREAM), anchor="la")
    d.text((x0 + int(2 * scale), y0 + lock.height + int(86 * scale)),
           "The last few minutes are always recorded. One key writes them to an mp4.",
           font=f_sub, fill=mix(SHELL, CREAM, 0.62), anchor="la")

    # the hotkey chip
    chip_y = y0 + lock.height + int(126 * scale)
    label = "Alt  +  Insert"
    tw = d.textlength(label, font=f_key)
    cw, ch = int(tw + 34 * scale), int(38 * scale)
    chip = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ImageDraw.Draw(chip).rounded_rectangle([0, 0, cw - 1, ch - 1],
                                           radius=int(8 * scale),
                                           fill=rgb(PURPLE) + (255,))
    img.paste(chip, (x0 + int(2 * scale), chip_y), chip)
    d.text((x0 + int(2 * scale) + cw // 2, chip_y + ch // 2), label,
           font=f_key, fill=rgb(CARD_CREAM), anchor="mm")

    # the banner at rest, bottom-right
    rest = M.sample(2000)
    card_x = W - int(96 * scale) - int(M.CARD_W * scale)
    card_y = H - int(110 * scale) - int(M.CARD_H * scale)
    img = draw_banner(img, rest, fonts, scale, "Nabbed", "5:00 · 1.2 GB",
                      origin=(card_x, card_y))
    img = img.resize((w, h), Image.LANCZOS)
    img.save(out)
    return out


# ------------------------------------------------------------- pipeline ----
def pipeline(out, fonts, w=1280, h=404, scale=2):
    W, H = w * scale, h * scale
    img = Image.new("RGB", (W, H), rgb(SHELL))
    d = ImageDraw.Draw(img)
    s = lambda v: int(round(v * scale))
    f_box = fonts.load("ui", s(16), weight=500)
    f_sm = fonts.load("ui", s(13), weight=400)
    f_mono = fonts.load("mono", s(12))
    f_eye = fonts.load("mono", s(11))

    def box(x, y, bw, bh, title, sub=None, fill=None, stroke=PURPLE_LIGHT,
            text=CREAM, radius=10, subcol=None):
        b = Image.new("RGBA", (s(bw), s(bh)), (0, 0, 0, 0))
        db = ImageDraw.Draw(b)
        db.rounded_rectangle([0, 0, s(bw) - 1, s(bh) - 1], radius=s(radius),
                             fill=(rgb(fill) + (255,)) if fill else (0, 0, 0, 0),
                             outline=rgb(stroke) + (255,), width=max(1, s(1.4)))
        img.paste(b, (s(x), s(y)), b)
        cy = s(y + bh / 2)
        if sub:
            d.text((s(x + bw / 2), cy - s(9)), title, font=f_box, fill=rgb(text), anchor="mm")
            d.text((s(x + bw / 2), cy + s(11)), sub, font=f_mono,
                   fill=rgb(subcol) if subcol else mix(SHELL, text, 0.55),
                   anchor="mm")
        else:
            d.text((s(x + bw / 2), cy), title, font=f_box, fill=rgb(text), anchor="mm")

    def arrow(x1, y1, x2, y2, colour=PURPLE_LIGHT, dashed=False):
        d.line([s(x1), s(y1), s(x2), s(y2)], fill=rgb(colour), width=max(1, s(1.6)))
        a = math.atan2(y2 - y1, x2 - x1)
        L = 9
        d.polygon([(s(x2), s(y2)),
                   (s(x2 - L * math.cos(a - .42)), s(y2 - L * math.sin(a - .42))),
                   (s(x2 - L * math.cos(a + .42)), s(y2 - L * math.sin(a + .42)))],
                  fill=rgb(colour))

    d.text((s(64), s(40)), "ALWAYS RECORDING", font=f_eye,
           fill=rgb(PURPLE_LIGHT), anchor="la")

    box(64, 74, 250, 62, "ddagrab", "GPU desktop capture")
    box(64, 156, 250, 62, "WASAPI loopback + mic", "in-process PCM mix")
    arrow(314, 105, 372, 130)
    arrow(314, 187, 372, 158)
    box(372, 112, 190, 62, "h264_nvenc", "zero-copy, no readback",
        fill=PURPLE, stroke=PURPLE, text=CARD_CREAM, subcol=DETAIL_FG)
    arrow(562, 143, 620, 143)
    box(620, 112, 210, 62, "2 s .ts segments", "written straight to disk")
    arrow(830, 143, 888, 143)
    box(888, 96, 328, 94, "ring buffer", "oldest segments pruned · capped",
        stroke=PURPLE_LIGHT)

    d.text((s(64), s(272)), "ON THE HOTKEY", font=f_eye, fill=rgb(CREAM), anchor="la")
    box(64, 306, 250, 62, "Alt + Insert", "RegisterHotKey", stroke=CREAM)
    arrow(314, 337, 372, 337, colour=CREAM)
    box(372, 306, 250, 62, "concat -c copy", "stream copy, no re-encode", stroke=CREAM)
    arrow(622, 337, 680, 337, colour=CREAM)
    box(680, 306, 210, 62, "nab.mp4", "Videos\\Nabd", fill=PURPLE,
        stroke=PURPLE, text=CARD_CREAM, subcol=DETAIL_FG)
    # buffer feeds the concat
    d.line([s(1052), s(190), s(1052), s(240), s(497), s(240), s(497), s(306)],
           fill=rgb(PURPLE_LIGHT), width=max(1, s(1.4)))
    arrow(497, 296, 497, 306)
    d.text((s(760), s(232)), "the newest N minutes", font=f_sm,
           fill=mix(SHELL, CREAM, 0.5), anchor="mb")

    d.text((s(920), s(337)), "no CPU spike · finishes near-instantly",
           font=f_sm, fill=mix(SHELL, CREAM, 0.45), anchor="lm")

    img.resize((w, h), Image.LANCZOS).save(out)
    return out


def palette(out, fonts, w=1280, h=190, scale=2):
    W, H = w * scale, h * scale
    img = Image.new("RGB", (W, H), rgb(SHELL))
    d = ImageDraw.Draw(img)
    s_ = lambda v: int(round(v * scale))
    f_name = fonts.load("ui", s_(15), weight=500)
    f_hex = fonts.load("mono", s_(12))
    f_role = fonts.load("ui", s_(12), weight=400)
    swatches = [("Nab'd Purple", PURPLE, "logo field, primary actions"),
                ("Purple Light", PURPLE_LIGHT, "dark-UI linework"),
                ("Purple Deep", PURPLE_DEEP, "pressed / hover"),
                ("Cream", CREAM, "the logo on purple"),
                ("Ink", INK, "the logo on light"),
                ("Shell", SHELL, "app background")]
    n = len(swatches)
    pad, gap = 64, 18
    cw = (w - pad * 2 - gap * (n - 1)) / n
    for i, (name, hexv, role) in enumerate(swatches):
        x = pad + i * (cw + gap)
        chip = Image.new("RGBA", (s_(cw), s_(74)), (0, 0, 0, 0))
        ImageDraw.Draw(chip).rounded_rectangle(
            [0, 0, s_(cw) - 1, s_(74) - 1], radius=s_(10),
            fill=rgb(hexv) + (255,),
            outline=rgb("#26242B") + (255,) if hexv in (SHELL, INK) else None,
            width=max(1, s_(1.2)))
        img.paste(chip, (s_(x), s_(46)), chip)
        d.text((s_(x), s_(140)), name, font=f_name, fill=rgb(CREAM), anchor="la")
        d.text((s_(x), s_(162)), hexv.upper(), font=f_hex,
               fill=rgb(PURPLE_LIGHT), anchor="la")
    img.resize((w, h), Image.LANCZOS).save(out)
    return out


def logos(out, fonts, w=1280, h=300, scale=2):
    W, H = w * scale, h * scale
    img = Image.new("RGB", (W, H), rgb(SHELL))
    d = ImageDraw.Draw(img)
    s_ = lambda v: int(round(v * scale))
    f_cap = fonts.load("mono", s_(11))

    field = Image.new("RGBA", (s_(560), s_(150)), (0, 0, 0, 0))
    ImageDraw.Draw(field).rounded_rectangle([0, 0, s_(560) - 1, s_(150) - 1],
                                            radius=s_(14), fill=rgb(PURPLE) + (255,))
    lock = fit(Image.open(BRAND / "nabd-lockup-cream.png").convert("RGBA"), s_(58))
    field.paste(lock, ((s_(560) - lock.width) // 2, (s_(150) - lock.height) // 2), lock)
    img.paste(field, (s_(64), s_(56)), field)
    d.text((s_(64), s_(226)), "PRIMARY LOCKUP — CREAM ON THE PURPLE FIELD",
           font=f_cap, fill=rgb(PURPLE_LIGHT), anchor="la")

    tile = Image.open(BRAND / "nabd-app-tile-512.png").convert("RGBA")
    for i, size in enumerate((150, 96, 64, 40)):
        t = tile.resize((s_(size), s_(size)), Image.LANCZOS)
        img.paste(t, (s_(688 + sum((150, 96, 64, 40)[:i]) + i * 26),
                      s_(56 + (150 - size) // 2)), t)
    d.text((s_(688), s_(226)), "APP TILE — 22.5% RADIUS, 58% RING, HOLDS TO 16 PX",
           font=f_cap, fill=rgb(PURPLE_LIGHT), anchor="la")
    img.resize((w, h), Image.LANCZOS).save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--fonts", default=None)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(Path(a.fonts) if a.fonts else None)
    if not fonts.ok:
        print("!! WARNING: Outfit / JetBrains Mono not found — using stand-ins.")
        print("   ui =", fonts.ui, " mono =", fonts.mono)
    hero(out / "hero.png", fonts)
    pipeline(out / "pipeline.png", fonts)
    palette(out / "palette.png", fonts)
    logos(out / "logos.png", fonts)
    banner_gif(out / "banner.gif", fonts)
    banner_gif(out / "banner-fail.gif", fonts, title="Nab failed",
               detail="display lost — see log", field=DANGER,
               field_line="#D2665C")
    for f in sorted(out.iterdir()):
        print(f"  {f.name:22s} {f.stat().st_size/1024:8.0f} KB")


if __name__ == "__main__":
    main()
