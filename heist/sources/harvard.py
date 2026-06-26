"""Harvard Art Museums. Free key (HARVARD_API_KEY); display-cleared images only."""
import re

import requests

from engine.common import HARVARD_API_KEY

API = "https://api.harvardartmuseums.org/object"
FIELDS = "title,people,dated,medium,classification,primaryimageurl,url"

# Harvard's display-cleared holdings are ~22% Photographs, and they are
# overwhelmingly historical black-and-white or sepia prints — the kind the
# color gate can't always catch, because a warm-toned silver print is
# statistically indistinguishable from a warm-toned painting. The thief only
# wants color, and the haul has five other museums for variety, so skip the
# whole class outright. Also skip the anonymous "Untitled"/"Unidentified"
# scans: dull loot with no story.
SKIP_CLASS = {"Photographs"}
SKIP_TITLE = re.compile(r"unidentified|unknown (sitter|man|woman)|^\[?untitled", re.I)


def available():
    return bool(HARVARD_API_KEY)


def steal(rng):
    if not HARVARD_API_KEY:
        raise RuntimeError("No HARVARD_API_KEY configured")
    records = requests.get(
        API,
        params={
            "apikey": HARVARD_API_KEY,
            "hasimage": 1,
            "q": "imagepermissionlevel:0",
            "size": 25,
            "sort": f"random:{rng.randint(1, 10_000_000)}",
            "fields": FIELDS,
        },
        timeout=30,
    ).json().get("records") or []
    for r in records:
        image = r.get("primaryimageurl")
        title = r.get("title") or ""
        if not image or not title:
            continue
        if r.get("classification") in SKIP_CLASS or SKIP_TITLE.search(title):
            continue
        # nrs.harvard.edu urls are 303 redirects that picky email clients
        # (Apple Mail) refuse to follow. Resolve to the final image url now.
        try:
            image = requests.head(image, allow_redirects=True, timeout=20).url
        except Exception:  # noqa: BLE001
            continue
        # The resolved url is IIIF; ask Harvard for an email-sized render.
        image = image.replace("/full/full/0/", "/full/!1120,1120/0/")
        people = r.get("people") or []
        return {
            "museum": "Harvard Art Museums",
            "title": r["title"],
            "artist": people[0].get("name", "Unknown") if people else "Unknown",
            "year": r.get("dated") or "",
            "medium": r.get("medium") or r.get("classification") or "",
            "image": image,
            "url": r.get("url") or "https://harvardartmuseums.org",
        }
    raise RuntimeError("Harvard: no usable records in sample")
