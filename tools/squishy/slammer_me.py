"""Kevin in the Slammer's mask and a dark suit, on a plain backdrop (grayscale)."""
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SCAN = "/Users/kevinhobster/Desktop/the slammer.jpeg"
BIGGER = 1.18

im = Image.open("kevin.jpg").convert("L")
W, H = im.size
j = json.load(open("face.json"))
person = Image.open("person.png").convert("L")
rng = np.random.default_rng(11)
P = lambda k: np.array(j[k], np.float64)

# --- the mask: three points on the scan to the same three points on Kevin ---
z = lambda x, y: (290 + x / 8, 100 + y / 8)     # mask-grid zoom coords to scan coords
src_pts = np.array([z(195, 378), z(395, 385), z(285, 578)])
le, re_ = P("leftEye").mean(0), P("rightEye").mean(0)
mouth = P("outerLips").mean(0)
dst_pts = np.array([le, re_, mouth])
c = dst_pts.mean(0)
dst_pts = c + (dst_pts - c) * BIGGER + np.array([-70.0, 0.0])  # nudged to our left
# affine taking Kevin coords -> scan coords (what Image.transform wants)
A = np.hstack([dst_pts, np.ones((3, 1))])
coef_x = np.linalg.solve(A, src_pts[:, 0])
coef_y = np.linalg.solve(A, src_pts[:, 1])
scan = Image.open(SCAN).convert("L")
warped = scan.transform((W, H), Image.AFFINE, tuple(coef_x) + tuple(coef_y), resample=Image.BICUBIC)
# the mask's outline on the scan, carried over the same way
outline_zoom = [(110, 240), (200, 225), (330, 235), (470, 250), (540, 290), (548, 400), (530, 520),
                (480, 600), (420, 640), (300, 655), (200, 640), (140, 590), (105, 500), (95, 380), (98, 300)]
inv = np.linalg.inv(np.array([[coef_x[0], coef_x[1], coef_x[2]], [coef_y[0], coef_y[1], coef_y[2]], [0, 0, 1]]))
outline = [tuple((inv @ np.array([*z(x, y), 1]))[:2]) for x, y in outline_zoom]
mk = Image.new("L", (W, H), 0)
ImageDraw.Draw(mk).polygon(outline, fill=255)
mk = mk.filter(ImageFilter.GaussianBlur(10))
# the scan's own JPEG blocks would show when blown up this far: soften, then add cloth grain back
warped = warped.filter(ImageFilter.GaussianBlur(6))
wa = np.asarray(warped, np.float32)
wa = wa + rng.normal(0, 7, wa.shape).astype(np.float32)
wa = (wa - wa.mean()) * 1.15 + wa.mean() + 6

base = np.asarray(im, np.float32)
a = np.asarray(mk, np.float32) / 255
out = base * (1 - a) + wa * a

# --- the suit: below the collar the person becomes jacket, shirt and tie ---
contour = P("contour")
chin_y = contour[:, 1].max()
pm = np.asarray(person, np.float32) / 255
rows = (pm > .5).sum(1)
face_w = contour[:, 0].max() - contour[:, 0].min()
collar_y = int(chin_y + 110)
cx = contour[:, 0].mean()
neck_half = face_w * 0.30
neck_w = neck_half * 2

suit = Image.new("L", (W, H), 0)
sd = ImageDraw.Draw(suit)
sd.rectangle((0, chin_y - 160, W, H), fill=255)
# keep the neck and the face (beard) out of the jacket
sd.rectangle((cx - neck_half, 0, cx + neck_half, collar_y), fill=0)
sd.polygon([tuple(p) for p in contour], fill=0)
sd.ellipse((cx - face_w * .55, chin_y - face_w * 1.2, cx + face_w * .55, chin_y + 20), fill=0)
suit = suit.filter(ImageFilter.GaussianBlur(4))
suit_np = (np.asarray(suit, np.float32) / 255) * pm  # only on the body
jacket = 46 + rng.normal(0, 5, (H, W)).astype(np.float32)
# soft light on the shoulders
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
jacket += 30 * np.exp(-(((xx - cx) / (W * .45)) ** 2 + ((yy - collar_y - 120) / 220) ** 2))

shirt = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(shirt)
v_bottom = collar_y + 560
d.polygon([(cx - neck_half * 1.05, collar_y - 10), (cx + neck_half * 1.05, collar_y - 10), (cx, v_bottom)], fill=255)
for s_ in (-1, 1):  # collar wings round the neck
    d.polygon([(cx + s_ * neck_half * 1.08, collar_y - 90), (cx + s_ * 10, collar_y + 10),
               (cx + s_ * neck_half * 0.55, collar_y + 150), (cx + s_ * neck_half * 1.15, collar_y - 10)], fill=255)
shirt = np.asarray(shirt.filter(ImageFilter.GaussianBlur(3)), np.float32) / 255
tie = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(tie)
d.polygon([(cx - 34, collar_y + 40), (cx + 34, collar_y + 40), (cx + 22, collar_y + 110),
           (cx + 60, v_bottom + 40), (cx, v_bottom + 120), (cx - 60, v_bottom + 40), (cx - 22, collar_y + 110)], fill=255)
d.polygon([(cx - 46, collar_y - 6), (cx + 46, collar_y - 6), (cx + 34, collar_y + 44), (cx - 34, collar_y + 44)], fill=255)  # knot
tie = np.asarray(tie.filter(ImageFilter.GaussianBlur(3)), np.float32) / 255
# lapels: lighter edges along the V
lap = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(lap)
for s in (-1, 1):
    d.line([(cx + s * neck_half * 1.05, collar_y - 10), (cx + s * 18, v_bottom - 20)], fill=255, width=14)
    d.line([(cx + s * neck_half * 1.6, collar_y + 10), (cx + s * neck_half * 0.9, collar_y + 330), (cx + s * 30, v_bottom + 30)], fill=255, width=10)
lap = np.asarray(lap.filter(ImageFilter.GaussianBlur(4)), np.float32) / 255

body = jacket.copy()
body = body * (1 - shirt) + 232 * shirt
body = body * (1 - tie) + 38 * tie
body = body + 40 * lap * (1 - shirt)
shirt_full = np.maximum(suit_np, shirt * pm)
out = out * (1 - shirt_full) + body * shirt_full

# --- plain backdrop ---
pa = np.asarray(person.filter(ImageFilter.GaussianBlur(3)), np.float32) / 255
back = (232 - 22 * (yy / H))
out = out * pa + back * (1 - pa)
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save("kevin-slammer.jpg", quality=95)
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).crop((0, 420, 2316, 2300)).resize((580, 471)).save("kevin-slammer-small.jpg")
print("collar", collar_y, "neck_w", neck_w)
