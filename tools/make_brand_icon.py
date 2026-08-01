"""Generate the HACS brand assets.

An original snowflake mark rather than the manufacturer's trademark: this is a
third-party integration and has no affiliation with Carrier. Rendered large and
downsampled so the strokes stay clean at 256 px.

Usage: python tools/make_brand_icon.py
"""

from __future__ import annotations

import math
import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "carrier_ac_ir" / "brand"
SUPER = 2048

BACKGROUND = (12, 74, 130, 255)  # deep cool blue
FOREGROUND = (255, 255, 255, 255)


def arm(draw: ImageDraw.ImageDraw, cx: float, cy: float, angle: float,
        length: float, width: int) -> None:
    """One snowflake spoke with two pairs of swept-back branches."""
    rad = math.radians(angle)
    ex, ey = cx + length * math.cos(rad), cy + length * math.sin(rad)
    draw.line([(cx, cy), (ex, ey)], fill=FOREGROUND, width=width)

    for frac, blen in ((0.52, 0.30), (0.80, 0.20)):
        bx, by = cx + length * frac * math.cos(rad), cy + length * frac * math.sin(rad)
        for sweep in (-52, 52):
            br = math.radians(angle + sweep)
            draw.line(
                [(bx, by), (bx + length * blen * math.cos(br),
                            by + length * blen * math.sin(br))],
                fill=FOREGROUND,
                width=int(width * 0.78),
            )


def render() -> Image.Image:
    img = Image.new("RGBA", (SUPER, SUPER), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, SUPER - 1, SUPER - 1], radius=int(SUPER * 0.22),
                        fill=BACKGROUND)

    c = SUPER / 2
    for angle in range(0, 360, 60):
        arm(d, c, c, angle, SUPER * 0.335, int(SUPER * 0.042))
    r = SUPER * 0.045
    d.ellipse([c - r, c - r, c + r, c + r], fill=FOREGROUND)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = render()
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        master.resize((size, size), Image.LANCZOS).save(OUT / name)
        print(f"wrote {OUT / name} ({size}x{size})")


if __name__ == "__main__":
    main()
