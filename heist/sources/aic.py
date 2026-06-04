"""Art Institute of Chicago. Open Access (CC0), no key needed."""
import requests

SEARCH = "https://api.artic.edu/api/v1/artworks/search"
IIIF = "https://www.artic.edu/iiif/2/{}/full/843,/0/default.jpg"
FIELDS = "id,title,artist_display,date_display,medium_display,image_id"


def steal(rng):
    page = rng.randint(1, 80)
    data = requests.get(
        SEARCH,
        params={
            "query[term][is_public_domain]": "true",
            "fields": FIELDS,
            "limit": 50,
            "page": page,
        },
        timeout=30,
    ).json().get("data") or []
    rng.shuffle(data)
    for art in data:
        if not art.get("image_id"):
            continue
        return {
            "museum": "Art Institute of Chicago",
            "title": art.get("title") or "Untitled",
            "artist": (art.get("artist_display") or "Unknown").split("\n")[0],
            "year": art.get("date_display") or "",
            "medium": art.get("medium_display") or "",
            "image": IIIF.format(art["image_id"]),
            "url": f"https://www.artic.edu/artworks/{art['id']}",
        }
    raise RuntimeError("AIC: no usable image on page")
