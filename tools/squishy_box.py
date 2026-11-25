"""One-off (macOS, needs numpy): build J. Paul Squishy's sig box.

    python tools/squishy_box.py <masked-headshot.jpg>

Writes the two fixed pieces heist/squishy.py sets beside each day's line:
box_ink.png (the rules and the name, already printed) and box_photo.png (the
continuous-tone headshot for its slot). Both are at the renderer's working
scale; the daily build screens them together with the type, so the box and
the words come off the same plate. The headshot itself (Kevin in the Slammer's
mask and a suit) was made from his photo with tools/squishy/slammer_me.py.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from heist.squishy import BOX_W, BOX_H, PHOTO_AT, PHOTO_SIZE, U, press  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "heist" / "assets" / "squishy"
HEAD = "/System/Library/Fonts/Helvetica.ttc"  # Helvetica Bold, like the Daily News sig boxes


def name_plate(lines, w, h):
    c = Image.new("L", (w * U, h * U), 255)
    d = ImageDraw.Draw(c)
    line_h = h * U / len(lines)
    for i, s in enumerate(lines):
        size = 10
        while True:  # the largest size that fits the box and its line
            f = ImageFont.truetype(HEAD, size + 2, index=1)
            l, tp, r, b = d.textbbox((0, 0), s, font=f)
            if r - l > w * U * .86 or b - tp > line_h * .86:
                break
            size += 2
        f = ImageFont.truetype(HEAD, size, index=1)
        l, tp, r, b = d.textbbox((0, 0), s, font=f)
        d.text(((w * U - (r - l)) / 2 - l, i * line_h + (line_h - (b - tp)) / 2 - tp), s, font=f, fill=0,
               stroke_width=int(U * .45), stroke_fill=0)
    return c


def main():
    c = Image.new("L", (BOX_W * U, BOX_H * U), 255)
    d = ImageDraw.Draw(c)
    side, top, bottom = 7, 2, 6  # heavy side and bottom rules, a hairline on top
    d.rectangle((0, 0, side * U, BOX_H * U), fill=0)
    d.rectangle(((BOX_W - side) * U, 0, BOX_W * U, BOX_H * U), fill=0)
    d.rectangle((0, (BOX_H - bottom) * U, BOX_W * U, BOX_H * U), fill=0)
    d.rectangle((0, 0, BOX_W * U, top * U), fill=0)
    c.paste(name_plate(["J. PAUL", "SQUISHY"], BOX_W - 2 * side - 16, 56), ((side + 8) * U, (top + 6) * U))
    press(c, np.random.default_rng(1993)).save(OUT / "box_ink.png", optimize=True)

    src = Image.open(sys.argv[1]).convert("L").crop((0, 420, 2316, 2300))
    g = ImageOps.fit(src, PHOTO_SIZE, centering=(.5, .45))
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(0.92).point(lambda v: int(255 * (v / 255) ** 1.05))
    g = g.filter(ImageFilter.GaussianBlur(U * .6))  # the screen does the detail
    g.save(OUT / "box_photo.png", optimize=True)
    print(f"wrote {OUT}/box_ink.png and box_photo.png (photo at {PHOTO_AT})")


if __name__ == "__main__":
    main()
