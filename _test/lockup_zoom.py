"""Blow the header lockup up so its construction can be inspected."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import brand  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

# What the panel actually draws, magnified without smoothing.
header = brand.tile_lockup_image(34)
zoom = header.resize((header.width * 5, header.height * 5), Image.NEAREST)

# The same composition rendered large, as a reference for the proportions.
big = brand.tile_lockup_image(120)

sheet = Image.new("RGB", (max(zoom.width, big.width) + 40,
                          zoom.height + big.height + 60), brand.SHELL)
sheet.paste(zoom, (20, 20), zoom)
sheet.paste(big, (20, zoom.height + 40), big)
sheet.save(OUT / "lockup_zoom.png")

print(f"header lockup : {header.width}x{header.height}px  "
      f"aspect {header.width / header.height:.2f}")
print(f"reference     : {big.width}x{big.height}px  "
      f"aspect {big.width / big.height:.2f}")
print(f"official SVG  : {brand.LOCK_WIDTH:.0f}x{brand.LOCK_HEIGHT:.0f} "
      f"aspect {brand.LOCK_WIDTH / brand.LOCK_HEIGHT:.2f}  (mark lockup)")

word = brand.wordmark_image(17)
print(f"\nwordmark @17px: {word.width}x{word.height}  "
      f"aspect {word.width / word.height:.2f}")
print(f"expected aspect: {brand.WORD_BOX_W / brand.WORD_BOX_H:.2f}")
print(f"stroke at that size: "
      f"{brand.WORD_STROKE * 17 / brand.WORD_HEIGHT:.2f}px")
