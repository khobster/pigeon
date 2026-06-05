"""Smithsonian Open Access: SAAM, the National Portrait Gallery, the
Freer/Sackler, and Cooper Hewitt. CC0 records, free key (SI_API_KEY)."""
import requests

from engine.common import SI_API_KEY

API = "https://api.si.edu/openaccess/api/v1.0/search"
QUERY = (
    '(unit_code:SAAM OR unit_code:NPG OR unit_code:FSG OR unit_code:CHNDM)'
    ' AND online_media_type:"Images" AND media_usage:CC0'
)
UNITS = {
    "SAAM": "the Smithsonian American Art Museum",
    "NPG": "the National Portrait Gallery",
    "FSG": "the Smithsonian's National Museum of Asian Art",
    "CHNDM": "Cooper Hewitt, Smithsonian Design Museum",
}


def available():
    return bool(SI_API_KEY)


def _freetext(content, key):
    items = (content.get("freetext") or {}).get(key) or []
    return items[0].get("content", "") if items else ""


def steal(rng):
    if not SI_API_KEY:
        raise RuntimeError("No SI_API_KEY configured")
    base = {"q": QUERY, "api_key": SI_API_KEY, "rows": 20}
    total = requests.get(API, params={**base, "rows": 1}, timeout=30).json()["response"]["rowCount"]
    start = rng.randint(0, max(0, min(total, 9000) - 20))
    rows = requests.get(API, params={**base, "start": start}, timeout=30).json()["response"]["rows"]
    rng.shuffle(rows)
    for r in rows:
        content = r.get("content") or {}
        dnr = content.get("descriptiveNonRepeating") or {}
        media = (dnr.get("online_media") or {}).get("media") or []
        image = media[0].get("content") if media else None
        title = r.get("title") or ""
        if not image or not title:
            continue
        return {
            "museum": UNITS.get(dnr.get("unit_code"), "the Smithsonian"),
            "title": title,
            "artist": _freetext(content, "name") or "Unknown",
            "year": _freetext(content, "date"),
            "medium": _freetext(content, "physicalDescription"),
            "image": image,
            "url": dnr.get("record_link") or dnr.get("guid") or "https://www.si.edu",
        }
    raise RuntimeError("Smithsonian: no usable rows in sample")
