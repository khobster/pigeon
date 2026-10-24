"""Curate the Paris Musées pool.

Paris Musées (the 14 City of Paris museums: Carnavalet, Petit Palais, the
Musée d'Art Moderne, Cernuschi, Galliera, Maison de Victor Hugo, ...) released
its public-domain collection as CC0 in 2020. Its own API needs a key and its
site is often down ("Service indisponible"), but it mirrored ~326,000 of those
CC0 images to Wikimedia Commons ("Category:Images from Paris Musées"), and
upload.wikimedia.org never blocks the GitHub Actions runner. So we search that
category for the color-rich, graphic seams (posters, shop signs, fans, menus,
Petit Palais and Art Moderne paintings), license- and color-vet every hit, and
write heist/parismusees_pool.json.

    python tools/build_parismusees_pool.py heist/parismusees_pool.json
"""
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com; kevin.murawinski@gmail.com)"}
CAT = 'incategory:"Images_from_Paris_Musées"'
# The mirror is mostly black-and-white Commune caricatures and documentary
# photos, so search the colorful corners instead of sampling the whole thing.
QUERIES = [
    "affiche", "affiche lithographie", "Chéret", "Steinlen", "Toulouse-Lautrec",
    "Mucha", "Delaunay", "Musée d'Art Moderne", "Petit Palais peinture",
    "Petit Palais", "enseigne", "éventail", "menu", "programme théâtre",
    "papier peint", "carte postale", "jouet", "Galliera robe", "costume",
    "Cernuschi peinture", "estampe", "faïence", "Victor Hugo dessin",
    "aquarelle", "gouache", "pochoir", "art nouveau", "art déco",
]
PER_QUERY = 25
# One Cernuschi album of Ming plant paintings alone fills a query; cap each
# artist so the pool reads like fourteen museums, not one sketchbook.
PER_ARTIST = 4
SEARCH_DEPTH = 300
# Paris Musées' CC0 release covers works it holds no rights in, but a stray
# modern poster can carry a later year in its title; keep pre-1931 only.
PD_YEAR = 1930
MUSEUMS = [
    ("Petit Palais", "the Petit Palais"),
    ("Carnavalet", "the Musée Carnavalet"),
    ("Art moderne", "the Musée d'Art Moderne de Paris"),
    ("Art Moderne", "the Musée d'Art Moderne de Paris"),
    ("Cernuschi", "the Musée Cernuschi"),
    ("Galliera", "the Palais Galliera"),
    ("Victor Hugo", "the Maison de Victor Hugo"),
    ("Cognacq-Jay", "the Musée Cognacq-Jay"),
    ("Vie romantique", "the Musée de la Vie romantique"),
    ("Bourdelle", "the Musée Bourdelle"),
]
STAMP = re.compile(r"[,.]?\s*Paris Musées.*$|\s*\(\d{8,}\)\s*$|,?\s*\b(?:PH|QB|G|M\.C\.|AMS|J)[\s.]?[\d.()-]+\S*\s*$")


CODE = re.compile(r"[,.]?\s*\b[A-Z]{1,6}[\s.]?\d[\w.()-]*\s*$|[,.]?\s*\b\d{2,}\.\d[\w.()-]*\s*$")


def tidy_artist(raw):
    """'Steinlen, Théophile Alexandre (Lausanne, 1859 - Paris, 1923)' ->
    'Théophile Alexandre Steinlen'; anonymous makers -> 'Unknown'."""
    a = re.sub(r"\s*\(.*$", "", raw or "").strip(" ,")
    a = re.sub(r"^(?:[ée]diteur|imprimeur)\s+", "", a, flags=re.I)
    a = re.sub(r",\s*(dessinateur|lithographe|graveur|peintre|photographe|sculpteur|ferronnier|imprimeur)\b.*$", "", a, flags=re.I)
    if not a or re.match(r"(anonyme|anonymous|unknown|no machine-readable)", a, re.I):
        return "Unknown"
    if a.count(",") == 1:
        last, first = [x.strip() for x in a.split(",")]
        a = f"{first} {last}"
    return a[:80]


def tidy_title(t):
    t = re.sub(r"^French:\s*", "", t)
    for _ in range(2):
        t = CODE.sub("", t).strip(" ,-")
    return t


def _clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.split(r"\b(?:title|label|date) QS:", s)[0]  # Wikidata template residue
    s = re.sub(r"\s+", " ", s).strip(' ,"')
    return "" if re.fullmatch(r"(?i)unknown( date)?", s) else s


