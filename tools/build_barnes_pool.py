"""Curate the Barnes Foundation pool.

The Barnes (Philadelphia) marks its public-domain works with a Public Domain
Mark and serves their images from a CloudFront bucket. Its collection site
runs on an open Elasticsearch search endpoint that takes a raw query body, so
one request returns every object that has an image. The whole collection is
only ~3,000 imaged objects, so we keep the public-domain pictures (paintings,
drawings, works on paper, textiles), skip the Barnes's famous wall of
wrought-iron hardware, and write heist/barnes_pool.json.

    python tools/build_barnes_pool.py heist/barnes_pool.json
"""
import json
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
API = "https://collection.barnesfoundation.org/api/search"
IMAGES = "https://d2r83x5xt28klo.cloudfront.net"
# objRightsTypeId codes the collection site labels "Public Domain".
PUBLIC_DOMAIN = {"4", "7", "8", "10"}
KEEP = {"Paintings", "Drawings", "Works on Paper", "Prints", "Textiles", "Manuscripts"}
# Renoir alone is ~180 of the Barnes's public-domain pictures; cap each artist
# so the pool reads like the whole collection, not one painter's room.
PER_ARTIST = 20
FIELDS = ["id", "title", "people", "displayDate", "medium", "classification",
          "objRightsTypeId", "imageSecret"]


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_barnes_pool.py <out.json>")
    body = {"from": 0, "size": 10000, "_source": FIELDS,
            "query": {"bool": {"filter": [{"exists": {"field": "imageSecret"}}]}}}
    r = requests.get(API, params={"body": json.dumps(body)}, headers=UA, timeout=120)
    r.raise_for_status()
    pool, per_artist = [], {}
    for hit in r.json()["hits"]["hits"]:
        o = hit["_source"]
        if o.get("objRightsTypeId") not in PUBLIC_DOMAIN:
            continue
        if o.get("classification") not in KEEP or not o.get("title"):
            continue
        artist = (o.get("people") or "").strip()
        if artist and not artist.startswith("Unidentified"):
            if per_artist.get(artist, 0) >= PER_ARTIST:
                continue
            per_artist[artist] = per_artist.get(artist, 0) + 1
        pool.append({
            "museum": "the Barnes Foundation",
            "title": o["title"].strip(),
            "artist": "Unknown" if not artist or artist.startswith("Unidentified") else artist,
            "year": o.get("displayDate") or "",
            "medium": o.get("medium") or "",
            "image": f"{IMAGES}/{o['id']}_{o['imageSecret']}_b.jpg",
            "url": f"https://collection.barnesfoundation.org/objects/{o['id']}",
        })
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} public-domain Barnes works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
