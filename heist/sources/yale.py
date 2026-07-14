"""Yale (LUX). Keyless Linked Art search (lux.collections.yale.edu).

LUX aggregates the Yale Center for British Art, the Yale University Art Gallery
and more. We search for objects with a digital image, open the object, derive
its IIIF manifest from the thumbnail access point, and REQUIRE the manifest's
rights to be CC0 before using it. The image comes from the stable
images.collections.yale.edu IIIF service, NOT the thumbnail access point (which
is a 60-second signed S3 url that can't be hot-linked).
"""
import json

import requests

HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
SEARCH = "https://lux.collections.yale.edu/api/search/item"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
QUERIES = ["painting", "landscape", "portrait", "still life", "watercolor", "seascape"]


def _find_service(node, found):
    """Walk the manifest for the first Yale IIIF image service id."""
    if found[0]:
        return
    if isinstance(node, dict):
        svc = node.get("service")
        if svc:
            svc = svc if isinstance(svc, list) else [svc]
            sid = svc[0].get("@id") or svc[0].get("id")
            if sid and "images.collections.yale.edu" in sid:
                found[0] = sid
                return
        for v in node.values():
            _find_service(v, found)
    elif isinstance(node, list):
        for v in node:
            _find_service(v, found)


def steal(rng):
    s = requests.Session()
    s.headers.update(HEAD)
    q = {"AND": [{"text": rng.choice(QUERIES)}, {"hasDigitalImage": 1}]}
    res = s.get(SEARCH, params={"q": json.dumps(q), "page": rng.randint(1, 20)},
                timeout=30).json()
    items = res.get("orderedItems") or []
    rng.shuffle(items)
    for it in items[:12]:
        obj = s.get(it["id"], timeout=30).json()
        man = None
        for rep in obj.get("representation", []):
            for ds in rep.get("digitally_shown_by", []):
                for ap in ds.get("access_point", []):
                    u = ap.get("id", "")
                    if "/thumbnail/" in u:
                        man = "https://manifests.collections.yale.edu/" + u.split("/thumbnail/")[-1]
        if not man:
            continue
        m = s.get(man, timeout=25).json()
        if m.get("rights") != CC0:  # CC0 only
            continue
        found = [None]
        _find_service(m, found)
        if not found[0]:
            continue
        label = m.get("label") or {}
        title = (label.get("en") or ["Untitled"])[0]
        artist = "Unknown"
        for pr in (obj.get("produced_by") or {}).get("part", []) or []:
            for a in pr.get("carried_out_by", []):
                artist = a.get("_label", artist)
        return {
            "museum": "Yale",
            "title": title,
            "artist": artist,
            "year": "",
            "medium": "",
            "image": found[0] + "/full/880,/0/default.jpg",
            "url": it["id"],
        }
    raise RuntimeError("Yale: no CC0 image found in sample")
