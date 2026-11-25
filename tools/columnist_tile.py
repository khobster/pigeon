"""One-off (needs numpy): python tools/columnist_tile.py tools/hobs-avatar.jpg <outdir>

Columnist tiles from the hobs avatar, aged as one piece: every mark (type,
rules, photo dots) goes through the same ink spread, dropout, paper and scan,
so nothing looks freshly pasted onto the old print."""
import io, math, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter

S = 3                       # draw at 3x, age, then scan down
rng = np.random.default_rng(1989)
HEAD = ("/System/Library/Fonts/HelveticaNeue.ttc", 9)  # Condensed Black
WIDEN = 1.22
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

def noise(h, w, cell):
    small = rng.random((max(2, h // cell), max(2, w // cell))).astype(np.float32)
    return np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255

def halftone(g, cell):
    big = g.rotate(45, expand=True, fillcolor=255)
    W, H = big.size; s = 4
    out = Image.new("L", (W * s, H * s), 255); d = ImageDraw.Draw(out)
    small = big.resize((W // cell, H // cell), Image.BOX)
    for j in range(small.height):
        for i in range(small.width):
            v = small.getpixel((i, j))
            r = cell * math.sqrt((1 - v / 255) / math.pi) * s * 1.05
            cx, cy = (i + .5) * cell * s, (j + .5) * cell * s
            if r > .6: d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    out = out.resize((W, H), Image.LANCZOS).rotate(-45, fillcolor=255)
    w, h = g.size
    return out.crop(((out.width - w) // 2, (out.height - h) // 2, (out.width - w) // 2 + w, (out.height - h) // 2 + h))

def typeset(c, text, size, cx, y):
    """Set a word letter by letter, the way a worn slug prints: no letter sits quite
    straight, on quite the same line, or inks quite as heavily as its neighbor."""
    font = ImageFont.truetype(HEAD[0], size, index=HEAD[1])
    glyphs = []
    for ch in text:
        g = Image.new("L", (int(size * 1.4), int(size * 1.4)), 255)
        ImageDraw.Draw(g).text((size * .2, size * .05), ch, font=font, fill=0, stroke_width=int(rng.integers(0, 2)), stroke_fill=0)
        g = g.crop(ImageOps.invert(g).getbbox() or (0, 0, 1, 1))
        g = g.resize((int(g.width * WIDEN), g.height), Image.LANCZOS)
        glyphs.append(g.rotate(float(rng.normal(0, .8)), resample=Image.BICUBIC, expand=True, fillcolor=255))
    track = .035 * size
    x = cx - (sum(g.width for g in glyphs) + track * (len(glyphs) - 1)) / 2
    cap = max(g.height for g in glyphs)
    for g in glyphs:
        c.paste(Image.new("L", g.size, 0), (int(x), int(y + cap - g.height + rng.normal(0, .6) * S)), ImageOps.invert(g))
        x += g.width + track

def photo(px, cell):
    src = Image.open(sys.argv[1]).convert("RGB").crop((120, 70, 880, 830)).resize((px, px), Image.LANCZOS)
    g = ImageOps.autocontrast(ImageOps.grayscale(src), cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.55).point(lambda v: int(18 + v * .9))
    return halftone(g, cell)

def age(clean, spread=.45, ragged=.10, scan=1.0):
    """clean: L image, 0 ink / 255 paper, at S x. Returns the aged RGB tile at 1x."""
    a = 1 - np.asarray(clean, np.float32) / 255
    h, w = a.shape
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(spread * S)), np.float32) / 255
    # ragged threshold: edges wander, thin strokes thicken, fine dots fill in
    t = .45 + ragged * (noise(h, w, 2 * S) - .5) + .08 * (noise(h, w, 12 * S) - .5) + .08 * (rng.random((h, w)) - .5)
    ink = (a > t).astype(np.float32)
    # worn plate: blotchy dropouts inside solids, a few dust specks on paper
    wear = noise(h, w, 30 * S)  # some areas of the plate print thinner
    ink *= rng.random((h, w)) > .025 + .2 * np.clip(wear - .55, 0, 1)
    ink = np.maximum(ink, (rng.random((h, w)) > .99995).astype(np.float32))
    ink = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(.45 * S)), np.float32) / 255
    # ink is never quite black and never even; newsprint is never quite white
    density = .90 + .07 * noise(h, w, 40 * S)
    paper = 236 + 8 * (noise(h, w, 60 * S) - .5) + 10 * (rng.random((h, w)) - .5)
    v = paper * (1 - ink * density)
    img = Image.fromarray(np.clip(v, 0, 255).astype(np.uint8)).rotate(.35, resample=Image.BICUBIC, fillcolor=236)
    img = img.resize((w // S // 2, h // S // 2), Image.LANCZOS).resize((w // S, h // S), Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(scan * .35)).filter(ImageFilter.UnsharpMask(2, 40, 2))
    rgb = Image.merge("RGB", [img.point(lambda x: min(255, int(x * k))) for k in (1.0, .985, .955)])
    buf = io.BytesIO(); rgb.save(buf, "JPEG", quality=55); buf.seek(0)
    return Image.open(buf).convert("RGB")

def breslin(name):
    W, H = 300 * S, 420 * S
    c = Image.new("L", (W, H), 255); d = ImageDraw.Draw(c)
    p = photo(236 * S, 3 * S)
    c.paste(p, (32 * S, 24 * S)); d.rectangle((31 * S, 23 * S, 268 * S, 260 * S), outline=0, width=2 * S)
    typeset(c, name, 60 * S, W / 2, 298 * S)
    d.rectangle((32 * S, 376 * S, 268 * S, 392 * S), fill=0)
    return age(c)

def lupica(name):
    W, H = 300 * S, 380 * S
    c = Image.new("L", (W, H), 255); d = ImageDraw.Draw(c)
    d.rectangle((14 * S, 12 * S, 286 * S, 368 * S), outline=0, width=2 * S)
    typeset(c, name, 58 * S, W / 2, 38 * S)
    p = photo(240 * S, 3 * S); c.paste(p, (30 * S, 114 * S))
    return age(c)

if __name__ == "__main__":
    out = sys.argv[2]
    a, b = breslin("HOBS"), lupica("HOBS")
    a.save(out + "/tile_breslin.jpg", quality=92); b.save(out + "/tile_lupica.jpg", quality=92)
    sheet = Image.new("RGB", (a.width + b.width + 60, max(a.height, b.height) + 40), (60, 58, 55))
    sheet.paste(a, (20, 20)); sheet.paste(b, (a.width + 40, 20)); sheet.save(out + "/tiles_aged.png")
