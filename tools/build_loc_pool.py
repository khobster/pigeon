"""Curate the color Library of Congress pool used by From the Vault.

loc.gov sits behind Cloudflare, which 403s the GitHub Actions runner's
datacenter IP, so the daily build cannot search loc.gov live. This script
runs from a non-blocked IP (a normal laptop), searches the color-rich
categories, color-vets every candidate, and writes heist/loc_pool.json. The
build then draws the Vault from that committed pool, so the section is always
present and always in color.

    python tools/build_loc_pool.py heist/loc_pool.json

Re-run whenever you want to refresh or grow the pool.
"""
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

# Run from anywhere: put the repo root on the path so `heist` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vet pool images with the exact same color and content tests the build
# enforces at send time, so nothing curated here gets dropped later (or, for
# the racist / colonial-spectacle screen, ever lands in the pool at all).
from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
API = "https://www.loc.gov/photos/"
# Color-rich categories only. Plain "photograph" topics are overwhelmingly
# black-and-white, which the thief no longer fences. The drawer used to be just
# seven topics (the old 350-item target filled up before the rest were ever
# searched), with photochroms dominated by one Austro-Hungarian series, so the
# Vault felt like Dalmatia and circus posters every day. Now every topic gets
# an equal capped share and no single place can flood a topic.
TOPICS = [
    "photochrom", "prokudin-gorskii", "kodachrome", "fsa owi color",
    "wpa poster", "national park poster", "circus poster", "magic poster",
    "theater poster", "movie poster", "railroad poster", "travel poster",
    "world's fair poster", "bicycle poster", "art nouveau poster",
    "world war poster", "advertising poster", "panoramic map", "pictorial map",
    "japanese print", "chromolithograph", "color lithograph", "cigar label",
    "fruit crate label", "seed catalog", "sheet music cover", "fashion plate",
    "baseball card", "political cartoon color",
]
# Rights: anything dated after the US public-domain line must come from a
# federal program (federal work = public domain), e.g. WPA posters, FSA/OWI
# Kodachromes, national park posters. Undated items pass, as before.
PD_YEAR = 1930
FEDERAL = {"wpa poster", "national park poster", "fsa owi color", "kodachrome"}
PER_TOPIC = 22        # equal share per topic so no category owns the drawer
PER_PLACE = 4         # max items per country ("..., Dalmatia, Austro-Hungary]")
PAGES = 3             # search deeper than page one, where series cluster
SKIP_TITLE = re.compile(r"unidentified|^\[?group |portrait of an? unidentified", re.I)
BAD_IMG = ("/static/", ".svg", ".gif")
MIN_AREA = 500 * 400


def best_image(urls):
    best, ba = None, 0
    for u in urls or []:
        b = u.split("#")[0]
        if not b.lower().endswith((".jpg", ".jpeg")):
            continue
        if any(x in b for x in BAD_IMG):
            continue
        w = re.search(r"[#&]w=(\d+)", u)
        h = re.search(r"[#&]h=(\d+)", u)
        a = (int(w.group(1)) if w else 0) * (int(h.group(1)) if h else 0)
        if a > ba:
            best, ba = b, a
    return best, ba


def wsrv(u, w=240):
    return f"https://wsrv.nl/?url={quote(u, safe='')}&w={w}&fit=inside"


def search_page(topic, page, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(API, params={"q": topic, "fo": "json", "c": 100, "sp": page},
                             headers=UA, timeout=40)
            r.raise_for_status()
            return r.json().get("results") or []
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    print(f"  ! {topic} p{page}: search failed: {last}")
    return []


def search(topic):
    results = []
    for page in range(1, PAGES + 1):
        got = search_page(topic, page)
        results += got
        if len(got) < 100:
            break
    # Shuffle (seeded, so reruns are stable) to break up catalog-order series.
    random.Random(topic).shuffle(results)
    return results


def place(title):
    """The trailing country in a catalog title, e.g. 'Austro-Hungary'."""
    m = re.search(r",\s*([^,\[\]]+)\]?$", title)
    return m.group(1).strip().lower() if m else None


def year(date):
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", date or "")
    return int(m.group(1)) if m else None


def vet(item, topic):
    title = (item.get("title") or "").strip(". ")
    if not title or SKIP_TITLE.search(title):
        return None
    if not secular(title) or not inoffensive(title):
        return None
    # Collection-level records ("Posters: Artist Posters") aren't a single find.
    if "collection" in (item.get("original_format") or []):
        return None
    y = year(item.get("date"))
    if y and y > PD_YEAR and topic not in FEDERAL:
        return None
    image, area = best_image(item.get("image_url"))
    if not image or area < MIN_AREA:
        return None
    try:
        r = requests.get(wsrv(image), headers=UA, timeout=45)
        if not r.headers.get("content-type", "").startswith("image/"):
            return None
        if not is_color(r.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return {
        "title": title,
        "date": item.get("date") or "",
        "image": image,
        "url": item.get("id") or item.get("url") or "https://www.loc.gov",
        "topic": topic,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_loc_pool.py <out.json>")
    pool, seen, places = [], set(), {}
    for topic in TOPICS:
        results = search(topic)
        added = 0
        # Vet in small batches and stop once this topic has its share.
        with ThreadPoolExecutor(max_workers=8) as ex:
            for start in range(0, len(results), 24):
                if added >= PER_TOPIC:
                    break
                batch = results[start:start + 24]
                for got in ex.map(lambda it: vet(it, topic), batch):
                    if not got or got["image"] in seen or added >= PER_TOPIC:
                        continue
                    where = place(got["title"])
                    if where and places.get(where, 0) >= PER_PLACE:
                        continue
                    seen.add(got["image"])
                    if where:
                        places[where] = places.get(where, 0) + 1
                    pool.append(got)
                    added += 1
        print(f"  {topic:28} +{added}  (pool={len(pool)})")
    pool.sort(key=lambda x: x["image"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {len(pool)} color items -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
