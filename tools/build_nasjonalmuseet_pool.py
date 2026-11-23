"""Curate the Nasjonalmuseet (Oslo) pool: Munch, Dahl, Gude, Thaulow,
Kittelsen, Astrup, via Wikidata and Commons.

The museum's own site sits behind Cloudflare, which blocks a script after a
few dozen requests, so we never touch it at build time. Wikidata catalogs
its paintings (collection = Nasjonalmuseet, instance of painting, with a
Commons image) with each maker's death date; we keep artists who died before
1956 and works dated 1930 or earlier. Images serve from upload.wikimedia.org;
the link goes to the museum's own object page by inventory number.

    python tools/build_nasjonalmuseet_pool.py heist/nasjonalmuseet_pool.json
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
 ?item wdt:P195 wd:Q1132918; wdt:P31 wd:Q3305213; wdt:P18 ?img; wdt:P170 ?a.
 ?a wdt:P570 ?dod. FILTER(YEAR(?dod) < 1956)
 OPTIONAL { ?item wdt:P571 ?inc }
 OPTIONAL { ?item p:P217 [ ps:P217 ?inv; pq:P195 wd:Q1132918 ] }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en,nb,no,nn". } }"""
PAGE = "https://www.nasjonalmuseet.no/en/collection/object/{inv}"
LATEST = 1930
PER_ARTIST = 8
# the crown jewels skip the per-artist cap (they still have to pass every check)
MUST = {"NG.M.00939", "NG.M.00844", "NG.M.00839"}  # The Scream, The Girls on the Bridge, The Sick Child
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
        "museum": "Nasjonalmuseet, Oslo",
        "title": title,
        "artist": "Unknown" if re.fullmatch(r"Q\d+", row["aLabel"]) else row["aLabel"],
        "year": year,
        "medium": "",
        "image": image,
        "url": PAGE.format(inv=quote(inv)) if inv else row["item"],
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_nasjonalmuseet_pool.py <out.json>")
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
    got = [p for p in got if sides.get(p["image"], 0) >= 1600]  # sharp originals only
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
    print(f"wrote {len(pool)} Nasjonalmuseet works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
