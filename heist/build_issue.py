"""Assemble today's heist, archive it to docs/, and optionally send it.

Usage:
  python -m heist.build_issue                       # build + archive only (dry run)
  python -m heist.build_issue --send                # build + archive + send to the list
  python -m heist.build_issue --test you@email.com  # build + send to one address only
"""
import random
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

from engine.render import render
from heist.sources import met, aic, cleveland, smk, si, harvard, chunklet, loc, lam

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARCHIVE_URL = "https://heist.arugulamotors.com/"
HEADER_WEB = "assets/header.png"


def img(url, width=1120):
    """Serve artwork through the wsrv.nl image CDN: one consistent host,
    proper headers, resized payloads. Six museums' web servers all behave
    differently in email clients (Apple Mail refused Harvard's redirects
    and Smithsonian's bare query urls on 2026-06-06); this makes them
    uniform. Width 1120 = retina-sharp at the 560px layout."""
    if not url:
        return ""
    if url.startswith(ARCHIVE_URL):
        return url  # already self-hosted on our domain
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={width}&fit=inside"


def localize(url, today, tag):
    """Download an image into the archive and serve it from our own domain.
    Harvard rate-limits shared proxy fetchers (wsrv got 429s; Apple Mail's
    privacy relay gets the same treatment, hence question marks on iOS),
    so their art physically leaves the building at build time."""
    art_dir = DOCS / "assets" / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    name = f"{today.isoformat()}-{tag}.jpg"
    resp = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0 (pigeon-heist)"})
    resp.raise_for_status()
    (art_dir / name).write_bytes(resp.content)
    return f"{ARCHIVE_URL}assets/art/{name}"


def build_haul(rng, today, extras_wanted=5):
    """One hero piece plus a few companions from the other museums."""
    museums = [met, aic, cleveland, smk] + [m for m in (si, harvard) if m.available()]
    start = today.toordinal() % len(museums)
    rotation = museums[start:] + museums[:start]

    hero, last = None, None
    for museum in rotation:
        try:
            hero = museum.steal(rng)
            break
        except Exception as e:  # noqa: BLE001
            last = e
    if not hero:
        raise RuntimeError(f"every museum was locked tonight: {last}")

    extras = []
    for museum in rotation * 2:  # loop twice so one museum can contribute two
        if len(extras) >= extras_wanted:
            break
        try:
            piece = museum.steal(rng)
            if piece["image"] != hero["image"] and piece["image"] not in [e["image"] for e in extras]:
                extras.append(piece)
        except Exception as e:  # noqa: BLE001
            print(f"  [skip extra] {museum.__name__}: {e}")
    return hero, extras


EXTRA_ROW = """
  <tr><td align="center" style="padding:8px 0 10px;">
    <a href="{url}" style="text-decoration:none;"><img src="{image}" alt="{title}" width="440" style="display:block; width:80%; max-width:440px; height:auto; border:0;"></a>
  </td></tr>
  <tr><td align="center" style="padding:0 0 18px; font-family:Helvetica, Arial, sans-serif; font-size:12px; color:#999999; line-height:1.5;">
    <strong style="color:#555555;">{title}</strong><br>{artist}{year_part} · <a href="{url}" style="color:#999999;">{museum}</a>
  </td></tr>"""


def extras_html(extras):
    if not extras:
        return ""
    rows = ['''
  <tr><td style="padding:0 0 8px; font-family:Helvetica, Arial, sans-serif; font-size:13px; font-weight:bold; color:#555555;">
    also in the bag:
  </td></tr>''']
    for e in extras:
        title = e["title"] if len(e["title"]) <= 80 else e["title"][:80].rsplit(" ", 1)[0] + "..."
        rows.append(EXTRA_ROW.format(
            url=e["url"], image=img(e["image"], width=880), title=title, artist=e["artist"],
            year_part=f", {e['year']}" if e["year"] else "", museum=e["museum"],
        ))
    rows.append('  <tr><td style="padding:0 0 22px;"></td></tr>')
    return "".join(rows)


def try_steal(source, rng):
    """Optional sections fail soft: a thin issue still ships."""
    try:
        return source.steal(rng)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] {source.__name__}: {e}")
        return {}


# Generic words that make dull loot. The manifest wants the rare ones.
SUBJECT_STOP = {
    "the", "from", "with", "also", "known", "series", "untitled", "study",
    "view", "scene", "portrait", "madame", "monsieur", "saint", "still",
    "life", "young", "woman", "man", "girl", "boy", "head", "figure",
    "landscape", "after", "called", "plate", "number", "between", "design",
}