def search(q):
    titles, offset = [], 0
    while offset < SEARCH_DEPTH:
        try:
            r = requests.get(API, params={
                "action": "query", "list": "search", "format": "json",
                "srsearch": f"{CAT} {q} filetype:bitmap", "srnamespace": 6,
                "srlimit": 100, "sroffset": offset}, headers=HEAD, timeout=40).json()
        except Exception as e:  # noqa: BLE001
            print(f"  ! {q}: search failed: {e}")
            break
        hits = r.get("query", {}).get("search", [])
        titles += [h["title"] for h in hits]
        if "continue" not in r:
            break
        offset = r["continue"]["sroffset"]
        time.sleep(0.5)
    return titles


def details(titles):
    out = []
    for i in range(0, len(titles), 50):
        try:
            r = requests.get(API, params={
                "action": "query", "format": "json", "titles": "|".join(titles[i:i + 50]),
                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata"},
                headers=HEAD, timeout=60).json()
        except Exception:  # noqa: BLE001
            continue
        out += list(r.get("query", {}).get("pages", {}).values())
        time.sleep(0.5)
    return out


def museum(text):
    for needle, name in MUSEUMS:
        if needle in text:
            return name
    return "Paris Musées"


def year(text):
    years = [int(y) for y in re.findall(r"\b(1[4-9]\d\d|20\d\d)\b", text or "")]
    return max(years) if years else None


def wsrv(u, w=240):
    return f"https://wsrv.nl/?url={quote(u, safe='')}&w={w}&fit=inside"


def vet(page):
    ii = (page.get("imageinfo") or [{}])[0]
    if ii.get("mime") != "image/jpeg" or not ii.get("url"):
        return None
    if ii.get("width", 0) * ii.get("height", 0) < 600 * 500:
        return None
    em = ii.get("extmetadata", {})
    lic = (em.get("License", {}).get("value", "") or "").lower()
    if not (lic.startswith("pd") or lic == "cc0"):
        return None
    raw = page["title"].replace("File:", "").rsplit(".", 1)[0]
    title = _clean(em.get("ObjectName", {}).get("value", "")) or raw
    title = STAMP.sub("", title).strip(" ,-")
    # "Artist - Title - inv - Museum" style names: keep the title part.
    parts = [p.strip() for p in title.split(" - ")]
    artist = _clean(em.get("Artist", {}).get("value", ""))
    if len(parts) >= 3:
        artist = artist or parts[0]
        title = parts[1]
    if not title or not secular(title) or not inoffensive(title):
        return None
    date = _clean(em.get("DateTimeOriginal", {}).get("value", ""))
    y = year(f"{date} {raw}")
    if y and y > PD_YEAR:
        return None
    try:
        r = requests.get(wsrv(ii["url"]), headers=HEAD, timeout=45)
        if not r.headers.get("content-type", "").startswith("image/") or not is_color(r.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    credit = _clean(em.get("Credit", {}).get("value", ""))
    link = re.search(r"https?://\S*parismuseescollections\S*", credit)
    return {
        "museum": museum(raw + " " + credit),
        "title": tidy_title(title)[:140],
        "artist": tidy_artist(artist),
        "year": date[:40],
        "medium": "",
        "image": ii["url"],
        "url": link.group(0) if link else ii.get("descriptionurl", ""),
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_parismusees_pool.py <out.json>")
    pool, seen, per_artist = [], set(), {}
    for q in QUERIES:
        pages = [p for p in details(search(q)) if p.get("title") not in seen]
        added = 0
        with ThreadPoolExecutor(max_workers=6) as ex:
            for start in range(0, len(pages), 24):
                if added >= PER_QUERY:
                    break
                for page, got in zip(pages[start:start + 24],
                                     ex.map(vet, pages[start:start + 24])):
                    seen.add(page.get("title"))
                    if not got or added >= PER_QUERY:
                        continue
                    who = got["artist"]
                    if who != "Unknown" and per_artist.get(who, 0) >= PER_ARTIST:
                        continue
                    per_artist[who] = per_artist.get(who, 0) + 1
                    pool.append(got)
                    added += 1
        print(f"  {q:26} +{added}  (pool={len(pool)})", flush=True)
    pool.sort(key=lambda x: x["image"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"\nwrote {len(pool)} CC0 Paris Musées works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
