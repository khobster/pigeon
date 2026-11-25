"""J. Paul Squishy: Kevin's line, printed as a clipping from a 1990s New York
tabloid.

The column is set the way the Daily News set its sports columns (a heavy
news serif, justified and hyphenated, lines 18.6px apart in a 240px column,
its first line indented) beside a fixed sig box: the rules, the name and the
masked headshot (see tools/squishy_box.py). Then the whole page is printed as
one piece: a 45 degree clustered-dot screen over paper, type and photo alike,
ink spread on the dots, and a scan back down to a sharp, slightly rough JPEG
at twice the size the email shows it.
"""
import io
import math
import re
from pathlib import Path

import numpy as np
import pyphen
import uharfbuzz as hb
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets" / "squishy"
FONT = ASSETS / "Merriweather-Squishy.ttf"  # Merriweather at wght 560, wdth 104 (OFL)

U = 5                      # draw at 5x the page, print, then scan down
K = 2                      # the scan keeps twice the page's pixels (retina)
PITCH, SIZE, COL = 18.6, 17.2, 240   # baseline to baseline, type size, column width
BOX_W, BOX_H = 236, 252    # the sig box
PHOTO_AT = (55, 350)       # headshot slot inside the box, at working scale
PHOTO_SIZE = (1070, 860)
LINES = 13                 # lines of body type the box is tall
GUTTER, MARGIN = 16, 4
PAPER = .88                # newsprint's gray, as screened dots
CELL = 2.2                 # screen pitch, in page pixels
ZOOM = 1.12                # final image is ~1130px wide, shown at 560
HY = pyphen.Pyphen(lang="en_US")

_face = hb.Face(hb.Blob.from_file_path(str(FONT)))
_font = hb.Font(_face)
_pil = ImageFont.truetype(str(FONT), int(SIZE * U))


def _shape(text):
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(_font, buf, {"liga": False})
    k = SIZE * U / _face.upem
    x, out = 0.0, []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((text[info.cluster], x + pos.x_offset * k))
        x += pos.x_advance * k
    return out, x


def _width(s):
    return _shape(s)[1]


def _curly(text):
    """Typewriter quotes to printer's quotes."""
    text = re.sub(r"(^|[\s(\[])\"", "\\1\u201c", text)
    text = text.replace("\"", "\u201d")
    text = re.sub(r"(^|[\s(\[])'", "\\1\u2018", text)
    return text.replace("'", "\u2019")


def _lines(text, col, indent):
    """Greedy justified lines, hyphenating a word that won't fit."""
    space = _width(" ")
    words, lines, cur, first, i = text.split(), [], [], True, 0
    while i < len(words):
        w = words[i]
        avail = col - (indent if first else 0)
        if not cur or sum(map(_width, cur + [w])) + space * .75 * len(cur) <= avail:
            cur.append(w)
            i += 1
            continue
        room = avail - sum(map(_width, cur)) - space * .75 * len(cur)
        for a, b in HY.iterate(w):
            if len(a) >= 2 and len(b) >= 2 and _width(a + "-") <= room:
                cur.append(a + "-")
                words[i] = b
                break
        lines.append((cur, False, first))
        cur, first = [], False
    lines.append((cur, True, first))
    return lines


def lines_needed(text):
    """How many lines `text` sets to in the column."""
    return len(_lines(_curly(text), COL * U, 1.1 * SIZE * U))


def _body(text):
    col, indent = COL * U, 1.1 * SIZE * U
    lines = _lines(_curly(text), col, indent)
    c = Image.new("L", (int(col + 2 * U), int((len(lines) * PITCH + 4) * U)), 255)
    d = ImageDraw.Draw(c)
    space, y = _width(" "), 0
    for words, last, first in lines:
        x = indent if first else 0
        nat = sum(map(_width, words))
        gap = space if last or len(words) < 2 else (col - x - nat) / (len(words) - 1)
        for w in words:
            for ch, gx in _shape(w)[0]:
                d.text((x + gx, y), ch, font=_pil, fill=0)
            x += _width(w) + gap
        y += PITCH * U
    return c


def press(c, rng):
    """Ink on newsprint at working scale: spread, a ragged edge, small dropouts."""
    a = 1 - np.asarray(c, np.float32) / 255
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(U * .3)), np.float32) / 255
    ink = (a > .38 + .10 * (rng.random(a.shape) - .5)).astype(np.float32)
    ink *= rng.random(a.shape) > .02
    return Image.fromarray(((1 - ink) * 255).astype(np.uint8))


def _screen(v, cell):
    """Clustered-dot screen at 45 degrees (v: 0 ink .. 1 paper). Solid ink
    stays solid, so type holds; every tone becomes dots."""
    h, w = v.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = math.radians(45)
    u = (xx * math.cos(t) + yy * math.sin(t)) * 2 * math.pi / cell
    q = (-xx * math.sin(t) + yy * math.cos(t)) * 2 * math.pi / cell
    f = (np.cos(u) + np.cos(q)) / 2
    return ((1 - v) > (1 - f) / 2).astype(np.float32)


def render(text, seed=0):
    """The clipping as JPEG bytes."""
    rng = np.random.default_rng(seed)
    box = np.asarray(Image.open(ASSETS / "box_ink.png").convert("L"), np.float32) / 255
    photo = np.asarray(Image.open(ASSETS / "box_photo.png").convert("L"), np.float32) / 255
    lines = np.asarray(press(_body(text), rng), np.float32) / 255
    bh, bw = box.shape
    m, g = MARGIN * U, GUTTER * U
    W = m + bw + g + lines.shape[1] + 2 * m
    H = max(bh, lines.shape[0]) + 3 * m
    page = np.full((H, W), PAPER, np.float32)
    py, px = m + PHOTO_AT[1], m + PHOTO_AT[0]
    page[py:py + photo.shape[0], px:px + photo.shape[1]] = photo * .97 + .015
    page[m:m + bh, m:m + bw] = np.minimum(page[m:m + bh, m:m + bw], box)
    ox = m + bw + g
    page[m:m + lines.shape[0], ox:ox + lines.shape[1]] = np.minimum(page[m:m + lines.shape[0], ox:ox + lines.shape[1]], lines)

    ink = _screen(page, CELL * U)
    # the dots print: they spread a little and their edges go uneven
    ink = np.asarray(Image.fromarray((ink * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(U * .35)), np.float32) / 255
    ink = (ink > .42 + .12 * (rng.random(ink.shape) - .5)).astype(np.float32)
    small = Image.fromarray(((1 - ink) * 255).astype(np.uint8)).resize((W * K // U, H * K // U), Image.LANCZOS)
    a = np.asarray(small, np.float32) / 255
    vals = 24 + (243 - 24) * a + rng.normal(0, 2.5, a.shape)
    scan = Image.fromarray(np.clip(vals, 0, 255).astype(np.uint8)).convert("RGB")
    buf = io.BytesIO()
    scan.save(buf, "JPEG", quality=72)
    scan = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    big = scan.resize((int(scan.width * ZOOM), int(scan.height * ZOOM)), Image.LANCZOS)
    warm = np.asarray(big, np.float32) * np.array([1.0, .985, .95])  # newsprint is never white
    out = io.BytesIO()
    Image.fromarray(np.clip(warm, 0, 255).astype(np.uint8)).save(out, "JPEG", quality=90)
    return out.getvalue()
