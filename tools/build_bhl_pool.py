"""Curate the Biodiversity Heritage Library pool: hand-colored natural
history plates (Gould's birds, Curtis's botanicals, Merian's insects, Reeve's
shells, Hewitson's butterflies, Redoute's lilies).

BHL publishes its whole catalog as monthly tab-separated dumps on S3 and
serves every page scan keylessly from the same bucket, at full resolution
(3,000 to 7,000px). Only a curated list of great illustrated books is used:
across BHL most "Illustration" pages are black-and-white journal figures.
Within those books we keep public-domain items, score each plate's color on
its small thumbnail (text pages and pale engravings score low), and cap how
many plates any one book contributes.

    python tools/build_bhl_pool.py heist/bhl_pool.json [dump_dir]

dump_dir (optional) holds title/item/page .txt.gz already downloaded;
otherwise they're fetched (page.txt.gz is ~600MB).
"""
import csv
import gzip
import io
import json
import math
import os
import random
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

DUMPS = "https://bhl-open-data.s3.us-east-2.amazonaws.com/data/{name}.txt.gz"
WEB = "https://bhl-open-data.s3.us-east-2.amazonaws.com/web/{bc}/{bc}_{seq:04d}_{size}.webp"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}
# TitleID -> (plates to keep, book as we name it, its artist)
BOOKS = {
    706: (160, "Curtis's Botanical Magazine", "Various artists"),
    8129: (70, "Conchologia Iconica", "Lovell Reeve"),
    383: (70, "Edwards's Botanical Register", "Various artists"),
    382: (50, "The Botanical Register", "Sydenham Edwards"),
    8763: (60, "Lepidoptera Indica", "Frederic Moore"),
    105698: (70, "The Birds of Australia", "John Gould"),
    62760: (60, "Seba's Thesaurus", "Albertus Seba"),
    51750: (50, "The Orchid Album", "John Nugent Fitch"),
    54727: (60, "The Birds of Asia", "John Gould"),
    537: (50, "Les Liliacees", "Pierre-Joseph Redoute"),
    133931: (50, "The Birds of New Guinea", "John Gould"),
    12625: (50, "Illustrations of Exotic Butterflies", "William Chapman Hewitson"),
    63636: (40, "Birds of Africa", "Francois Le Vaillant"),
    60852: (40, "Histoire naturelle des perroquets", "Francois Le Vaillant"),
    41517: (30, "Reichenbachia", "Henry George Moon"),
    51672: (30, "Reichenbachia", "Henry George Moon"),
    61652: (30, "Birds of Paradise", "Francois Le Vaillant"),
    87591: (30, "Les Roses", "Pierre-Joseph Redoute"),
    63607: (40, "Metamorphosis of the Insects of Surinam", "Maria Sibylla Merian"),
    102214: (30, "Kunstformen der Natur", "Ernst Haeckel"),
    51215: (30, "Hummingbirds (Trochilidae)", "John Gould"),
    156962: (30, "Toucans (Ramphastidae)", "John Gould"),
    82494: (20, "Birds of Paradise (Paradiseidae)", "John Gould"),
    131250: (10, "Pittas (Pittidae)", "John Gould"),
}
COLORFUL = 25  # thumbnail colorfulness: text ~5-9, pale engravings ~11-20, plates 30-110
SEED = 20261123
csv.field_size_limit(10**9)


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        yield from r


def dump(name, where):
    path = os.path.join(where, f"{name}.txt.gz")
    if not os.path.exists(path):
        with requests.get(DUMPS.format(name=name), headers=HEAD, timeout=600, stream=True) as r:
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    return path


def colorfulness(bc, seq):
    """Hasler-Susstrunk colorfulness of the page thumbnail, margins cropped."""
    raw = requests.get(WEB.format(bc=bc, seq=seq, size="thumb"), headers=HEAD, timeout=40).content
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    px = list(im.crop((int(w * .08), int(h * .06), int(w * .92), int(h * .94))).getdata())
    rg = [r - g for r, g, b in px]
    yb = [0.5 * (r + g) - b for r, g, b in px]

    def ms(a):
        m = sum(a) / len(a)
        return m, math.sqrt(sum((x - m) ** 2 for x in a) / len(a))
    (mr, sr), (my, sy) = ms(rg), ms(yb)
    return math.sqrt(sr * sr + sy * sy) + 0.3 * math.sqrt(mr * mr + my * my)



def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_bhl_pool.py <out.json> [dump_dir]")
    where = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
    titles = {int(r["TitleID"]): r for r in rows(dump("title", where)) if int(r["TitleID"]) in BOOKS}
    items = {}
    for r in rows(dump("item", where)):
        status, lic = r["CopyrightStatus"].lower(), r["LicenseType"].lower()
        if int(r["TitleID"]) in BOOKS and not lic and (status.startswith("public domain")
                                                       or "not in copyright" in status
                                                       or status == "not_in_copyright"):
            items[int(r["ItemID"])] = r
    plates = {}
    for r in rows(dump("page", where)):
        if r["ItemID"].isdigit() and int(r["ItemID"]) in items and "Illustration" in r["PageTypeName"]:
            tid = int(items[int(r["ItemID"])]["TitleID"])
            plates.setdefault(tid, []).append(r)
    rng = random.Random(SEED)

    def vet(page):
        item = items[int(page["ItemID"])]
        tid = int(item["TitleID"])
        bc, seq = item["BarCode"], int(page["SequenceOrder"])
        _, book, artist = BOOKS[tid]
        label = " ".join(x for x in (page["PagePrefix"], page["PageNumber"]) if x).strip() or "Plate"
        title = f"{label}, from {book}"
        if not secular(title) or not inoffensive(title):
            return None
        try:
            if colorfulness(bc, seq) < COLORFUL:
                return None
            t = requests.get(WEB.format(bc=bc, seq=seq, size="thumb"), headers=HEAD, timeout=40)
            if not is_color(t.content):
                return None
        except Exception:  # noqa: BLE001
            return None
        year = item["Year"] or titles[tid]["StartYear"]
        return {
            "museum": "the Biodiversity Heritage Library",
            "title": title,
            "artist": artist,
            "year": re.sub(r"\s+", " ", year)[:40],
            "medium": "",
            "image": WEB.format(bc=bc, seq=seq, size="full"),
            "url": f"https://www.biodiversitylibrary.org/page/{page['PageID']}",
        }

    pool = []
    for tid, (want, _, _) in BOOKS.items():
        pages = plates.get(tid, [])
        rng.shuffle(pages)
        seen, picked = set(), []
        with ThreadPoolExecutor(max_workers=8) as ex:
            for p in ex.map(vet, pages[:want * 3]):
                if p and p["title"] not in seen and len(picked) < want:  # several copies of a book: one plate once
                    seen.add(p["title"])
                    picked.append(p)
        pool += picked
        print(f"  {tid} {titles.get(tid, {}).get('ShortTitle', '?')[:40]}: {len(pages)} plates, kept {len(picked)}",
              flush=True)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} BHL plates -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
