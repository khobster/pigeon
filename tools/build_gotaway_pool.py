"""Curate the pool for The One That Got Away.

MoMA and the Whitney publish their full collection catalogs as CC0 data on
GitHub; only the pictures are off limits (the art is still in copyright). So
this section names a great modern piece the thief couldn't take and links to
the museum's own page, where the reader sees it. Text only, no image.

Notability filters: MoMA works currently on view (its own greatest-hits
wall), paintings and sculpture; Whitney paintings that have a Wikidata entry,
by artists the Whitney holds deeply (25+ works: Hopper, Warhol, Ruscha,
Lichtenstein, Johns, Calder...), since a famous name is the heartbreak.
We keep only work from after the public-domain line (the stuff we really
can't show), skip bare "Untitled", and cap each artist so it stays varied.

    python tools/build_gotaway_pool.py heist/gotaway_pool.json
"""
import csv
import io
import json
import re
import sys

import requests

MOMA = "https://media.githubusercontent.com/media/MuseumofModernArt/collection/main/Artworks.csv"
WHITNEY = "https://raw.githubusercontent.com/whitneymuseum/open-access/main/artworks.csv"
PD_YEAR = 1930
PER_ARTIST = 3
WHITNEY_DEPTH = 25


def rows(url):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def first_year(text):
    m = re.search(r"\b(19\d\d|20\d\d)\b", text or "")
    return int(m.group(1)) if m else None


def keep(title, artist, date):
    if not title or not artist or re.fullmatch(r"(?i)untitled\.?", title.strip()):
        return False
    y = first_year(date)
    return bool(y and y > PD_YEAR)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_gotaway_pool.py <out.json>")
    pool = []
    for r in rows(MOMA):
        if not r.get("OnView", "").strip() or r.get("Classification") not in ("Painting", "Sculpture"):
            continue
        if not keep(r["Title"], r["Artist"], r["Date"]) or not r.get("URL"):
            continue
        pool.append({"museum": "MoMA", "title": r["Title"].strip(), "artist": r["Artist"].strip(),
                     "year": r["Date"].strip(), "medium": r["Medium"].strip(), "url": r["URL"]})
    whitney = rows(WHITNEY)
    holdings = {}
    for r in whitney:
        holdings[r["artists"]] = holdings.get(r["artists"], 0) + 1
    for r in whitney:
        if not r.get("wikidata_id", "").strip() or holdings[r["artists"]] < WHITNEY_DEPTH:
            continue
        if not keep(r["title"], r["artists"], r["display_date"]):
            continue
        pool.append({"museum": "the Whitney", "title": r["title"].strip(), "artist": r["artists"].strip(),
                     "year": r["display_date"].strip(), "medium": r["medium"].strip(),
                     "url": f"https://whitney.org/collection/works/{r['id']}"})
    per, out = {}, []
    for p in pool:
        if per.get(p["artist"], 0) >= PER_ARTIST:
            continue
        per[p["artist"]] = per.get(p["artist"], 0) + 1
        out.append(p)
    out.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(out, f, indent=0, ensure_ascii=False)
    n = sum(p["museum"] == "MoMA" for p in out)
    print(f"wrote {len(out)} works ({n} MoMA, {len(out) - n} Whitney) -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
