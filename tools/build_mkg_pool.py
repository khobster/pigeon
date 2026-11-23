"""Curate the MKG Hamburg (Museum fuer Kunst und Gewerbe) pool: Jugendstil
posters (Mucha, Klimt, Moser), Japanese woodblock prints (Hokusai,
Hiroshige, Kuniyoshi) and Art Nouveau glass and ceramics (Tiffany, Galle).

MKG's API is gone and its new site has no data feed, but it published a CC0
LIDO-XML dump of its collection on GitHub (a 2017 snapshot). We keep records
marked public domain ("gemeinfrei") whose image is CC0 or CC BY, where every
named person died before 1956. Images come from digiCult at 1200px on the
long side (the ceiling), so we also require at least 600px of width, the
bag's minimum. Titles stay in German, as the museum gives them.

    python tools/build_mkg_pool.py heist/mkg_pool.json
"""
import io
import json
import os
import random
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heist.build_issue import inoffensive, is_color, secular  # noqa: E402

DUMP = "https://raw.githubusercontent.com/MKGHamburg/MKGCollectionOnlineLIDO_XML/master/mkg_lido-dC.web_{n}.xml"
NS = {"lido": "http://www.lido-schema.org"}
L = "{http://www.lido-schema.org}"
HEAD = {"User-Agent": "the-heist-newsletter/1.0 (https://heist.arugulamotors.com)"}
DEATH_BEFORE = 1956
EROTIC = re.compile(r"(?i)shunga|erotis|makura-?e|liebesszene")
PER_ARTIST = 8
SEED = 20261123


def records(path):
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != L + "lido":
            continue
        t = lambda q: el.findtext(q, namespaces=NS)  # noqa: E731
        cls = {}
        for c in el.findall(".//lido:classification", NS):
            cls.setdefault(c.get(L + "type"), []).append(c.findtext("lido:term", namespaces=NS) or "")
        people, years = [], []
        for e in el.findall(".//lido:event", NS):
            for a in e.findall(".//lido:actorInRole", NS):
                actor = a.find("lido:actor", NS)
                people.append({"name": a.findtext(".//lido:nameActorSet/lido:appellationValue", namespaces=NS) or "",
                               "person": actor is not None and actor.get(L + "type") == "person",
                               "death": a.findtext(".//lido:vitalDatesActor/lido:latestDate", namespaces=NS)})
            d = e.find("lido:eventDate", NS)
            if d is not None:
                years += [x for x in (d.findtext(".//lido:earliestDate", namespaces=NS),
                                      d.findtext(".//lido:latestDate", namespaces=NS)) if x]
        rs = el.find(".//lido:resourceSet", NS)
        yield {
            "id": t(".//lido:recordWrap/lido:recordID"),
            "title": t(".//lido:titleSet/lido:appellationValue") or "",
            "worktype": [x.text or "" for x in el.findall('.//lido:objectWorkType/lido:term[@lido:pref="preferred"]', NS)],
            "cls": cls,
            "rights": t(".//lido:rightsWorkSet/lido:rightsType/lido:term"),
            "people": people,
            "years": years,
            "image": rs.findtext('lido:resourceRepresentation[@lido:type="provided_image"]/lido:linkResource', namespaces=NS) if rs is not None else None,
            "license": rs.findtext("lido:rightsResource/lido:rightsType/lido:term", namespaces=NS) if rs is not None else None,
        }
        el.clear()


def seam(r):
    """Which drawer of loot a record belongs to, or None."""
    coll = " ".join(r["cls"].get("Sammlung", []))
    kind = " ".join(r["worktype"]).lower()
    style = " ".join(r["cls"].get("Stil", []))
    if "plakat" in kind:
        return "poster"
    if "Ostasien" in coll and "holzschnitt" in kind:
        return "japanese print"
    if "Jugendstil" in style or "Jugendstil" in coll:
        return "jugendstil"
    return None


def eligible(r):
    if r["rights"] != "gemeinfrei" or not r["image"] or not (r["license"] or "").startswith(("CC0", "CC BY")):
        return False
    deaths = [p["death"] for p in r["people"] if p["person"]]
    if any(not d or not d[:4].isdigit() or int(d[:4]) >= DEATH_BEFORE for d in deaths):
        return False  # an unknown or too-recent death date: can't be sure it's free
    hay = " ".join([r["title"]] + sum(r["cls"].values(), []))
    return not EROTIC.search(hay)


def artist(r):
    people = [p["name"] for p in r["people"] if p["person"] and p["name"]]
    if not people:
        return "Unknown"
    last, _, first = people[0].partition(", ")
    return f"{first} {last}".strip() if first else last


def year(r):
    ys = sorted({y[:4] for y in r["years"] if y[:4].isdigit()})
    return ys[0] if len(ys) == 1 else (f"{ys[0]} to {ys[-1]}" if ys else "")


def vet(r):
    if not secular(r["title"]) or not inoffensive(r["title"]):
        return None
    image = r["image"].replace("http://", "https://")
    try:
        g = requests.get(image, headers=HEAD, timeout=60)
        if not g.headers.get("content-type", "").startswith("image/"):
            return None
        w, h = Image.open(io.BytesIO(g.content)).size
        if w < 600 or not is_color(g.content):
            return None
    except Exception:  # noqa: BLE001
        return None
    return {
        "museum": "MKG Hamburg",
        "title": r["title"],
        "artist": artist(r),
        "year": year(r),
        "medium": "",
        "image": image,
        "url": f"https://www.mkg-hamburg.de/en/object/{r['id']}",
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: build_mkg_pool.py <out.json>")
    found = {}
    with tempfile.TemporaryDirectory() as tmp:
        for n in range(3):
            path = os.path.join(tmp, f"{n}.xml")
            with requests.get(DUMP.format(n=n), headers=HEAD, timeout=600, stream=True) as r:
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            for rec in records(path):
                s = seam(rec)
                if s and eligible(rec):
                    found.setdefault(s, []).append(rec)
    rng = random.Random(SEED)
    pool, per = [], {}
    for s, recs in sorted(found.items()):
        rng.shuffle(recs)
        with ThreadPoolExecutor(max_workers=6) as ex:
            got = [p for p in ex.map(vet, recs) if p]
        kept = 0
        for p in got:
            if p["artist"] != "Unknown" and per.get(p["artist"], 0) >= PER_ARTIST:
                continue
            per[p["artist"]] = per.get(p["artist"], 0) + 1
            pool.append(p)
            kept += 1
        print(f"  {s}: {len(recs)} eligible, kept {kept}", flush=True)
    pool.sort(key=lambda x: x["url"])
    with open(sys.argv[1], "w") as f:
        json.dump(pool, f, indent=0, ensure_ascii=False)
    print(f"wrote {len(pool)} MKG works -> {sys.argv[1]}")


if __name__ == "__main__":
    main()
