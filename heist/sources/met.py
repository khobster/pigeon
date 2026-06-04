"""The Metropolitan Museum of Art. Open Access (CC0), no key needed."""
import requests

SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"


def steal(rng):
    """Return one public-domain artwork with an image, or raise."""
    q = rng.choice(["painting", "portrait", "landscape", "still life", "flowers"])
    ids = requests.get(
        SEARCH,
        params={"q": q, "isPublicDomain": "true", "hasImages": "true"},
        timeout=30,
    ).json().get("objectIDs") or []
    if not ids:
        raise RuntimeError("Met search returned nothing")
    rng.shuffle(ids)
    for object_id in ids[:8]:
        obj = requests.get(OBJECT.format(object_id), timeout=30).json()
        image = obj.get("primaryImage") or obj.get("primaryImageSmall")
        if not image:
            continue
        return {
            "museum": "The Metropolitan Museum of Art",
            "title": obj.get("title") or "Untitled",
            "artist": obj.get("artistDisplayName") or "Unknown",
            "year": obj.get("objectDate") or "",
            "medium": obj.get("medium") or "",
            "image": image,
            "url": obj.get("objectURL") or "",
        }
    raise RuntimeError("Met: no usable image in sample")
