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
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

# Run from anywhere: put the repo root on the path so `heist` imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vet pool images with the exact same color test the build enforces at send
# time, so nothing curated here gets dropped later for being black-and-white.
from heist.build_issue import is_color  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
API = "https://www.loc.gov/photos/"
# Color-rich categories only. Plain "photograph" topics are overwhelmingly
# black-and-white, which the thief no longer fences.
# Interleaved so the pool stays varied: photochrom landscapes and park
# posters sit alongside the WPA/circus/travel poster runs.
TOPICS = [
    "travel poster", "photochrom", "wpa poster", "national park poster",
    "circus poster", "movie poster", "railroad poster", "theater poster",
    "chromolithograph", "world's fair poster", "tourism poster",
    "color lithograph", "vaudeville poster", "advertising poster",
    "opera poster", "exhibition poster", "ballet poster",
    "federal art project poster",
]
SKIP_TITLE = re.compile(r"unidentified|^\[?group |portrait of an? unidentified", re.I)
BAD_IMG = ("/static/", ".svg", ".gif")
MIN_AREA = 500 * 400
TARGET = 350


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


def search(topic, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(API, params={"q": topic, "fo": "json", "c": 150},
                             headers=UA, timeout=40)
            r.raise_for_status()
            return r.json().get("results") or []
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    print(f"  ! {topic}: search failed: {last}")
    return []


def vet(item, topic):
    title = (item.get("title") or "").strip(". ")
    if not title or SKIP_TITLE.search(title):
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
    pool, seen = [], set()
    for topic in TOPICS:
        if len(pool) >= TARGET:
            break
        results = search(topic)
        added = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            for got in ex.map(lambda it: vet(it, topic), results):
                if got and got["image"] not in seen:
                    seen.add(got["image"])
                    pool.append(got)
                    added += 1
        print(f"  {topic:28} +{added}  (pool={len(pool)})")
    pool.sort(key=lambda x: x["image"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {len(pool)} color items -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
