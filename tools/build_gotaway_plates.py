"""Make the blurred "not pictured" plates for The Ones That Got Away.

We can't show the modern pieces (still in copyright), so each one's box
gets a joke instead: a famous public-domain painting (Mona Lisa, Starry
Night, The Scream...) blurred past recognition-ish, with a red rubber stamp
over it of the kind a real gallery puts up (ON LOAN, TEMPORARILY REMOVED). The plates are made once
from Wikimedia Commons originals and committed to heist/gotaway_plates/;
the build copies one in per piece.

    python tools/build_gotaway_plates.py
"""
import io
import json
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "heist" / "gotaway_plates"
API = "https://commons.wikimedia.org/w/api.php"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
W, H = 1120, 600
# (Commons file, plate name, vertical focus 0=top 1=bottom, horizontal focus,
#  the stamp: what a real gallery would put up)
PAINTINGS = [
    ("Mona_Lisa,_by_Leonardo_da_Vinci,_from_C2RMF_retouched.jpg", "mona-lisa", 0.25, 0.5,
     "TEMPORARILY\nREMOVED"),
    ("Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg", "starry-night", 0.4, 0.5,
     "ON LOAN"),
    ("Edvard_Munch,_1893,_The_Scream,_oil,_tempera_and_pastel_on_cardboard,"
     "_91_x_73_cm,_National_Gallery_of_Norway.jpg", "the-scream", 0.35, 0.5,
     "ON LOAN"),
    ("1665_Girl_with_a_Pearl_Earring.jpg", "pearl-earring", 0.35, 0.5,
     "TEMPORARILY\nREMOVED"),
    ("Tsunami_by_hokusai_19th_century.jpg", "great-wave", 0.4, 0.5,
     "ON LOAN"),
    ("Whistlers_Mother_high_res.jpg", "whistlers-mother", 0.45, 0.8,
     "TEMPORARILY\nREMOVED"),
    ("Georges_Seurat_-_A_Sunday_on_La_Grande_Jatte_--_1884_-_Google_Art_Project.jpg", "grande-jatte", 0.5, 0.5,
     "ON LOAN"),
    ("Vermeer_-_The_Milkmaid.jpg", "milkmaid", 0.4, 0.5,
     "TEMPORARILY\nREMOVED"),
]
RED = (214, 40, 40)
FONT = "/System/Library/Fonts/Helvetica.ttc"


def fetch(file):
    d = requests.get(API, params={"action": "query", "format": "json", "prop": "imageinfo",
                                  "iiprop": "url", "iiurlwidth": 1400, "titles": "File:" + file},
                     headers=HEAD, timeout=60).json()
    ii = next(iter(d["query"]["pages"].values()))["imageinfo"][0]
    r = requests.get(ii.get("thumburl") or ii["url"], headers=HEAD, timeout=120)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def crop(im, focus, hfocus):
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    top = round((im.height - H) * focus)
    left = round((im.width - W) * hfocus)
    return im.crop((left, top, left + W, top + H))


def stamp(im, text):
    """A crooked red rubber stamp, sized to fill most of the plate's width."""
    size = 150
    while True:
        font = ImageFont.truetype(FONT, size, index=1)  # Helvetica Bold
        box = ImageDraw.Draw(im).multiline_textbbox((0, 0), text, font=font, align="center", spacing=8)
        if box[2] - box[0] <= W * 0.55 or size <= 60:
            break
        size -= 6
    tw, th = round(box[2] - box[0]), round(box[3] - box[1])
    pad, line = 30, 9
    layer = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((line // 2, line // 2, layer.width - line // 2, layer.height - line // 2),
                outline=RED + (235,), width=line)
    d.multiline_text((pad - box[0], pad - box[1]), text, font=font, fill=RED + (235,),
                     align="center", spacing=8)
    layer = layer.rotate(-8, expand=True, resample=Image.BICUBIC)
    im.paste(layer, ((W - layer.width) // 2, (H - layer.height) // 2), layer)
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for file, name, focus, hfocus, text in PAINTINGS:
        im = crop(fetch(file), focus, hfocus).filter(ImageFilter.GaussianBlur(26))
        im = Image.blend(im, Image.new("RGB", im.size, (255, 255, 255)), 0.18)
        stamp(im, text).save(OUT / f"{name}.jpg", "JPEG", quality=82, optimize=True)
        made.append(name)
        print(f"  {name}")
    (OUT / "plates.json").write_text(json.dumps(made, indent=0))
    print(f"wrote {len(made)} plates -> {OUT}")


if __name__ == "__main__":
    main()
