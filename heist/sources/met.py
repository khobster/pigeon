"""The Metropolitan Museum of Art. Open Access (CC0), no key needed.

The Met RETIRED its keyword /search endpoint on 2026-10-01, so we can no longer
search by term (the old QUERIES list is gone). Instead we pull by DEPARTMENT via
the still-live /objects (full id list, filterable by department) and
/objects/{id} endpoints. That doubles as the variety fix: the Met's public-domain
ukiyo-e holdings are enormous, and a term list heavy with Japanese keywords made
the whole newsletter skew Asian. Here Asian Art is just one department of
fourteen. We cache each department's id list for the process so we are not
re-fetching a 15k-id list on every draw.
"""
import requests

API = "https://collectionapi.metmuseum.org/public/collection/v1"

# A broad spread of departments for cross-cultural variety. Asian Art (6) is one
# slot among many, on purpose. Skipped: Libraries (books), Photographs (B&W).
DEPARTMENTS = [
    1,   # American Decorative Arts
    3,   # Ancient Near Eastern Art
    4,   # Arms and Armor
    5,   # Arts of Africa, Oceania, and the Americas
    6,   # Asian Art
    9,   # Costume Institute
    10,  # Egyptian Art
    11,  # European Paintings
    12,  # European Sculpture and Decorative Arts
    13,  # Greek and Roman Art
    14,  # Islamic Art
    17,  # Medieval Art
    21,  # Modern and Contemporary Art
    60,  # Drawings and Prints
]

_DEPT_CACHE = {}


def _dept_ids(dept):
    if dept not in _DEPT_CACHE:
        try:
            r = requests.get(f"{API}/objects", params={"departmentIds": dept}, timeout=30)
            ids = r.json().get("objectIDs") or []
        except Exception:  # noqa: BLE001
            ids = []
        if ids:  # don't cache a transient empty (the /objects call can throttle)
            _DEPT_CACHE[dept] = ids
        return ids
    return _DEPT_CACHE[dept]


def steal(rng):
    """Return one public-domain Met object with an image, or raise."""
    ids = list(_dept_ids(rng.choice(DEPARTMENTS)))
    if not ids:
        raise RuntimeError("Met: no objects in department")
    rng.shuffle(ids)
    for oid in ids[:10]:
        try:
            obj = requests.get(f"{API}/objects/{oid}", timeout=30).json()
        except Exception:  # noqa: BLE001  (throttle / bad body -> try the next id)
            continue
        if not obj.get("isPublicDomain"):
            continue
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
    raise RuntimeError("Met: no public-domain image in sample")
