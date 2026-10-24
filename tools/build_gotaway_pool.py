"""Curate the pool for The One That Got Away.

The great modern museums publish their catalogs as open data; only the
pictures are off limits (the art is still in copyright). So this section
names great modern pieces the thief couldn't take and links to each museum's
own page, where the reader sees them. Text only, no image.

Sources and their notability filters (a famous name is the heartbreak):
  MoMA        Artworks.csv (CC0, GitHub): works currently on view
  the Whitney artworks.csv (CC0, GitHub): Wikidata entry + an artist it holds
              deeply (25+ works: Hopper, Warhol, Ruscha, Lichtenstein...)
  the Art Institute of Chicago  public API: "boosted" (its own highlights)
  the Met     public API: highlights of Modern and Contemporary Art
  Tate        artwork_data.csv (CC0, GitHub): in copyright, by a famous name
  the Guggenheim  its site's public WordPress API, by a famous name
"Famous name" for Tate and the Guggenheim means the artist also made the cut
at one of the first four, so we never send anyone to an unknown.

We keep paintings and sculpture from after the public-domain line (the stuff
we really can't show), skip bare "Untitled", and cap each artist.

    python tools/build_gotaway_pool.py heist/gotaway_pool.json
"""
import csv
import html
import io
import json
import re
import sys
import time
import unicodedata

import requests

MOMA = "https://media.githubusercontent.com/media/MuseumofModernArt/collection/main/Artworks.csv"
WHITNEY = "https://raw.githubusercontent.com/whitneymuseum/open-access/main/artworks.csv"
TATE = "https://raw.githubusercontent.com/tategallery/collection/master/artwork_data.csv"
AIC = "https://api.artic.edu/api/v1/artworks/search"
MET = "https://collectionapi.metmuseum.org/public/collection/v1"
GUGG = "https://www.guggenheim.org/wp-json/wp/v2"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
PD_YEAR = 1930
PER_ARTIST = 2  # per museum, so each one keeps its own Pollock
WHITNEY_DEPTH = 25
TATE_MEDIUM = re.compile(r"(?i)\b(paint|acrylic|oil|bronze|steel|wood|stone|marble|plaster|aluminium)\b")


def rows(url):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def get(url, **params):
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=HEAD, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return None


def first_year(text):
    m = re.search(r"\b(19\d\d|20\d\d)(?!\d)", text or "")
    return int(m.group(1)) if m else None


def keep(title, artist, date):
    if not title or not artist or re.fullmatch(r"(?i)(untitled|no title)\.?", title.strip()):
        return False
    y = first_year(date)
    return bool(y and y > PD_YEAR)


