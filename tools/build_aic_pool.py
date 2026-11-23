"""Curate the Art Institute of Chicago pool: Seurat, Monet, Caillebotte,
Cassatt, Hokusai and Hiroshige, Toulouse-Lautrec.

AIC's API (CC0 data) blocks the GitHub runner, so we list public-domain works
from a laptop instead and commit the pool; the nightly build then only needs
AIC's IIIF image host. That host refuses the wsrv proxy, so the build fetches
these images directly (see DIRECT_HOSTS in build_issue). The largest open
size is 1686px wide, so we keep originals at least that wide. AIC asks for
no more than about one request a second, so this runs slowly.

    python tools/build_aic_pool.py heist/aic_pool.json
"""
import json
import os
import random
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

SEARCH = "https://api.artic.edu/api/v1/artworks/search"
IIIF = "https://www.artic.edu/iiif/2/{id}/full/{w},/0/default.jpg"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)",
        "AIC-User-Agent": "the-heist-newsletter (kevin.murawinski@gmail.com)"}
FIELDS = ["id", "title", "artist_title", "date_display", "date_end", "image_id", "thumbnail"]
# (department, classification) -> how many candidates to vet
SEAMS = {
    ("Painting and Sculpture of Europe", "painting"): 450,
    ("Arts of Asia", "print"): 400,
    ("Arts of the Americas", "painting"): 300,
    ("Prints and Drawings", "print"): 250,
    ("Arts of Asia", "painting"): 150,
}
LATEST = 1930
PER_ARTIST = 8
# the icons skip the per-artist cap and the sampling (they still pass every check):
# Grande Jatte, Paris Street; Rainy Day, The Bedroom, Van Gogh self-portrait,
# The Great Wave, Water Lilies, The Child's Bath, Two Sisters, At the Moulin Rouge,
# Stacks of Wheat (End of Summer)
MUST = [27992, 20684, 28560, 80607, 24645, 16568, 111442, 14655, 61128, 64818]
SEED = 20261123


def search(dept, kind):
    must = [{"term": {"is_public_domain": True}}, {"exists": {"field": "image_id"}},
            {"term": {"department_title.keyword": dept}}, {"match": {"classification_titles": kind}},
            {"range": {"date_end": {"lte": LATEST}}}]
    out = []
    for page in range(1, 11):  # the API caps a query at 1,000 results
        r = requests.post(SEARCH, headers=HEAD, timeout=60, json={
            "query": {"bool": {"must": must}}, "fields": FIELDS, "limit": 100, "page": page})
        data = r.json().get("data") or []
        out += data
        time.sleep(1)
        if len(data) < 100:
            break
    return out


def vet(a):
    title = (a.get("title") or "Untitled").strip()
    if not secular(title) or not inoffensive(title):
        return None
    try:
        t = requests.get(IIIF.format(id=a["image_id"], w=843), headers=HEAD, timeout=60)
        time.sleep(1)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return {
        "museum": "the Art Institute of Chicago",
        "title": title,
        "artist": "Unknown" if (a.get("artist_title") or "").lower() in ("", "artist unknown") else a["artist_title"],
        "year": (a.get("date_display") or "")[:40],
        "medium": "",
        "image": IIIF.format(id=a["image_id"], w=1686),
        "url": f"https://www.artic.edu/artworks/{a['id']}",
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_aic_pool.py <out.json>")
    rng = random.Random(SEED)
    pool, per, seen = [], {}, set()
    for (dept, kind), n in SEAMS.items():
        found = [a for a in search(dept, kind)
                 if (a.get("thumbnail") or {}).get("width", 0) >= 1686 and a["id"] not in seen]
        rng.shuffle(found)
        kept = 0
        for a in found[:n]:
            p = vet(a)
            if not p or (p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST):
                continue
            per[p["artist"]] = per.get(p["artist"], 0) + 1
            seen.add(a["id"])
            pool.append(p)
            kept += 1
        print(f"  {dept} / {kind}: {len(found)} eligible, vetted {min(n, len(found))}, kept {kept}", flush=True)
    r = requests.get(SEARCH.rsplit("/", 1)[0], headers=HEAD, timeout=60,
                     params={"ids": ",".join(map(str, MUST)), "fields": ",".join(FIELDS + ["is_public_domain"])})
    for a in r.json().get("data") or []:
        ok = a.get("is_public_domain") and a.get("image_id") and a["id"] not in seen
        p = vet(a) if ok else None
        if p:
            seen.add(a["id"])
            pool.append(p)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} Art Institute works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
