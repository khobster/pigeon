"""Cleveland Museum of Art. Open Access (CC0), no key needed."""
import requests

API = "https://openaccess-api.clevelandart.org/api/artworks/"


def steal(rng):
    base = {"cc0": "1", "has_image": "1", "limit": 1}
    # On ~half the draws, restrict to Cleveland's early-modern window (1880-1940:
    # 6,674 CC0 works — Bellows, late Monet, Degas, Redon lithographs) so its real
    # modern slice surfaces instead of being diluted by the whole 41k collection.
    if rng.random() < 0.5:
        base = {**base, "created_after": 1880, "created_before": 1940}
    total = requests.get(API, params=base, timeout=30).json()["info"]["total"]
    skip = rng.randint(0, max(0, total - 1))
    arts = requests.get(
        API, params={**base, "skip": skip}, timeout=30
    ).json().get("data") or []
    if not arts:
        raise RuntimeError("Cleveland returned nothing")
    art = arts[0]
    image = ((art.get("images") or {}).get("web") or {}).get("url")
    if not image:
        raise RuntimeError("Cleveland: no web image")
    creators = art.get("creators") or []
    artist = creators[0]["description"] if creators else "Unknown"
    return {
        "museum": "The Cleveland Museum of Art",
        "title": art.get("title") or "Untitled",
        "artist": artist,
        "year": art.get("creation_date") or "",
        "medium": art.get("technique") or "",
        "image": image,
        "url": art.get("url") or "",
    }
