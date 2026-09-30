"""Europeana: one API over 3,000+ European institutions — museums, national
libraries, archives. A single integration that behaves like dozens of sources,
which is why it is worth a key. Free key (EUROPEANA_KEY); the source is inert
until one is configured, so a missing key just drops it from the rotation.

We restrict to openly-licensed images (reusability=open covers CC0, Public
Domain and CC-BY, all of which we may show with the credit we already print),
rotate an eclectic set of queries away from plain paintings, and jump to a
random page for day-to-day variety. edmIsShownBy is the full digital object;
edmPreview is the fallback thumbnail. The build's verified() proxies and resizes
whatever host the provider uses, and drops anything that will not fetch, so a
provider that blocks datacenter IPs simply falls through to the next candidate.
"""
import re

import requests

from engine.common import EUROPEANA_KEY

# edmIsShownBy is often a viewer/landing page (returns HTML/JSON, not an image),
# which is why Europeana contributed nothing at first. Take it only when it is a
# direct image file; otherwise fall back to edmPreview, Europeana's own thumbnail
# proxy, which always resolves to a real JPEG.
_DIRECT_IMAGE = re.compile(r"\.(jpe?g|png|tiff?)(\?|$)", re.I)

API = "https://api.europeana.eu/record/v2/search.json"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}

# Eclectic subjects and mediums, steered away from generic paintings so the
# breadth of the aggregator actually shows up as posters, prints and ephemera.
QUERIES = [
    "poster", "ukiyo-e", "woodcut", "art nouveau", "art deco", "lithograph",
    "chromolithograph", "botanical", "textile", "ceramic", "kimono", "fresco",
    "illustration", "colour engraving", "folk art", "costume", "fan", "mask",
    "stained glass", "mosaic", "fashion plate", "tapestry",
]


def available():
    return bool(EUROPEANA_KEY)


def _first(item, *keys):
    for k in keys:
        v = item.get(k)
        if isinstance(v, list) and v:
            return v[0]
        if isinstance(v, str) and v:
            return v
    return ""


def steal(rng):
    if not EUROPEANA_KEY:
        raise RuntimeError("No EUROPEANA_KEY configured")
    q = rng.choice(QUERIES)
    params = {
        "wskey": EUROPEANA_KEY,
        "query": q,
        "qf": "TYPE:IMAGE",
        "reusability": "open",
        "media": "true",
        "rows": 48,
        # Deep paging without a cursor is capped at start+rows<=1000; a random
        # start inside that window is plenty for variety.
        "start": rng.randint(1, 950),
        "profile": "standard",
    }
    resp = requests.get(API, params=params, headers=HEAD, timeout=30).json()
    items = resp.get("items") or []
    rng.shuffle(items)
    for it in items:
        shown = _first(it, "edmIsShownBy")
        image = shown if (shown and _DIRECT_IMAGE.search(shown)) else _first(it, "edmPreview")
        if not image:
            continue
        provider = _first(it, "dataProvider", "edmDataProvider")
        # Build the record URL from the item id, NOT guid: guid embeds our wskey
        # as a utm_campaign param (a key leak in every link) and sometimes points
        # off to a raw Wikidata entity. id looks like "/628/Pb_102090".
        eid = it.get("id") or ""
        return {
            # Many Europeana holders are obscure digitization outfits; "via
            # Europeana" gives the odd institution name context and legitimacy.
            "museum": (f"{provider}, via Europeana" if provider else "Europeana"),
            "title": _first(it, "title") or "Untitled",
            "artist": _first(it, "dcCreator") or "Unknown",
            "year": _first(it, "year"),
            "medium": q,  # the query is a usable medium/subject hint for bucketing
            "image": image,
            "url": (f"https://www.europeana.eu/item{eid}" if eid else "https://www.europeana.eu"),
        }
    raise RuntimeError("Europeana: no usable image in sample")
