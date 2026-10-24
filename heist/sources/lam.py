"""On the Lam: tonight's hideout, somewhere on earth."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests

PLACES = json.loads((Path(__file__).resolve().parent.parent / "places.json").read_text())
SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"


def steal(rng):
    place = rng.choice(PLACES)
    data = requests.get(
        SUMMARY.format(place["wiki"]),
        timeout=30,
        headers={"User-Agent": "pigeon-heist/1.0"},
    ).json()
    blurb = (data.get("extract") or "").strip()
    # Keep it a bite, not a meal: first two sentences.
    parts = blurb.split(". ")
    blurb = ". ".join(parts[:2]).rstrip(".") + "." if parts else ""
    # The full-size original, not the 320px thumbnail; the build scales it to
    # a crisp email size. Only a real photo (JPEG, 800px+); lead images that
    # are PNG/SVG are maps, flags and seals.
    orig = data.get("originalimage") or {}
    image = orig.get("source", "")
    if not urlsplit(image).path.lower().endswith((".jpg", ".jpeg")) or orig.get("width", 0) < 800:
        image = ""
    return {
        "name": place["name"],
        "blurb": blurb,
        "image": image,
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
    }
