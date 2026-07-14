"""Rijksmuseum, Amsterdam. Keyless Linked Art open data (data.rijksmuseum.nl).

The classic Rijksmuseum API (which needed a key) was retired and now errors.
The current keyless path is Linked Art JSON-LD. We filter to type=painting (the
full image set is dominated by coins, stamps and prints), walk a BOUNDED random
number of opaque pageTokens to land somewhere in the ~4,900-painting set, then
follow the object -> VisualItem -> DigitalObject chain to the iiif.micr.io image
url. Send Accept: application/ld+json or the root serves the docs site instead
of data. This costs several chained fetches per pick, so it is the slowest
source; the walk is capped to keep build time sane, and any failure just makes
the haul resample another museum.
"""
import requests

HEAD = {
    "User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)",
    "Accept": "application/ld+json",
}
SEARCH = "https://data.rijksmuseum.nl/search/collection?imageAvailable=true&type=painting"
# the Getty AAT id Linked Art tags a "creator/artist" name statement with
PAINTER = "300435416"


def _get(url):
    return requests.get(url, timeout=30, headers=HEAD).json()


def steal(rng):
    d = _get(SEARCH)
    for _ in range(rng.randint(0, 12)):  # bounded walk for spread, not full coverage
        nxt = (d.get("next") or {}).get("id")
        if not nxt:
            break
        d = _get(nxt)
    items = d.get("orderedItems") or []
    if not items:
        raise RuntimeError("Rijksmuseum returned no items")
    o = _get(rng.choice(items)["id"])
    ident = o.get("identified_by") or []
    title = next((b["content"] for b in ident if b.get("type") == "Name"), "Untitled")
    objnum = next((b["content"] for b in ident if b.get("type") == "Identifier"), "")
    pb = o.get("produced_by") or {}
    artist = next((r["content"] for r in pb.get("referred_to_by", [])
                   if any(c.get("id", "").endswith(PAINTER)
                          for c in r.get("classified_as", []))), "Unknown")
    year = next((n["content"] for n in
                 (pb.get("timespan") or {}).get("identified_by", [])), "")
    shows = o.get("shows") or []
    if not shows:
        raise RuntimeError("Rijksmuseum: object has no visual item")
    v = _get(shows[0]["id"])
    dig = v.get("digitally_shown_by") or []
    if not dig:
        raise RuntimeError("Rijksmuseum: no digital object")
    ap = (_get(dig[0]["id"]).get("access_point") or [])
    if not ap:
        raise RuntimeError("Rijksmuseum: no image access point")
    return {
        "museum": "Rijksmuseum, Amsterdam",
        "title": title,
        "artist": artist,
        "year": year,
        "medium": "painting",
        "image": ap[0]["id"],  # iiif.micr.io url
        "url": f"https://www.rijksmuseum.nl/en/collection/{objnum}",
    }