def norm(name):
    """'Pollock, Jackson' and 'Jackson Pollock' -> 'jackson pollock'."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    if n.count(",") == 1:
        last, first = [x.strip() for x in n.split(",")]
        n = f"{first} {last}"
    return re.sub(r"[^a-z ]", "", n).strip()


def short_year(text):
    """'August 1964 (fourth version, ...)' -> '1964'; '1990s' stays a decade."""
    m = re.search(r"\b(?:19|20)\d\d(?:s\b)?", text or "")
    return m.group(0) if m else ""


def piece(museum, title, artist, year, medium, url):
    return {"museum": museum, "title": html.unescape(title).strip(), "artist": artist.strip(),
            "year": short_year(str(year)), "medium": (medium or "").strip(), "url": url}


def moma():
    out = []
    for r in rows(MOMA):
        if not r.get("OnView", "").strip() or r.get("Classification") not in ("Painting", "Sculpture"):
            continue
        if keep(r["Title"], r["Artist"], r["Date"]) and r.get("URL"):
            out.append(piece("MoMA", r["Title"], r["Artist"], r["Date"], r["Medium"], r["URL"]))
    return out


def whitney():
    data, holdings, out = rows(WHITNEY), {}, []
    for r in data:
        holdings[r["artists"]] = holdings.get(r["artists"], 0) + 1
    for r in data:
        if not r.get("wikidata_id", "").strip() or holdings[r["artists"]] < WHITNEY_DEPTH:
            continue
        if keep(r["title"], r["artists"], r["display_date"]):
            out.append(piece("the Whitney", r["title"], r["artists"], r["display_date"], r["medium"],
                             f"https://whitney.org/collection/works/{r['id']}"))
    return out


def aic():
    out, page = [], 1
    while True:
        d = get(AIC, **{
            "query[bool][must][0][term][is_boosted]": "true",
            "query[bool][must][1][term][is_public_domain]": "false",
            "fields": "id,title,artist_title,date_display,medium_display,artwork_type_title",
            "limit": 100, "page": page})
        if not d:
            break
        for r in d["data"]:
            if r.get("artwork_type_title") not in ("Painting", "Sculpture"):
                continue
            if keep(r.get("title"), r.get("artist_title"), r.get("date_display")):
                out.append(piece("the Art Institute of Chicago", r["title"], r["artist_title"],
                                 r["date_display"], r.get("medium_display"),
                                 f"https://www.artic.edu/artworks/{r['id']}"))
        if page >= d["pagination"]["total_pages"]:
            break
        page += 1
    return out


def met():
    ids, offset = [], 0
    while True:
        d = get(MET + ".1/search", isHighlight="true", departmentId=21, q="*", offset=offset, limit=100)
        got = (d or {}).get("objectIDs") or []
        ids += got
        if len(got) < 100:
            break
        offset += 100
    out = []
    for i in ids:
        r = get(f"{MET}/objects/{i}")
        time.sleep(0.1)
        if not r or r.get("isPublicDomain"):
            continue
        if r.get("classification") not in ("Paintings", "Sculpture"):
            continue
        if keep(r.get("title"), r.get("artistDisplayName"), r.get("objectDate")):
            out.append(piece("the Met", r["title"], r["artistDisplayName"], r["objectDate"],
                             r.get("medium"), r["objectURL"]))
    return out


def tate(famous):
    out = []
    for r in rows(TATE):
        if not r.get("thumbnailCopyright", "").strip() or not TATE_MEDIUM.search(r.get("medium", "")):
            continue
        if "paper" in r.get("medium", "").lower() or norm(r["artist"]) not in famous:
            continue
        if keep(r["title"], r["artist"], r["year"]):
            last, _, first = r["artist"].partition(", ")
            out.append(piece("Tate", r["title"], f"{first} {last}".strip(), r["dateText"], r["medium"],
                             r["url"].replace("http://", "https://")))
    return out


def taxonomy(name):
    names, page = {}, 1
    while True:
        d = get(f"{GUGG}/{name}", per_page=100, page=page, _fields="id,name")
        if not d:
            break
        names.update({t["id"]: html.unescape(t["name"]) for t in d})
        if len(d) < 100:
            break
        page += 1
    return names


def guggenheim(famous):
    artists, decades, types = taxonomy("artist"), taxonomy("decade"), taxonomy("artwork_type")
    out, page = [], 1
    while True:
        d = get(f"{GUGG}/artwork", per_page=100, page=page, _fields="link,title,artist,decade,artwork_type")
        if not d:
            break
        for r in d:
            # Most records leave the type blank, so only drop the known misses.
            kinds = {types.get(t) for t in r.get("artwork_type") or []}
            if kinds & {"Film/Video", "Photography", "Internet Art", "Work on paper"}:
                continue
            who = [artists[a] for a in r.get("artist") or [] if a in artists]
            decade = next((decades[x] for x in r.get("decade") or [] if x in decades), "")
            if len(who) != 1 or norm(who[0]) not in famous:
                continue
            if keep(r["title"]["rendered"], who[0], decade):
                out.append(piece("the Guggenheim", r["title"]["rendered"], who[0], decade, "", r["link"]))
        if len(d) < 100:
            break
        page += 1
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_gotaway_pool.py <out.json>")
    pool = []
    for fn in (moma, whitney, aic, met):
        got = fn()
        print(f"  {fn.__name__:12} {len(got)}", flush=True)
        pool += got
    famous = {norm(p["artist"]) for p in pool}
    for fn in (tate, guggenheim):
        got = fn(famous)
        print(f"  {fn.__name__:12} {len(got)}", flush=True)
        pool += got
    per, seen, out = {}, set(), []
    for p in pool:
        who = (p["museum"], norm(p["artist"]))
        if per.get(who, 0) >= PER_ARTIST or p["url"] in seen:
            continue
        per[who] = per.get(who, 0) + 1
        seen.add(p["url"])
        out.append(p)
    out.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(out, f, indent=0, ensure_ascii=False)
    counts = {}
    for p in out:
        counts[p["museum"]] = counts.get(p["museum"], 0) + 1
    print(f"wrote {len(out)} works {counts} -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
