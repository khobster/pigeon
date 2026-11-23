"""Curate the J. Paul Getty Museum pool.

The Getty's Open Content Program releases its public-domain images as CC0 at
full resolution (Irises is 9021px wide), and its whole collection is open
linked data. We list objects by classification over the SPARQL endpoint,
fetch each object's Linked Art record (title, maker, date, homepage, image)
and its IIIF manifest (the image license lives there: CC0 or skip), then
vet: secular, inoffensive, in color. Photographs are skipped (mostly
black-and-white); the paintings, illuminated manuscripts, drawings and
decorative arts are the seams worth stealing from.

    python tools/build_getty_pool.py heist/getty_pool.json
"""
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

SPARQL = "https://data.getty.edu/museum/collection/sparql"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
CC0 = "http://creativecommons.org/publicdomain/zero/1.0/"
AAT = "http://vocab.getty.edu/aat/"
# classification -> how many to try for (most get vetted out: religious
# subjects, black-and-white, no open image)
SEAMS = {
    "300033618": 1046,  # Paintings: try them all
    "300265483": 1400,  # Manuscripts (illuminated leaves)
    "300033973": 600,   # Drawings
    "300411641": 500,   # Decorative Arts
    "300047090": 250,   # Sculpture
    "300209286": 150,   # Jewelry
}
PER_ARTIST = 6
SHELFMARK = re.compile(r"\s*\((?:Ms|MS)\.?\s.*$")
SEED = 20261123


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers={**HEAD, **kw.pop("headers", {})}, timeout=60, **kw)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return None


def objects(aat):
    q = f"""PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
SELECT DISTINCT ?obj WHERE {{ ?obj a crm:E22_Human-Made_Object ; crm:P2_has_type <{AAT}{aat}> . }}"""
    r = get(SPARQL, params={"query": q}, headers={"Accept": "application/sparql-results+json"})
    return [b["obj"]["value"] for b in r.json()["results"]["bindings"]] if r else []


def labels(items):
    return [i.get("_label", "") for i in items or []]


def record(uri):
    r = get(uri, headers={"Accept": "application/ld+json"})
    if not r:
        return None
    d = r.json()
    reps = d.get("representation") or []
    if not reps:
        return None
    image = reps[0]["id"]  # .../iiif/image/<id>/full/full/0/default.jpg
    manifest = next((s.get("id") for s in d.get("subject_of") or []
                     if "IIIF Manifest" in labels(s.get("classified_as"))), None)
    page = next((s.get("id") for s in d.get("subject_of") or []
                 if "Web Page" in labels(s.get("classified_as")) and "Primary" in labels(s.get("classified_as"))), None)
    if not manifest or not page:
        return None
    m = get(manifest.replace("/manifest/2/", "/manifest/3/"))
    if not m or m.json().get("rights") != CC0:
        return None
    prod = d.get("produced_by") or {}
    makers = [c.get("_label", "") for c in prod.get("carried_out_by") or []]
    for part in prod.get("part") or []:
        makers += [c.get("_label", "") for c in part.get("carried_out_by") or []]
    span = (prod.get("timespan") or {}).get("identified_by") or [{}]
    title = re.sub(r"\s*\([^)]*\)\s*$", "", d.get("_label", "")).strip()  # drop "(90.PA.20)"
    title = title.strip("[]")
    title = SHELFMARK.sub("", title).strip()  # "Goats (Ms. 100 (2007.16), fol. 14v)" -> "Goats"
    return {
        "museum": "the Getty",
        "title": title or "Untitled",
        "artist": makers[0] if len(makers) == 1 else ("Unknown" if not makers else makers[0]),
        "year": (span[0].get("content") or "")[:40],
        "medium": "",
        "image": image.replace("/full/full/", "/full/!1600,1600/"),
        "url": page,
    }


def vet(uri):
    try:
        p = record(uri)
    except Exception:  # noqa: BLE001
        return None
    if not p or not secular(p["title"]) or not inoffensive(p["title"]):
        return None
    t = get(p["image"].replace("/full/!1600,1600/", "/full/!240,240/"))
    if not t or not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
        return None
    return p


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_getty_pool.py <out.json>")
    rng = random.Random(SEED)
    pool, per = [], {}
    for aat, n in SEAMS.items():
        uris = objects(aat)
        rng.shuffle(uris)
        with ThreadPoolExecutor(max_workers=8) as ex:
            got = [p for p in ex.map(vet, uris[:n]) if p]
        kept = 0
        for p in got:
            who = p["artist"]
            if who != "Unknown" and per.get(who, 0) >= PER_ARTIST:
                continue
            per[who] = per.get(who, 0) + 1
            pool.append(p)
            kept += 1
        print(f"  {aat}: {len(uris)} listed, tried {min(n, len(uris))}, kept {kept}", flush=True)
    seen, out = set(), []
    for p in pool:
        if p["url"] not in seen:
            seen.add(p["url"])
            out.append(p)
    out.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(out, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(out)} Getty works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
