"""Rijksmuseum, Amsterdam. Needs a free API key (RIJKS_API_KEY)."""
import requests

from engine.common import RIJKS_API_KEY

API = "https://www.rijksmuseum.nl/api/en/collection"


def available():
    return bool(RIJKS_API_KEY)


def steal(rng):
    if not RIJKS_API_KEY:
        raise RuntimeError("No RIJKS_API_KEY configured")
    page = rng.randint(1, 80)
    arts = requests.get(
        API,
        params={"key": RIJKS_API_KEY, "imgonly": "True", "ps": 50, "p": page, "type": "painting"},
        timeout=30,
    ).json().get("artObjects") or []
    rng.shuffle(arts)
    for art in arts:
        image = (art.get("webImage") or {}).get("url")
        if not image:
            continue
        return {
            "museum": "Rijksmuseum, Amsterdam",
            "title": art.get("title") or "Untitled",
            "artist": art.get("principalOrFirstMaker") or "Unknown",
            "year": art.get("longTitle", "").rsplit(",", 1)[-1].strip(),
            "medium": "",
            "image": image,
            "url": (art.get("links") or {}).get("web") or "",
        }
    raise RuntimeError("Rijks: no usable image on page")
