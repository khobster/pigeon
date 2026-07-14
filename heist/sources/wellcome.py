"""Wellcome Collection, London. Keyless catalogue API (Public Domain Mark).

A single REST call — the cheapest of the sources. Wellcome skews toward
historical prints and drawings, a fair share of them black-and-white, so many
candidates get dropped by the color gate downstream; the build's resampling
routes around that. The license filter is `pdm` (Public Domain Mark) — `cc0`
returns almost nothing here.
"""
import requests

HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
API = "https://api.wellcomecollection.org/catalogue/v2/works"


def steal(rng):
    params = {
        "items.locations.locationType": "iiif-image",
        "items.locations.license": "pdm",
        "workType": "k",  # Pictures
        "pageSize": 100,
        "page": rng.randint(1, 50),
        "include": "items,production,contributors",
    }
    res = requests.get(API, params=params, timeout=30, headers=HEAD).json().get("results") or []
    if not res:
        raise RuntimeError("Wellcome returned nothing")
    w = rng.choice(res)
    info = next((loc["url"] for it in w.get("items", [])
                 for loc in it.get("locations", [])
                 if loc.get("locationType", {}).get("id") == "iiif-image"), None)
    if not info:
        raise RuntimeError("Wellcome: no iiif image location")
    # the location url ends in /info.json; swap it for a sized image request
    image = info.rsplit("/info.json", 1)[0] + "/full/880,/0/default.jpg"
    artist = next((c["agent"]["label"] for c in w.get("contributors", [])
                   if c.get("agent")), "Unknown")
    prod = w.get("production") or []
    dates = (prod[0].get("dates") if prod else []) or []
    year = dates[0].get("label", "") if dates else ""
    return {
        "museum": "Wellcome Collection, London",
        "title": w.get("title", "Untitled"),
        "artist": artist,
        "year": year,
        "medium": "print/drawing",
        "image": image,
        "url": f"https://wellcomecollection.org/works/{w['id']}",
    }
