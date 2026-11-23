"""Curate a pool for a museum whose own site blocks scripts but whose
public-domain pictures are on Wikimedia Commons and cataloged on Wikidata.

Wikidata gives each work's collection, type, maker (with death date),
inception and the museum's own object id; Commons serves the images from
upload.wikimedia.org, which never blocks the runner. A work is in the public
domain for us if every maker died before 1956, or, with no maker death date
known, it was made before 1850; and it must be dated 1930 or earlier. Then:
an original at least MIN_SIDE px, in color, secular, inoffensive, capped per
artist.

    python tools/build_wikidata_pool.py nasjonalmuseet heist/nasjonalmuseet_pool.json
    python tools/build_wikidata_pool.py brooklyn heist/brooklyn_pool.json
    python tools/build_wikidata_pool.py birmingham heist/birmingham_pool.json
    python tools/build_wikidata_pool.py walters heist/walters_pool.json
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
PAINTING, WATERCOLOR, DRAWING, PRINT = "wd:Q3305213", "wd:Q18761202", "wd:Q93184", "wd:Q11060274"

MUSEUMS = {
    # The site's Cloudflare blocks a script after a few dozen requests.
    "nasjonalmuseet": {
        "museum": "Nasjonalmuseet, Oslo",
        "collections": ["wd:Q1132918"],
        "types": [PAINTING],
        "ref": "?item p:P217 [ ps:P217 ?ref; pq:P195 wd:Q1132918 ]",  # inventory number
        "page": "https://www.nasjonalmuseet.no/en/collection/object/{ref}",
        "languages": "en,nb,no,nn",
        # the crown jewels skip the per-artist cap (they still pass every check):
        # The Scream, The Girls on the Bridge, The Sick Child
        "must": {"NG.M.00939", "NG.M.00844", "NG.M.00839"},
    },
    # Site and API behind a bot checkpoint; Brooklyn uploaded its paintings to
    # Commons. Its better uploads are 1536px web masters, still sharper than the
    # 1120px the email shows; the older 400-800px scans stay out.
    "brooklyn": {
        "museum": "the Brooklyn Museum",
        "collections": ["wd:Q632682"],
        "types": [PAINTING],
        "ref": "?item wdt:P4740 ?ref",
        "page": "https://www.brooklynmuseum.org/objects/{ref}",
        "min_side": 1200,
    },
    # Pre-Raphaelites (Burne-Jones, Rossetti, Millais, Ford Madox Brown). The
    # museum's object pages are gone, so the link searches its open image bank
    # by accession number.
    "birmingham": {
        "museum": "Birmingham Museum and Art Gallery",
        "collections": ["wd:Q1799857", "wd:Q4916759"],
        "types": [PAINTING, WATERCOLOR, DRAWING, PRINT],
        "ref": "?item wdt:P217 ?ref",
        "page": ("https://dams.birminghammuseums.org.uk/assetbank-birminghammuseums/action/search"
                 "?keywords={ref}&quickSearch=true&newSearch=true"),
        "min_side": 1200,
    },
    # The Walters gave ~19,000 high-resolution images to Commons in 2011; its
    # own site blocks scripts.
    "walters": {
        "museum": "the Walters Art Museum",
        "collections": ["wd:Q210081"],
        "types": [PAINTING, WATERCOLOR, DRAWING, PRINT],
        "ref": "?item wdt:P4713 ?ref",
        "page": "https://art.thewalters.org/detail/{ref}/",
    },
}
LATEST = 1930
DEATH_BEFORE = 1956
OLD_ENOUGH = 1850  # no maker death date known: made before this is safe
PER_ARTIST = 8
SEED = 20261123
YEAR = re.compile(r"\d{4}")


def query(cfg):
    return f"""SELECT ?item ?itemLabel ?aLabel ?dod ?inc ?img ?ref WHERE {{
 VALUES ?c {{ {" ".join(cfg["collections"])} }}
 VALUES ?type {{ {" ".join(cfg["types"])} }}
 ?item wdt:P195 ?c; wdt:P31 ?type; wdt:P18 ?img.
 OPTIONAL {{ ?item wdt:P170 ?a. OPTIONAL {{ ?a wdt:P570 ?dod }} }}
 OPTIONAL {{ ?item wdt:P571 ?inc }}
 OPTIONAL {{ {cfg["ref"]} }}
 SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{cfg.get("languages", "en")}". }} }}"""


def year_of(value):
    """'1893-01-01T00:00:00Z' -> 1893; Wikidata's 'unknown value' is a url -> None."""
    m = YEAR.match(value or "")
    return int(m.group()) if m else None


def works(cfg):
    """One dict per Wikidata item, with every maker's death year gathered."""
    r = requests.get(WDQS, params={"query": query(cfg), "format": "json"}, headers=HEAD, timeout=300)
    items = {}
    for b in r.json()["results"]["bindings"]:
        row = {k: v["value"] for k, v in b.items()}
        w = items.setdefault(row["item"], {**row, "deaths": set(), "makers": set()})
        if row.get("aLabel"):
            w["makers"].add(row["aLabel"])
            w["deaths"].add(year_of(row.get("dod")))
        if row.get("ref") and not w.get("ref"):
            w["ref"] = row["ref"]
    return list(items.values())


def free(w):
    made = year_of(w.get("inc"))
    if made and made > LATEST:
        return False
    deaths = w["deaths"]
    if deaths and None not in deaths:
        return max(deaths) < DEATH_BEFORE
    return bool(made) and made < OLD_ENOUGH


def vet(w, cfg):
    title = w["itemLabel"]
    if re.fullmatch(r"Q\d+", title) or not secular(title) or not inoffensive(title):
        return None
    if not free(w):
        return None
    image = w["img"].replace("http://", "https://") + "?width=1600"
    try:
        t = requests.get(f"https://wsrv.nl/?url={quote(image, safe='')}&w=240&fit=inside&we",
                         headers={"User-Agent": "Mozilla/5.0 Chrome/130"}, timeout=60)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    makers = sorted(m for m in w["makers"] if not re.fullmatch(r"Q\d+", m))
    made = year_of(w.get("inc"))
    ref = w.get("ref")
    return {
        "museum": cfg["museum"],
        "title": title,
        "artist": makers[0] if len(makers) == 1 else ("Unknown" if not makers else makers[0]),
        "year": str(made) if made else "",
        "medium": "",
        "image": image,
        "url": cfg["page"].format(ref=quote(ref)) if ref else w["item"],
        "ref": ref or "",
    }


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in MUSEUMS:
        sys.exit(f"usage: build_wikidata_pool.py <{'|'.join(MUSEUMS)}> <out.json>")
    cfg = MUSEUMS[sys.argv[1]]
    rows = works(cfg)
    print(f"  {len(rows)} works on Wikidata", flush=True)
    random.Random(SEED).shuffle(rows)
    with ThreadPoolExecutor(max_workers=6) as ex:
        got = [p for p in ex.map(lambda w: vet(w, cfg), rows) if p]
    sides = long_sides([p["image"] for p in got])
    got = [p for p in got if sides.get(p["image"], 0) >= cfg.get("min_side", 1600)]
    must = cfg.get("must", set())
    got.sort(key=lambda p: p["ref"] not in must)  # jewels first, outside the cap
    pool, per = [], {}
    for p in got:
        ref = p.pop("ref")
        if ref not in must:
            if p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST:
                continue
            per[p["artist"]] = per.get(p["artist"], 0) + 1
        pool.append(p)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[2], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"  vetted {len(rows)}, kept {len(got)}, after artist cap {len(pool)}")
    print(f"wrote {len(pool)} {cfg['museum']} works -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
