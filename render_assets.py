"""
Rasterise brand/*.svg into brand/render/*.png.

Run this whenever the SVGs change:

    python render_assets.py

The app loads the PNGs and scales them, so the artwork comes from the supplied
files rather than from geometry typed out by hand. Rendering needs svglib,
reportlab and rlPyCairo; the app itself does not - that is the whole point of
baking the PNGs here.
"""
import sys
from pathlib import Path

BRAND = Path(__file__).resolve().parent / "brand"
RENDER = BRAND / "render"

# Rendered tall enough that every on-screen size is a downscale, never an
# upscale. LANCZOS down from this is indistinguishable from native.
TARGETS = {
    "nabd-wordmark-cream.svg": 512,
    "nabd-wordmark-ink.svg": 512,
    "nabd-lockup-cream.svg": 512,
    "nabd-lockup-ink.svg": 512,
    "nabd-mark-cream.svg": 512,
    "nabd-mark-ink.svg": 512,
    "nabd-app-tile-512.svg": 1024,
}


def render(svg_path, target_height):
    """Rasterise with real alpha.

    renderPM always mattes onto a background, so the same drawing is rendered
    twice - once on white, once on black - and the two are solved for alpha and
    colour. Keying off a single white render only works for flat one-colour
    art, and silently turns the app tile's cream ring into purple.
    """
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM

    def raster(bg):
        drawing = svg2rlg(str(svg_path))
        if drawing is None:
            raise RuntimeError(f"could not parse {svg_path.name}")
        scale = target_height / drawing.height
        drawing.width *= scale
        drawing.height *= scale
        drawing.scale(scale, scale)
        return renderPM.drawToPIL(drawing, bg=bg).convert("RGB")

    return _unmatte(raster(0xFFFFFF), raster(0x000000))


def _unmatte(on_white, on_black):
    """Solve the two composites for straight alpha and colour.

    For a pixel of colour C at coverage a:
        on_white = C*a + 255*(1-a)      on_black = C*a
    so a = 1 - (on_white - on_black)/255, and C = on_black / a.
    """
    from PIL import Image, ImageChops

    # 255*(1-a) per channel; the largest channel is the safest estimate.
    diff = ImageChops.difference(on_white, on_black).split()
    transparency = ImageChops.lighter(ImageChops.lighter(diff[0], diff[1]),
                                      diff[2])
    alpha = ImageChops.invert(transparency)

    # Done on the raw buffers rather than with ImageMath, whose eval() was
    # removed in recent Pillow.
    rgb = on_black.tobytes()
    a_bytes = alpha.tobytes()
    out = bytearray(len(a_bytes) * 4)
    for i, a in enumerate(a_bytes):
        j, k = i * 3, i * 4
        if a:
            out[k] = min(255, rgb[j] * 255 // a)
            out[k + 1] = min(255, rgb[j + 1] * 255 // a)
            out[k + 2] = min(255, rgb[j + 2] * 255 // a)
        out[k + 3] = a
    return Image.frombytes("RGBA", on_black.size, bytes(out))


def main():
    RENDER.mkdir(parents=True, exist_ok=True)
    made = 0
    for name, height in TARGETS.items():
        src = BRAND / name
        if not src.exists():
            print(f"  missing {name}")
            continue
        try:
            img = render(src, height)
        except Exception as exc:
            print(f"  FAILED {name}: {exc}")
            continue
        dest = RENDER / (src.stem + ".png")
        img.save(dest)
        print(f"  {dest.name}  {img.width}x{img.height}")
        made += 1
    print(f"\n{made} assets rendered into {RENDER}")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
