"""Wikimedia Commons. Public-domain paintings, keyless MediaWiki API.

The resilience anchor. Every other source depends on a museum CDN that can
start blocking the GitHub Actions runner's datacenter IP (AIC and Harvard both
died that way — Cloudflare 403 / rate-limit 429, and even the wsrv proxy is
blocked for them). Commons serves its images from upload.wikimedia.org, which
is built to be hot-linked from anywhere on earth and does not block datacenter
IPs, so this drawer can always be opened.

We rotate a set of real, populated painting categories (the obvious guesses
like "Still life paintings" are near-empty — paintings live in subcategories),
jump to a random point in each alphabetized category, and take the raw original
file url. We deliberately do NOT ask the API for a pre-sized thumbnail: its
on-the-fly thumbnail renderer intermittently 429s when a proxy fetches it,
while the static original never does. The build's verified() wraps this url in
wsrv.nl to resize it, exactly like every other source.
"""
import re
import string

import requests

API = "https://commons.wikimedia.org/w/api.php"
# A descriptive User-Agent is required by Wikimedia API etiquette; a bare or
# default agent gets throttled to empty bodies.
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}

# Real, populated, painting-heavy categories (verified via categoryinfo).
# PD-Art (PD-old-100) is the ~185k guaranteed-public-domain megacategory.
CATS = [
    "Category:Oil paintings",
    "Category:Landscape paintings",
    "Category:Self-portraits",
    "Category:Portrait paintings of men",
    "Category:Portrait paintings of women",
    "Category:Watercolor paintings",
    "Category:Impressionist paintings",
    "Category:Genre paintings",
    "Category:History paintings",
    "Category:PD-Art (PD-old-100)",
]


def _clean(s):
    """Commons metadata arrives wrapped in HTML and Wikidata QS cruft."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.split(r"\b(?:title|label|date) QS:", s)[0]
    return re.sub(r"\s+", " ", s).strip(' ,"')


def steal(rng):
    """Return one public-domain painting with a raw upload.wikimedia.org image."""
    for cat in rng.sample(CATS, len(CATS)):
        params = {
            "action": "query", "format": "json",
            "generator": "categorymembers", "gcmtitle": cat,
            "gcmtype": "file", "gcmlimit": "30",
            # categorymembers has no random offset, so jump to a random letter
            # in the alphabetized listing, then shuffle what comes back.
            "gcmstartsortkeyprefix": rng.choice(string.ascii_uppercase),
            "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
            "iiextmetadatafilter": "ObjectName|Artist|DateTimeOriginal|License",
        }
        try:
            resp = requests.get(API, params=params, headers=HEAD, timeout=30).json()
        except Exception:  # noqa: BLE001  (throttled/empty body -> try next category)
            continue
        pages = list(resp.get("query", {}).get("pages", {}).values())
        rng.shuffle(pages)
        for info in pages:
            ii = (info.get("imageinfo") or [{}])[0]
            # JPEG only drops SVG/PNG/TIFF diagrams and maps.
            if ii.get("mime") != "image/jpeg" or not ii.get("url"):
                continue
            em = ii.get("extmetadata", {})
            lic = (em.get("License", {}).get("value", "") or "").lower()
            # PD/CC0 only: the big painting categories carry a minority of
            # modern user-photographed uploads under CC-BY-SA.
            if not (lic.startswith("pd") or lic == "cc0"):
                continue
            title = _clean(em.get("ObjectName", {}).get("value", "")) or \
                info["title"].replace("File:", "").rsplit(".", 1)[0]
            return {
                "museum": "Wikimedia Commons",
                "title": title[:140],
                "artist": _clean(em.get("Artist", {}).get("value", "")) or "Unknown",
                "year": _clean(em.get("DateTimeOriginal", {}).get("value", "")),
                "medium": cat.replace("Category:", "").lower(),
                "image": ii["url"],  # raw original; wsrv resizes it
                "url": ii.get("descriptionurl", ""),
            }
    raise RuntimeError("Commons: no usable public-domain painting found")
