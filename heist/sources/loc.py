"""From the Vault: a find from the Library of Congress archives.

The thief favors the loud stuff the catalog actually photographed at size:
posters, lithographs, panoramas. The search hands back a list of image
sizes per item with the pixel dimensions encoded in a #h=&w= fragment, so
we rank by that and take the largest real jpg. Anything that is only a
150px thumbnail, an SVG placeholder, or an unidentified-portrait scan gets
skipped, which is how the dull Civil War mugshots stop slipping through.
"""
import re
import time

import requests

API = "https://www.loc.gov/photos/"
TOPICS = [
    "wpa poster", "travel poster", "circus poster", "theater poster",
    "national park poster", "railroad poster", "world's fair poster",
    "panoramic photograph", "lighthouse", "ocean liner",
    "route 66", "diner", "drive-in theater", "vaudeville", "carousel",
]

# Catalog scans that make dull loot, no matter how big the file is.
SKIP_TITLE = re.compile(r"unidentified|^\[?group |portrait of an? unidentified", re.I)
BAD_IMG = ("/static/", ".svg", ".gif")
MIN_AREA = 500 * 400  # below this it is a thumbnail, not a haul


def _best_image(urls):
    """The largest real jpg in an image_url list. LOC stores the pixel size
    in a #h=&w= fragment, so we rank by area rather than trusting list order,
    and drop placeholders, gifs and tiny thumbnails."""
    best, best_area = None, 0
    for u in urls or []:
        base = u.split("#")[0]
        if not base.lower().endswith((".jpg", ".jpeg")):
            continue
        if any(b in base for b in BAD_IMG):
            continue
        w = re.search(r"[#&]w=(\d+)", u)
        h = re.search(r"[#&]h=(\d+)", u)
        area = (int(w.group(1)) if w else 0) * (int(h.group(1)) if h else 0)
        if area > best_area:
            best, best_area = base, area
    return best, best_area


def _search(topic):
    """Fetch one topic's results, retrying LOC's flaky API.

    loc.gov regularly answers a perfectly valid request with an empty body,
    an HTML "please slow down" page, or a 429/5xx — especially from a
    datacenter IP like the GitHub runner. A raw .json() on that throws
    'Expecting value: line 1 column 1', which used to kill the whole Vault
    section. So we check the status, guard the decode, and back off."""
    last = None
    for attempt in range(4):
        try:
            r = requests.get(
                API,
                params={"q": topic, "fo": "json", "c": 60},
                timeout=30,
                headers={"User-Agent": "pigeon-heist/1.0 (+https://heist.arugulamotors.com)"},
            )
            r.raise_for_status()
            return r.json().get("results") or []
        except Exception as e:  # noqa: BLE001 — any flake means try again
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"LOC unreachable for '{topic}': {last}")


def steal(rng):
    # Try every topic before giving up, so one flaky API call (or one topic
    # with nothing usable) no longer drops the section. Shuffle once, from the
    # seeded rng, so the day stays reproducible.
    order = TOPICS[:]
    rng.shuffle(order)
    last = None
    for topic in order:
        try:
            results = _search(topic)
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        rng.shuffle(results)
        for item in results:
            title = (item.get("title") or "").strip(". ")
            if not title or SKIP_TITLE.search(title):
                continue
            image, area = _best_image(item.get("image_url"))
            if not image or area < MIN_AREA:
                continue
            return {
                "title": title,
                "date": item.get("date") or "",
                "image": image,
                "url": item.get("id") or item.get("url") or "https://www.loc.gov",
                "topic": topic,
            }
    raise RuntimeError(f"LOC: nothing usable across all topics: {last}")
