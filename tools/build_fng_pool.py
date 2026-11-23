"""Curate the Finnish National Gallery pool (Ateneum, Kiasma, Sinebrychoff).

The gallery publishes its entire collection as one unauthenticated JSON
download (89k objects), with CC0 images at up to 4000px. We keep CC0 works
whose every maker died before 1956 (belt and braces on copyright), with an
image at least 1600px on the long side, in color, secular, inoffensive, and
cap each artist so Schjerfbeck doesn't take over.

    python tools/build_fng_pool.py heist/fng_pool.json
"""
import gzip
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

API = "https://kokoelma.kansallisgalleria.fi/api/v1/objects"
SITE = "https://kokoelma.kansallisgalleria.fi"
HEAD = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130.0 Safari/537.36"}
DEATH_BEFORE = 1956
LATEST = 1930  # the heist's copyright line: nothing made after 1930
ELDER = re.compile(r"\s+\S+ / \S+ \S+ / (the \w+)$")  # "X vanhempi / den äldre / the Elder" -> "X the Elder"
# classification -> how many candidates to vet
SEAMS = {"painting": 1400, "Japanese woodblock print": 550, "drawing": 500, "graphic arts": 500}
PER_ARTIST = 8
SEED = 20261123


def text(d):
    return (d or {}).get("en") or (d or {}).get("fi") or (d or {}).get("sv") or ""


def candidate(o):
    media = [m for m in o.get("multimedia") or [] if m.get("license") == "CC0" and m.get("jpg")]
    if not media or max(media[0].get("width") or 0, media[0].get("height") or 0) < 1600:
        return None
    people = o.get("people") or []
    if any((p.get("deathYear") or 0) >= DEATH_BEFORE for p in people):
        return None
    makers = [p for p in people if "artist" in text(p.get("role")).lower()] or people
    artist = " ".join(x for x in (makers[0].get("firstName"), makers[0].get("familyName")) if x) if makers else ""
    artist = ELDER.sub(r" \1", artist)
    y0, y1 = o.get("yearFrom"), o.get("yearTo")
    if not y0 or (y1 or y0) > LATEST:
        return None
    year = str(y0) if y0 and (not y1 or y1 == y0) else (f"{y0} to {y1}" if y0 else "")
    sizes = media[0]["jpg"]
    return {
        "museum": "the Finnish National Gallery",
        "title": text(o.get("title")) or "Untitled",
        "artist": artist or "Unknown",
        "year": year,
        "medium": "",
        "image": SITE + (sizes.get("2000") or sizes.get("1000")),
        "thumb": SITE + (sizes.get("300") or sizes.get("500") or sizes.get("1000")),
        "url": f"{SITE}/en/object/{o['objectId']}",
    }


def vet(p):
    if not secular(p["title"]) or not inoffensive(p["title"]):
        return None
    try:
        r = requests.get(p.pop("thumb"), headers=HEAD, timeout=40)
        if not r.headers.get("content-type", "").startswith("image/") or not is_color(r.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return p


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_fng_pool.py <out.json>")
    raw = requests.get(API, headers={**HEAD, "Accept-Encoding": "gzip"}, timeout=600).content
    try:
        objects = json.loads(raw)
    except ValueError:
        objects = json.loads(gzip.decompress(raw))
    print(f"  {len(objects)} objects in the catalog", flush=True)
    rng = random.Random(SEED)
    pool, per = [], {}
    for kind, n in SEAMS.items():
        found = []
        for o in objects:
            if kind in [text(c) for c in o.get("classifications") or []]:
                c = candidate(o)
                if c:
                    found.append(c)
        rng.shuffle(found)
        with ThreadPoolExecutor(max_workers=8) as ex:
            got = [p for p in ex.map(vet, found[:n]) if p]
        kept = 0
        for p in got:
            if p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST:
                continue
            per[p["artist"]] = per.get(p["artist"], 0) + 1
            pool.append(p)
            kept += 1
        print(f"  {kind}: {len(found)} eligible, vetted {min(n, len(found))}, kept {kept}", flush=True)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} Finnish National Gallery works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
