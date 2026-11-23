"""Curate the Minneapolis Institute of Art (Mia) pool: Hokusai, Hiroshige,
Japanese screens and scrolls, Chinese and Indian painting, plus its European
and American pictures.

Mia's search (search.artsmia.org, open Elasticsearch) lists public-domain
works, which Mia says are "available for any use". Images come off its
img.artsmia.org CDN, which only has 400px, 800px and the full original, so
we store the original and let wsrv.nl shrink it. wsrv refuses anything over
71 megapixels, so we cap the size; and the color check renders the small
thumbnail through wsrv with the same 20s timeout the nightly build uses, so
a work only gets in if it loads fast enough to be used.

    python tools/build_mia_pool.py heist/mia_pool.json
"""
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, resized, secular  # noqa: E402

SEARCH = "https://search.artsmia.org/"
CDN = "https://img.artsmia.org/web_objects_cache/{loc}/{rend}_full.jpg"
HEAD = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130.0 Safari/537.36"}
BASE = 'rights_type:"Public Domain" AND image:valid AND public_access:1'
# query -> how many candidates to vet
SEAMS = {
    'department:"Asian Art" AND classification:Prints': 700,
    'department:"Asian Art" AND classification:Paintings': 600,
    'department:"European Art" AND classification:Paintings': 450,
    'department:"Arts of the Americas" AND classification:Paintings': 250,
    'department:"European Art" AND classification:Prints': 200,
}
MAX_PIXELS = 60_000_000
CJK = re.compile(r"\s*[\u3000-\u9fff\uf900-\ufaff]+.*$")  # "Buncho 一筆齊文調" -> "Buncho"
PLACES = {"Japan", "China", "India", "Korea", "Iran", "Tibet", "Nepal", "Thailand", "Unknown artist"}
PER_ARTIST = 8
SEED = 20261123


def search(q):
    r = requests.get(SEARCH + quote(f"{BASE} AND {q}") + "?size=10000", headers=HEAD, timeout=180)
    return [h["_source"] for h in r.json()["hits"]["hits"]]


def candidate(h):
    w, ht = h.get("image_width") or 0, h.get("image_height") or 0
    if max(w, ht) < 1600 or w * ht > MAX_PIXELS:
        return None
    if not h.get("Cache_Location") or not h.get("Primary_RenditionNumber"):
        return None
    artist = (h.get("artist") or "").split(";")[0].strip()
    for role in ("Artist: ", "Designer: ", "Maker: ", "Publisher: "):
        artist = artist.replace(role, "")
    artist = CJK.sub("", artist).strip()
    if artist in PLACES:  # Mia credits anonymous work to its country
        artist = ""
    return {
        "museum": "the Minneapolis Institute of Art",
        "title": (h.get("title") or "Untitled").strip(),
        "artist": artist or "Unknown",
        "year": (h.get("dated") or "")[:40],
        "medium": "",
        "image": CDN.format(loc=h["Cache_Location"].replace("\\", "/"),
                            rend=h["Primary_RenditionNumber"].rsplit(".", 1)[0]),
        "url": f"https://collections.artsmia.org/art/{h['id']}",
    }


def vet(p):
    if not secular(p["title"]) or not inoffensive(p["title"]):
        return None
    try:
        t = requests.get(resized(p["image"], 240), headers=HEAD, timeout=20)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return p


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_mia_pool.py <out.json>")
    rng = random.Random(SEED)
    pool, per, seen = [], {}, set()
    for q, n in SEAMS.items():
        found = [c for c in map(candidate, search(q)) if c and c["url"] not in seen]
        rng.shuffle(found)
        with ThreadPoolExecutor(max_workers=6) as ex:
            got = [p for p in ex.map(vet, found[:n]) if p]
        kept = 0
        for p in got:
            if p["artist"] not in ("Unknown",) and per.get(p["artist"], 0) >= PER_ARTIST:
                continue
            per[p["artist"]] = per.get(p["artist"], 0) + 1
            seen.add(p["url"])
            pool.append(p)
            kept += 1
        print(f"  {q}: {len(found)} eligible, vetted {min(n, len(found))}, kept {kept}", flush=True)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} Mia works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
