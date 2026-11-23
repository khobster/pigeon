"""Curate the Yale pool: the Yale Center for British Art and the Yale
University Art Gallery (Turner, Constable, Stubbs, Blake, Van Gogh's Night
Cafe, Homer).

Yale's LUX search sits behind a bot challenge, so we skip it and read the
IIIF manifests directly, which are open:
  YCBA: sweep object ids 1..6000 at manifests.collections.yale.edu/ycba/obj/N
  YUAG: ask Wikidata for YUAG object ids (paintings, watercolors, drawings,
        prints), then fetch each manifest.
The image license is NOT the manifest's top-level "rights" (that's CC0 for the
metadata, even on a Picasso). It's the first canvas's "Image Use Rights",
which must start with "No Copyright" (and not carry contractual
restrictions). Then: 1600px+, made by 1930, not a loan or a frame, color
media for YCBA works on paper, secular, inoffensive, in color.

    python tools/build_yale_pool.py heist/yale_pool.json
"""
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

MANIFEST = "https://manifests.collections.yale.edu/{museum}/obj/{oid}"
WDQS = "https://query.wikidata.org/sparql"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}
YUAG_QUERY = """SELECT DISTINCT ?id WHERE { ?item wdt:P8583 ?id ; wdt:P31 ?type .
  VALUES ?type { wd:Q3305213 wd:Q18761202 wd:Q93184 wd:Q11060274 } }"""
YCBA_IDS = range(1, 6001)
LATEST = 1930
COLOR_MEDIA = re.compile(r"(?i)oil|watercolou?r|gouache|tempera|pastel|hand-?colou?red|colou?r[- ]printed|"
                         r"chromolithograph|colou?r woodcut|aquatint")
PER_ARTIST = 8
SEED = 20261123
session = requests.Session()
session.headers.update(HEAD)
session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=8))


def md(meta):
    return {x["label"].get("en", [""])[0]: x["value"].get("en", [""])[0] for x in meta or []}


def manifest(museum, oid):
    try:
        r = session.get(MANIFEST.format(museum=museum, oid=oid), timeout=30)
        if r.status_code != 200:
            return None
        m = r.json()
        c = (m.get("items") or [None])[0]
        if not c:
            return None
        body = c["items"][0]["items"][0]["body"]
        svc = (body.get("service") or [{}])[0]
        return {"museum": museum, "meta": md(m.get("metadata")), "rights": md(c.get("metadata")).get("Image Use Rights", ""),
                "canvas": (c.get("label") or {}).get("en", [""])[0], "label": (m.get("label") or {}).get("en", [""])[0],
                "service": svc.get("@id") or svc.get("id"), "w": body.get("width") or 0, "h": body.get("height") or 0,
                "home": (m.get("homepage") or [{}])[0].get("id")}
    except Exception:  # noqa: BLE001
        return None


def shape(x):
    """Manifest -> heist piece, or None if it isn't public domain loot."""
    M = x["meta"]
    if not x["rights"].startswith("No Copyright") or "Contractual" in x["rights"]:
        return None
    if max(x["w"], x["h"]) < 1600 or "Lent" in x["canvas"] or not x["service"] or not x["home"]:
        return None
    title = (M.get("Title") or "").strip()
    if not title:
        return None
    if x["museum"] == "ycba":
        if M.get("Collection") == "Frames":
            return None
        if "Paintings" not in (M.get("Collection") or "") and not COLOR_MEDIA.search(M.get("Medium") or ""):
            return None
        label = x["label"]
        if title not in label:
            return None
        artist = label.split(", " + title)[0].split(",")[0].strip()
        artist = re.sub(r"^Print made by ", "", artist)
        year = label.split(title + ", ", 1)[1].strip() if title + ", " in label else ""
        museum = "the Yale Center for British Art"
    else:
        creator = (M.get("Creator(s)") or "").split("\n")[0]
        artist = re.sub(r"\s*\(.*$", "", re.sub(r"^\w[\w ]*?:\s*", "", creator)).strip()
        year = M.get("Date") or ""
        museum = "the Yale University Art Gallery"
    years = [int(y) for y in re.findall(r"\b(1[0-9]\d\d)\b", year)]
    if years and min(years) > LATEST:
        return None
    if not years and x["museum"] == "ycba":
        return None
    return {
        "museum": museum,
        "title": title,
        "artist": artist or "Unknown",
        "year": year[:40],
        "medium": "",
        "image": x["service"] + "/full/!1600,1600/0/default.jpg",
        "url": x["home"],
    }


def vet(p):
    if not secular(p["title"]) or not inoffensive(p["title"]):
        return None
    try:
        t = session.get(p["image"].replace("/full/!1600,1600/", "/full/!240,240/"), timeout=60)
        if not t.headers.get("content-type", "").startswith("image/") or not is_color(t.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return p


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_yale_pool.py <out.json>")
    wd = requests.get(WDQS, params={"query": YUAG_QUERY, "format": "json"}, headers=HEAD, timeout=300).json()
    yuag_ids = sorted({b["id"]["value"] for b in wd["results"]["bindings"]})
    jobs = [("ycba", i) for i in YCBA_IDS] + [("yuag", i) for i in yuag_ids]
    with ThreadPoolExecutor(max_workers=8) as ex:
        found = [p for p in (shape(m) for m in ex.map(lambda j: manifest(*j), jobs) if m) if p]
    print(f"  {len(jobs)} manifests read, {len(found)} public domain candidates", flush=True)
    rng = random.Random(SEED)
    rng.shuffle(found)
    with ThreadPoolExecutor(max_workers=6) as ex:
        got = [p for p in ex.map(vet, found) if p]
    pool, per = [], {}
    for p in got:
        if p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST:
            continue
        per[p["artist"]] = per.get(p["artist"], 0) + 1
        pool.append(p)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"  vetted {len(found)}, kept {len(got)}, after artist cap {len(pool)}")
    print(f"wrote {len(pool)} Yale works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
