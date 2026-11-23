"""Curate the Brooklyn Museum pool via Wikidata and Commons.

Brooklyn's site and API now sit behind a bot checkpoint (and the old API
host is gone), but Brooklyn put its public-domain paintings on Wikimedia
Commons and Wikidata catalogs them with the museum's own object id, so the
link still goes to brooklynmuseum.org. Makers dead before 1956, works dated
1930 or earlier, originals at least 1200px.

    python tools/build_brooklyn_pool.py heist/brooklyn_pool.json
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

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402
from tools.commons_size import long_sides  # noqa: E402

WDQS = "https://query.wikidata.org/sparql"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}
QUERY = """SELECT ?item ?itemLabel ?aLabel ?inc ?img ?inv WHERE {
 ?item wdt:P195 wd:Q632682; wdt:P31 wd:Q3305213; wdt:P18 ?img; wdt:P170 ?a.
 ?a wdt:P570 ?dod. FILTER(YEAR(?dod) < 1956)
 OPTIONAL { ?item wdt:P571 ?inc }
 OPTIONAL { ?item wdt:P4740 ?inv }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
PAGE = "https://www.brooklynmuseum.org/objects/{inv}"
LATEST = 1930
PER_ARTIST = 8
# Brooklyn's better Commons uploads are its 1536px web masters, still sharper
# than the 1120px the email shows; its older 400-800px scans stay out
MIN_SIDE = 1200
MUST = set()  # object ids that skip the per-artist cap
SEED = 20261123


def vet(row):
    title = row["itemLabel"]
    if re.fullmatch(r"Q\d+", title) or not secular(title) or not inoffensive(title):
        return None
    year = (row.get("inc") or "")[:4]
    if not re.fullmatch(r"\d{4}", year):
        year = ""  # Wikidata's "unknown value" comes back as a blank-node url
    if year and int(year) > LATEST:
        return None
    image = row["img"].replace("http://", "https://") + "?width=1600"
    try:
        t = requests.get(f"https://wsrv.nl/?url={quote(image, safe='')}&w=240&fit=inside&we",
                         headers={"User-Agent": "Mozilla/5.0 Chrome/130"}, timeout=60)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    inv = row.get("inv")
    return {
        "museum": "the Brooklyn Museum",
        "title": title,
        "artist": "Unknown" if re.fullmatch(r"Q\d+", row["aLabel"]) else row["aLabel"],
        "year": year,
        "medium": "",
        "image": image,
        "url": PAGE.format(inv=quote(inv)) if inv else row["item"],
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_brooklyn_pool.py <out.json>")
    r = requests.get(WDQS, params={"query": QUERY, "format": "json"}, headers=HEAD, timeout=300)
    rows, seen = [], set()
    for b in r.json()["results"]["bindings"]:
        row = {k: v["value"] for k, v in b.items()}
        if row["item"] not in seen:  # one row per painting (multiple makers/dates)
            seen.add(row["item"])
            rows.append(row)
    print(f"  {len(rows)} paintings on Wikidata", flush=True)
    random.Random(SEED).shuffle(rows)
    with ThreadPoolExecutor(max_workers=6) as ex:
        got = [p for p in ex.map(vet, rows) if p]
    sides = long_sides([p["image"] for p in got])
    got = [p for p in got if sides.get(p["image"], 0) >= MIN_SIDE]  # sharp originals only
    pool, per = [], {}
    got.sort(key=lambda p: p["url"].rsplit("/", 1)[-1] not in MUST)  # jewels first, outside the cap
    for p in got:
        if p["url"].rsplit("/", 1)[-1] in MUST:
            pool.append(p)
            continue
        if p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST:
            continue
        per[p["artist"]] = per.get(p["artist"], 0) + 1
        pool.append(p)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"  vetted {len(rows)}, kept {len(got)}, after artist cap {len(pool)}")
    print(f"wrote {len(pool)} Brooklyn Museum works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