def keyword(text):
    """The most distinctive word in a title: longest capitalized word that
    is not generic catalog language. The manifest, one word per item."""
    words = re.findall(r"[A-Za-z][A-Za-z']*", text or "")
    def norm(w):
        w = w.lower()
        return w[:-2] if w.endswith("'s") else w
    caps = [w for w in words if w[0].isupper() and norm(w) not in SUBJECT_STOP and len(w) >= 4]
    pool = caps or [w for w in words if len(w) >= 5 and norm(w) not in SUBJECT_STOP]
    return max(pool, key=len) if pool else ""


def build_subject(haul, extras, line, vault, hideout):
    texts = (
        [haul["title"] or haul["artist"]]
        + [e["title"] for e in extras]
        + [line.get("work") or line.get("attribution", "")]
        + [vault.get("title") or vault.get("topic", "")]
        + [hideout.get("name", "")]
    )
    words, seen = [], set()
    for t in texts:
        w = keyword(t)
        if w and w.lower() not in seen:
            words.append(w)
            seen.add(w.lower())
    while len(", ".join(words)) > 75 and len(words) > 3:
        words.pop(1)  # shed loot from the middle, keep the hero and the hideout
    return ", ".join(words) or "last night's haul"


def build(today=None):
    today = today or date.today()
    rng = random.Random(today.isoformat())

    haul, extras = build_haul(rng, today)
    for i, piece in enumerate([haul] + extras):
        if "ids.lib.harvard.edu" in piece["image"]:
            try:
                piece["image"] = localize(piece["image"], today, f"harvard{i}")
            except Exception as e:  # noqa: BLE001
                print(f"  [localize fail, serving direct] {e}")
    line = try_steal(chunklet, rng)
    vault = try_steal(loc, rng)
    hideout = try_steal(lam, rng)

    context = {
        "date_pretty": today.strftime("%B %-d, %Y"),
        "preheader": f"Last night's haul: {haul['title']}",
        "archive_url": ARCHIVE_URL,
        "haul_image": img(haul["image"]),
        "haul_title": haul["title"],
        "haul_artist": haul["artist"],
        "haul_year": haul["year"],
        "haul_medium": haul["medium"],
        "haul_museum": haul["museum"],
        "haul_url": haul["url"],
        "extras_html": extras_html(extras),
        "line_text": line.get("text", ""),
        "line_attr": line.get("attribution") or "lifted from somewhere in the canon",
        "line_summary": line.get("summary", ""),
        "vault_image": img(vault.get("image", "")),
        "vault_title": vault.get("title", ""),
        "vault_date": vault.get("date", ""),
        "vault_url": vault.get("url", ""),
        "lam_name": hideout.get("name", ""),
        "lam_blurb": hideout.get("blurb", ""),
        "lam_image": img(hideout.get("image", "")),
        "lam_url": hideout.get("url", ""),
    }

    template = (ROOT / "heist" / "template.html").read_text()
    email_html = render(template, {**context, "header_src": ARCHIVE_URL + HEADER_WEB})
    archive_html = render(template, {**context, "header_src": "../" + HEADER_WEB})

    subject = build_subject(haul, extras, line, vault, hideout)
    return subject, email_html, archive_html, today


def write_archive(archive_html, today):
    issues_dir = DOCS / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    (issues_dir / f"{today.isoformat()}.html").write_text(archive_html)

    issues = sorted(issues_dir.glob("*.html"), reverse=True)

    def pretty(stem):
        try:
            return date.fromisoformat(stem).strftime("%B %-d, %Y")
        except ValueError:
            return stem

    items = "\n".join(
        f'      <li><a href="issues/{p.name}">{pretty(p.stem)}</a></li>' for p in issues
    )
    n = len(issues)
    count_line = f"{n} heist{'s' if n != 1 else ''} and counting"
    index = (ROOT / "docs" / "_index_template.html").read_text()
    (DOCS / "index.html").write_text(
        index.replace("{{count_line}}", count_line).replace("{{issue_list}}", items)
    )
    print(f"archived issue {today.isoformat()} ({len(issues)} total)")


def main():
    subject, email_html, archive_html, today = build()
    write_archive(archive_html, today)
    if "--test" in sys.argv:
        from engine.send import send_issue

        to = sys.argv[sys.argv.index("--test") + 1]
        send_issue(subject, email_html, recipients=[to])
        print(f"test: sent '{subject}' to {to} only")
    elif "--send" in sys.argv:
        from engine.send import send_issue

        n = send_issue(subject, email_html)
        print(f"sent '{subject}' to {n} subscriber(s)")
    else:
        print(f"dry run: '{subject}' built but not sent")


if __name__ == "__main__":
    main()
