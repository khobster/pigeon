"""Build heist/nga_pool.json from the National Gallery of Art open-access CSVs.

Run from any machine (the data lives on GitHub, which isn't IP-blocked):
    python tools/build_nga_pool.py

Joins published_images.csv (image uuids + IIIF urls) to objects.csv (metadata)
on published_images.depictstmsobjectid == objects.objectid, keeps open-access
(CC0) rows with a primary image, prefers paintings, and samples a capped pool so
the committed JSON stays small. NGA images serve from media.nga.gov (reachable
from CI); the build's verified() re-checks and self-hosts each one at send time.
"""
import csv
import io
import json
import random
import tempfile
from pathlib import Path

import requests

RAW = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/"
OUT = Path(__file__).resolve().parent.parent / "heist" / "nga_pool.json"
CAP = 6000
UA = {"User-Agent": "Mozilla/5.0 (nga-pool-builder)"}


def download(name, dest):
    print(f"downloading {name} ...")
    with requests.get(RAW + name, timeout=600, headers=UA, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="nga-"))
    objs_csv, imgs_csv = tmp / "objects.csv", tmp / "published_images.csv"
    download("objects.csv", objs_csv)
    download("published_images.csv", imgs_csv)

    # keep only the fields we need, to hold the object table in memory cheaply
    objs = {}
    with open(objs_csv, newline="", encoding="utf-8") as f:
        for o in csv.DictReader(f):
            objs[o["objectid"]] = (
                o.get("title", ""), o.get("attribution", ""),
                o.get("displaydate", ""), o.get("medium", ""),
                (o.get("classification", "") or "").lower(),
            )
    print(f"  {len(objs)} objects")

    seen, pool = set(), []
    with open(imgs_csv, newline="", encoding="utf-8") as f:
        for p in csv.DictReader(f):
            if p.get("openaccess") != "1" or not p.get("iiifurl"):
                continue
            if p.get("viewtype") != "primary":  # skip detail crops / alt views
                continue
            oid = p.get("depictstmsobjectid")
            o = objs.get(oid)
            if not o or not o[0] or oid in seen:
                continue
            seen.add(oid)
            title, attribution, displaydate, medium, classification = o
            pool.append({
                "museum": "National Gallery of Art, Washington",
                "title": title,
                "artist": attribution or "Unknown",
                "year": displaydate,
                "medium": medium,
                "image": p["iiifurl"].rstrip("/") + "/full/!880,880/0/default.jpg",
                "url": "https://www.nga.gov/artworks/" + oid,
                "_paint": "painting" in classification,
            })
    print(f"  {len(pool)} open-access primary images")

    paintings = [x for x in pool if x["_paint"]]
    rest = [x for x in pool if not x["_paint"]]
    random.seed(0)
    random.shuffle(paintings)
    random.shuffle(rest)
    chosen = (paintings + rest)[:CAP]  # paintings first, then fill with other color media
    for x in chosen:
        x.pop("_paint", None)
    OUT.write_text(json.dumps(chosen, indent=0))
    print(f"wrote {len(chosen)} items ({len(paintings)} paintings available) to {OUT}")


if __name__ == "__main__":
    main()
