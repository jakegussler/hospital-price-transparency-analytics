"""Generate Hospital Price Lens raster brand assets from the vector mark.

Renders the "lens" mark (magnifier ring + ascending bar chart) that matches
static/icon.svg, and writes the favicon / app-icon set plus the social OG image
into ../static/.

Run with uv (no project install needed):

    uv run --with pillow python scripts/gen_icons.py

Swapping the header logo does NOT require this script — replace
static/brand/logo.svg + logo-dark.svg. This script only produces the raster
icons and og-image.png.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = (Path(__file__).resolve().parent.parent / "static")
TEAL = (15, 118, 110, 255)      # #0F766E
TEAL_DARK = (11, 59, 56, 255)   # deep teal for gradient
WHITE = (255, 255, 255, 255)
MINT = (204, 251, 241, 255)     # #CCFBF1
SS = 4  # supersample factor


def draw_mark(size, bg=True, stroke=WHITE):
    """Lens mark on a size x size RGBA canvas; geometry mirrors static/icon.svg."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = big / 64.0
    if bg:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=14 * s, fill=TEAL)
    for x, y, h in [(19.5, 30, 7), (25.75, 25, 12), (32, 21, 16)]:
        d.rounded_rectangle([x * s, y * s, (x + 4.5) * s, (y + h) * s], radius=1.5 * s, fill=stroke)
    cx, cy, r = 28 * s, 28 * s, 16.5 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=stroke, width=int(round(4.5 * s)))
    hw = 5 * s
    p0, p1 = (40.2 * s, 40.2 * s), (52 * s, 52 * s)
    d.line([p0, p1], fill=stroke, width=int(round(hw)))
    for (px, py) in (p0, p1):
        rr = hw / 2
        d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=stroke)
    return img.resize((size, size), Image.LANCZOS)


def load_font(size):
    for path, idx in [
        ("/System/Library/Fonts/Helvetica.ttc", 1),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
        ("/Library/Fonts/Arial Bold.ttf", 0),
    ]:
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def main():
    draw_mark(512, bg=True).save(OUT / "icon-512.png")
    draw_mark(192, bg=True).save(OUT / "icon-192.png")
    draw_mark(180, bg=True).save(OUT / "apple-touch-icon.png")
    draw_mark(64, bg=True).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

    W, H = 1200, 630
    grad = Image.new("RGBA", (1, H))
    for y in range(H):
        t = y / (H - 1)
        grad.putpixel((0, y), tuple(int(TEAL[i] + (TEAL_DARK[i] - TEAL[i]) * t) for i in range(4)))
    og = grad.resize((W, H))
    d = ImageDraw.Draw(og)
    og.alpha_composite(draw_mark(220, bg=False, stroke=WHITE), (120, 200))
    title_font, sub_font, url_font = load_font(76), load_font(40), load_font(30)
    tx, ty = 380, 250
    part1 = "Hospital Price "
    w1 = d.textlength(part1, font=title_font)
    d.text((tx, ty), part1, font=title_font, fill=WHITE)
    d.text((tx + w1, ty), "Lens", font=title_font, fill=MINT)
    d.text((tx + 3, ty + 118), "Prices you can actually compare.", font=sub_font, fill=MINT)
    d.text((120, H - 72), "hospitalpricelens.com", font=url_font, fill=MINT)
    og.convert("RGB").save(OUT / "og-image.png")

    print("wrote icons + og-image.png to", OUT)


if __name__ == "__main__":
    main()
