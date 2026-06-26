"""Smithsonian Open Access: the American Art Museum, the National Museum of
Asian Art, Cooper Hewitt, the Hirshhorn, and the National Museum of African
Art. CC0 records, free key (SI_API_KEY).

The National Portrait Gallery was dropped on purpose — it is wall-to-wall
B&W portraits (named sitters slipped past the color gate, anonymous ones were
dull loot). The Asian-art unit code FSG is dead (0 CC0 records); the current
code is NMAA, which is what we query now."""
import re

import requests

from engine.common import SI_API_KEY

API = "https://api.si.edu/openaccess/api/v1.0/search"
QUERY = (
    '(unit_code:SAAM OR unit_code:NMAA OR unit_code:CHNDM'
    ' OR unit_code:HMSG OR unit_code:NMAfA)'
    ' AND online_media_type:"Images" AND media_usage:CC0'
)
UNITS = {
    "SAAM": "the Smithsonian American Art Museum",
    "NMAA": "the National Museum of Asian Art",
    "CHNDM": "Cooper Hewitt, Smithsonian Design Museum",
    "HMSG": "the Hirshhorn Museum and Sculpture Garden",
    "NMAfA": "the National Museum of African Art",
}

# Drop anonymous/untitled scans across any unit — dull loot, no story.
SKIP_TITLE = re.compile(r"unidentified|unknown (sitter|man|woman)|^\[?untitled", re.I)


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
        if not image or not title or SKIP_TITLE.search(title):
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
