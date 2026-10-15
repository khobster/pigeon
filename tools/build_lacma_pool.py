"""Build heist/lacma_pool.json from the LACMA online collection.

LACMA (Los Angeles County Museum of Art) releases its public-domain images
"free of charge and for use without restriction" (Public Domain Mark), but it
has no search API and no open-data dump — so, like the National Gallery of Art
and the Library of Congress vault, we pre-build a committed pool and the source
module just draws from it.

The collection site (collections.lacma.org) is a Next.js app. Every object page
carries a `publicDomain` flag in its payload and a clean <dt>/<dd> metadata list
(Title, Date Made, Medium, Classification, Collecting Area), and the images live
on collections-images.lacma.org (AWS CloudFront + S3), which is reachable from a
datacenter IP — so the build's verified() can fetch them at send time.

Object IDs are enumerable from the sitemaps listed in robots.txt. We sample them,
keep only public-domain works that have an image, and BIAS the pool toward the
heist's "cool / modern / graphic" taste: anything made from 1850 on, plus any
design-forward form (prints, drawings, photographs, costumes, textiles,
decorative arts) of any age. Ancient manuscripts / sculpture / ceramics that
aren't design-forward are dropped — that is exactly the old-timey loot we want
LESS of. The color gate in build_issue still runs at send time.

Run from any machine (collections.lacma.org isn't IP-blocked):
    python tools/build_lacma_pool.py            # full build
    python tools/build_lacma_pool.py --test 40  # quick sample, writes nothing
"""
import concurrent.futures as cf
import html
import json
import random
import re
import sys
from pathlib import Path

import requests

SITE = "https://collections.lacma.org"
IMG = "https://collections-images.lacma.org"
OUT = Path(__file__).resolve().parent.parent / "heist" / "lacma_pool.json"
UA = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}

FETCH_BUDGET = 18000   # object pages to pull (≈13% kept after the modern/design filter)
CAP = 2500             # committed-pool ceiling, modern-first
WORKERS = 12

# Design-forward classifications: "cool / graphic" regardless of age. Everything
# else must be dated 1850+ to make the pool (keeps out ancient ceramics/sculpture).
DESIGN_FORWARD = re.compile(
    r"print|drawing|photograph|costume|textile|decorative|poster|design|graphic",
    re.I,
)

_DT_DD = re.compile(r'<dt class="font-lacma">([^<]+)</dt><dd[^>]*>(.*?)</dd>', re.S)
_TAGS = re.compile(r"<[^>]+>")
_PD = re.compile(r'\\"publicDomain\\":1')
_IMG_DESKTOP = re.compile(r'(https://collections-images\.lacma\.org/images/\d+/[\w.-]+?-desktop\.jpg)')
_IMG_WEBP = re.compile(r'(https://collections-images\.lacma\.org/images/\d+/[\w.-]+?-primary\.webp)')
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
_CENTURY = re.compile(r"(\d{1,2})(?:st|nd|rd|th) century", re.I)


def _text(v):
    return html.unescape(_TAGS.sub(" ", v)).strip(" ,")


def _era(date_made):
    """A rough latest-year for modern-biasing. '18th century' -> 1750."""
    years = [int(y) for y in _YEAR.findall(date_made)]
    if years:
        return max(years)
    c = _CENTURY.search(date_made)
    return (int(c.group(1)) - 1) * 100 + 50 if c else 0


def parse(session, oid):
    try:
        r = session.get(f"{SITE}/object/{oid}", timeout=25)
        r.raise_for_status()
        html_text = r.text
    except Exception:  # noqa: BLE001
        return None
    if not _PD.search(html_text):
        return None  # not public domain
    m = _IMG_DESKTOP.search(html_text) or _IMG_WEBP.search(html_text)
    if not m:
        return None  # no usable image
    fields = {k.strip().lower(): _text(v) for k, v in _DT_DD.findall(html_text)}
    title = fields.get("title") or "Untitled"
    date = fields.get("date made") or ""
    classification = fields.get("classification") or fields.get("collecting area") or ""
    artist = next((fields[k] for k in fields if "artist" in k or "maker" in k), "")
    if not artist:
        # <title> is "Artist, Title, Year | LACMA Collections"
        head = html.unescape(re.sub(r"\s*\|\s*LACMA Collections.*$", "", re.search(
            r"<title>(.*?)</title>", html_text, re.S).group(1))) if "<title>" in html_text else ""
        artist = head.split(",")[0].strip() if head else "Unknown"
    era = _era(date)
    design = bool(DESIGN_FORWARD.search(classification))
    if era < 1850 and not design:
        return None  # old-timey, not design-forward -> skip
    return {
        "museum": "the Los Angeles County Museum of Art",
        "title": title[:140],
        "artist": artist or "Unknown",
        "year": date,
        "medium": fields.get("medium", ""),
        "image": m.group(1),
        "url": f"{SITE}/object/{oid}",
        "_era": era,
        "_design": design,
    }


def gather_ids(session):
    ids = []
    robots = session.get(f"{SITE}/robots.txt", timeout=25).text
    maps = re.findall(r"Sitemap:\s*(\S+)", robots) or [f"{SITE}/sitemap/{n}.xml" for n in range(14)]
    for url in maps:
        try:
            ids += re.findall(r"/object/(\d+)", session.get(url, timeout=30).text)
        except Exception as e:  # noqa: BLE001
            print(f"  sitemap {url} err {e}")
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def main():
    test_n = 0
    if "--test" in sys.argv:
        test_n = int(sys.argv[sys.argv.index("--test") + 1])

    session = requests.Session()
    session.headers.update(UA)

    ids = gather_ids(session)
    print(f"{len(ids)} object ids across sitemaps")
    random.seed(0)
    random.shuffle(ids)
    budget = test_n or FETCH_BUDGET
    ids = ids[:budget]

    kept = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(parse, session, oid): oid for oid in ids}
        for fut in cf.as_completed(futs):
            done += 1
            rec = fut.result()
            if rec:
                kept.append(rec)
            if done % 500 == 0:
                print(f"  {done}/{len(ids)} fetched, {len(kept)} kept")
    print(f"fetched {done}, kept {len(kept)} public-domain design/modern works")

    # modern-first: latest era wins, design-forward breaks ties
    kept.sort(key=lambda x: (x["_era"], x["_design"]), reverse=True)
    chosen = kept[:CAP]
    modern = sum(1 for x in chosen if x["_era"] >= 1900)
    design = sum(1 for x in chosen if x["_design"])
    for x in chosen:
        x.pop("_era", None)
        x.pop("_design", None)

    if test_n:
        print(f"\n--- TEST ({len(chosen)} items, would NOT write) ---")
        for x in chosen[:40]:
            print(f"  [{x['year']}] {x['title'][:55]}  <{x['medium'][:30]}>")
        return
    OUT.write_text(json.dumps(chosen, indent=0))
    print(f"wrote {len(chosen)} items to {OUT}  ({modern} dated 1900+, {design} design-forward)")


if __name__ == "__main__":
    main()
