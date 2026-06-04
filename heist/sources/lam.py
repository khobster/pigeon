"""On the Lam: tonight's hideout, somewhere on earth."""
import json
from pathlib import Path

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
    image = ((data.get("thumbnail") or {}).get("source") or "").replace("/320px-", "/640px-")
    return {
        "name": place["name"],
        "blurb": blurb,
        "image": image,
        "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
    }
