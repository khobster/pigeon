"""New York Public Library Digital Collections — public-domain graphic loot:
posters, prints, ephemera, vintage photography, design. Free token (NYPL_TOKEN).

publicDomainOnly=true restricts to the subset NYPL has explicitly cleared as
public domain, so the licensing is clean (unlike the V&A, whose images are all
copyrighted). Images come off images.nypl.org at t=w (~760px). Inert without a
token, so a missing key just drops it from the rotation.
"""
import requests

from engine.common import NYPL_TOKEN

API = "http://api.repo.nypl.org/api/v2/items/search"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}

# Color-rich graphic subjects — NYPL is deep in these. We steer away from its
# large black-and-white ephemera (menus, news, plain advertising) because the
# color gate would just drop those.
QUERIES = [
    "poster", "art deco", "art nouveau", "travel poster", "chromolithograph",
    "fashion plate", "japanese woodblock print", "circus poster",
    "botanical", "decorative arts", "illuminated", "ex libris",
]


def available():
    return bool(NYPL_TOKEN)


def steal(rng):
    if not NYPL_TOKEN:
        raise RuntimeError("No NYPL_TOKEN configured")
    q = rng.choice(QUERIES)
    headers = {**HEAD, "Authorization": f'Token token="{NYPL_TOKEN}"'}
    params = {"q": q, "publicDomainOnly": "true", "per_page": 50, "page": rng.randint(1, 10)}
    resp = requests.get(API, params=params, headers=headers, timeout=30).json()
    result = ((resp.get("nyplAPI") or {}).get("response") or {}).get("result") or []
    if isinstance(result, dict):  # NYPL returns a bare object when a page holds one item
        result = [result]
    rng.shuffle(result)
    for it in result:
        iid = it.get("imageID")
        if not iid or not isinstance(iid, str):
            continue
        return {
            "museum": "the New York Public Library",
            "title": (it.get("title") or "Untitled").strip(" ."),
            "artist": "Unknown",
            "year": "",
            "medium": q,
            "image": f"https://images.nypl.org/index.php?id={iid}&t=w",
            "url": it.get("itemLink") or "https://digitalcollections.nypl.org",
        }
    raise RuntimeError("NYPL: no usable image in sample")
