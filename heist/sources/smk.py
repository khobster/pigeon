"""SMK, the National Gallery of Denmark. Open data (CC0), no key needed."""
import requests

API = "https://api.smk.dk/api/v1/art/search/"


def steal(rng):
    base = {
        "keys": "*",
        "filters": "[has_image:true],[public_domain:true]",
        "rows": 1,
        "lang": "en",
    }
    total = requests.get(API, params={**base, "offset": 0}, timeout=30).json().get("found", 0)
    if not total:
        raise RuntimeError("SMK search returned nothing")
    offset = rng.randint(0, min(total, 10000) - 1)
    items = requests.get(API, params={**base, "offset": offset}, timeout=30).json().get("items") or []
    if not items:
        raise RuntimeError("SMK: empty page")
    art = items[0]

    iiif = art.get("image_iiif_id")
    image = f"{iiif}/full/!843,/0/default.jpg" if iiif else art.get("image_thumbnail")
    if not image:
        raise RuntimeError("SMK: no usable image")

    titles = art.get("titles") or []
    english = [t for t in titles if (t.get("language") or "").lower() in ("english", "engelsk")]
    title = (english or titles or [{}])[0].get("title") or "Untitled"
    artists = art.get("artist") or []
    dating = art.get("production_date") or []
    techniques = art.get("techniques") or []
    return {
        "museum": "SMK, the National Gallery of Denmark",
        "title": title,
        "artist": artists[0] if artists else "Unknown",
        "year": dating[0].get("period", "") if dating else "",
        "medium": techniques[0] if techniques else "",
        "image": image,
        "url": art.get("frontend_url") or "https://open.smk.dk",
    }
