"""Curate the Nationalmuseum (Stockholm) pool, via Wikidata and Commons.

Nationalmuseum's own image server is capped near 1200px and refuses
hot-linking, but the museum donated its public-domain paintings to Wikimedia
Commons at full resolution. Wikidata lists them (collection = Nationalmuseum,
instance of painting, with an image) along with the maker's death date, so we
keep only artists who died before 1956. Images serve from upload.wikimedia.org
(Special:FilePath?width=1600 redirects there), which never blocks the runner.
The color check runs on a small render through wsrv.nl, because Wikimedia
rate-limits a laptop that pulls hundreds of thumbnails in a row.

    python tools/build_nationalmuseum_pool.py heist/nationalmuseum_pool.json
"""
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, unquote

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402
from tools.commons_size import long_sides  # noqa: E402

WDQS = "https://query.wikidata.org/sparql"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}
QUERY = """SELECT ?item ?itemLabel ?aLabel ?inc ?img WHERE {
 ?item wdt:P195 wd:Q842858; wdt:P31 wd:Q3305213; wdt:P18 ?img; wdt:P170 ?a.
 ?a wdt:P570 ?dod. FILTER(YEAR(?dod) < 1956)
 OPTIONAL { ?item wdt:P571 ?inc }
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en,sv". } }"""
TRY = 1500
LATEST = 1930  # the heist's copyright line
PER_ARTIST = 8
SEED = 20261123


def vet(row):
    title = row["itemLabel"]
    if re.fullmatch(r"Q\d+", title) or not secular(title) or not inoffensive(title):
        return None
    image = row["img"].replace("http://", "https://") + "?width=1600"
    try:
        t = requests.get(f"https://wsrv.nl/?url={quote(image, safe='')}&w=240&fit=inside&we",
                         headers={"User-Agent": "Mozilla/5.0 Chrome/130"}, timeout=60)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    year = (row.get("inc") or "")[:4]
    if not re.fullmatch(r"\d{4}", year):
        year = ""  # Wikidata's "unknown value" comes back as a blank-node url
    if year and int(year) > LATEST:
        return None
    file = unquote(row["img"].rsplit("/", 1)[-1])
    oid = re.search(r"Nationalmuseum - (\d+)\.", file)
    return {
        "museum": "Nationalmuseum, Stockholm",
        "title": title,
        "artist": "Unknown" if re.fullmatch(r"Q\d+", row["aLabel"]) else row["aLabel"],
        "year": year,
        "medium": "",
        "image": image,
        "url": (f"https://collection.nationalmuseum.se/en/collection/item/{oid.group(1)}/" if oid
                else row["item"]),
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_nationalmuseum_pool.py <out.json>")
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
        got = [p for p in ex.map(vet, rows[:TRY]) if p]
    sides = long_sides([p["image"] for p in got])
    got = [p for p in got if sides.get(p["image"], 0) >= 1600]  # sharp originals only
    pool, per = [], {}
    for p in got:
        if per.get(p["artist"], 0) >= PER_ARTIST:
            continue
        per[p["artist"]] = per.get(p["artist"], 0) + 1
        pool.append(p)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"  vetted {min(TRY, len(rows))}, kept {len(pool)}")
    print(f"wrote {len(pool)} Nationalmuseum works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
