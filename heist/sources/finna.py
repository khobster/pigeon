"""Finna — the Finnish/Nordic aggregator across Finland's museums, archives, and
libraries. Keyless. Adds Nordic and Finnish graphic loot (posters, design, art).

We restrict to freely-online records AND, in code, to openly-licensed images:
CC0, Public Domain, or CC BY / CC BY-SA (attribution is fine, we credit the
source). CC BY-NC (non-commercial) and CC BY-ND (no-derivatives — we resize, a
derivative) are excluded. The record's cover image resolves off api.finna.fi.
"""
import requests

API = "https://api.finna.fi/api/v1/search"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}

QUERIES = [
    "juliste", "poster", "taide", "design", "graafinen", "art nouveau",
    "modernismi", "print", "textile", "kuvataide", "mainos", "kansitaide",
]


def _open(rights):
    """True for a license we may reuse with attribution: CC0, PD, CC BY(-SA).
    Excludes NC (non-commercial) and ND (no-derivatives)."""
    r = (rights or "").lower()
    if "nc" in r or "nd" in r:
        return False
    return ("cc0" in r) or ("public domain" in r) or ("pdm" in r) or ("cc by" in r)


def steal(rng):
    params = [
        ("lookfor", rng.choice(QUERIES)),
        ("type", "AllFields"),
        ("limit", "50"),
        ("page", str(rng.randint(1, 10))),
        ("field[]", "title"),
        ("field[]", "images"),
        ("field[]", "imageRights"),
        ("field[]", "id"),
        ("field[]", "institutions"),
        ("filter[]", 'free_online_boolean:"1"'),
    ]
    resp = requests.get(API, params=params, headers=HEAD, timeout=30).json()
    recs = resp.get("records") or []
    rng.shuffle(recs)
    for r in recs:
        imgs = r.get("images") or []
        if not imgs:
            continue
        if not _open((r.get("imageRights") or {}).get("copyright")):
            continue
        insts = r.get("institutions") or []
        museum = (insts[0].get("value") if insts and isinstance(insts[0], dict) else "") or "Finna"
        return {
            "museum": museum,
            "title": r.get("title") or "Untitled",
            "artist": "Unknown",
            "year": "",
            "medium": "",
            "image": "https://api.finna.fi" + imgs[0],
            "url": "https://www.finna.fi/Record/" + (r.get("id") or ""),
        }
    raise RuntimeError("Finna: no usable open image in sample")
