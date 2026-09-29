"""The Metropolitan Museum of Art. Open Access (CC0), no key needed."""
import requests

SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{}"

# Eclectic subjects and mediums, deliberately steered AWAY from the generic
# "painting / portrait / landscape" terms that funnel the Met's search into its
# most-reproduced old-master oil paintings. This vocabulary pulls prints,
# ukiyo-e, posters, textiles, ceramics, design and ephemera — the wild, modern-
# feeling end of an encyclopedic public-domain collection.
QUERIES = [
    "ukiyo-e", "woodblock print", "art nouveau", "art deco", "tiffany",
    "stained glass", "poster", "kimono", "textile", "tapestry", "porcelain",
    "lacquer", "netsuke", "jewelry", "glass", "folk", "mask", "costume",
    "botanical", "musical instrument", "arms and armor", "fan", "screen",
    "playing cards", "calligraphy", "embroidery", "fashion", "vase", "tea",
    "dance", "festival", "puppet", "toy", "shell", "insect", "map",
    # modernist supply so the art director has genuinely modern/indie options,
    # not just old-master paintings, to lean into.
    "post-impressionism", "impressionism", "expressionism", "modern",
    "van gogh", "cezanne", "gauguin", "seurat", "toulouse-lautrec", "klimt",
]


def steal(rng):
    """Return one public-domain artwork with an image, or raise."""
    q = rng.choice(QUERIES)
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
