"""Assemble today's heist, archive it to docs/, and optionally send it.

Usage:
  python -m heist.build_issue                       # build + archive only (dry run)
  python -m heist.build_issue --send                # build + archive + send to the list
  python -m heist.build_issue --test you@email.com  # build + send to one address only
"""
import json
import random
import re
import sys
import time
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


UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"}
OUTBOX = ROOT / ".outbox.json"


def img(url, width=1120):
    """The wsrv.nl image CDN: one consistent host, proper headers, resized
    payloads. Width 1120 = retina-sharp at the 560px layout."""
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={width}&fit=inside"


def probe_ok(url):
    """True if the URL serves an actual image to a normal client right now."""
    try:
        r = requests.get(url, timeout=25, headers=UA, stream=True)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
        r.close()
        return ok
    except Exception:  # noqa: BLE001
        return False


def localize(url, today, tag):
    """Download an image into the archive and serve it from our own domain.
    Retries with backoff: Harvard 429s datacenter IPs (it cost us the
    2026-06-07 issue), so the GitHub runner may need a few polite tries."""
    art_dir = DOCS / "assets" / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(4):
        try:
            resp = requests.get(url, timeout=45, headers=UA)
            resp.raise_for_status()
            ext = ".png" if "png" in resp.headers.get("content-type", "") else ".jpg"
            name = f"{today.isoformat()}-{tag}{ext}"
            (art_dir / name).write_bytes(resp.content)
            return f"{ARCHIVE_URL}assets/art/{name}"
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(12 * (attempt + 1))
    raise RuntimeError(f"could not localize: {last}")


def verified(url, today, tag):
    """Return a URL proven to serve this image to email clients, or raise.
    Ladder: CDN-wrapped -> direct -> downloaded and self-hosted. Origins
    differ: artic.edu blocks the CDN, Harvard rate-limits every shared
    fetcher on earth including Apple Mail's privacy relay. A piece whose
    image cannot be proven gets dropped; the manifest never lists loot
    the thief could not carry out."""
    if not url:
        raise RuntimeError("no image url")
    if "ids.lib.harvard.edu" not in url:  # Harvard goes straight to self-hosting
        proxied = img(url)
        if probe_ok(proxied):
            return proxied
        if probe_ok(url):
            return url
    return localize(url, today, tag)


def build_haul(rng, today, extras_wanted=5):
    """One hero piece plus a few companions from the other museums."""
    museums = [met, aic, cleveland, smk] + [m for m in (si, harvard) if m.available()]
    start = today.toordinal() % len(museums)
    rotation = museums[start:] + museums[:start]

    hero, last = None, None
    for museum in rotation:
        try:
            candidate = museum.steal(rng)
            candidate["image"] = verified(candidate["image"], today, "haul")
            hero = candidate
            break
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  [hero fell through] {museum.__name__}: {e}")
    if not hero:
        raise RuntimeError(f"every museum was locked tonight: {last}")

    extras, seen = [], {hero["image"]}
    for museum in rotation * 2:  # loop twice so one museum can contribute two
        if len(extras) >= extras_wanted:
            break
        try:
            piece = museum.steal(rng)
            if piece["image"] in seen:
                continue
            seen.add(piece["image"])
            piece["image"] = verified(piece["image"], today, f"extra{len(extras)}")
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
            url=e["url"], image=e["image"], title=title, artist=e["artist"],
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
    line = try_steal(chunklet, rng)

    vault = try_steal(loc, rng)
    if vault:
        try:
            vault["image"] = verified(vault["image"], today, "vault")
        except Exception as e:  # noqa: BLE001
            print(f"  [vault image unprovable, section dropped] {e}")
            vault = {}

    hideout = try_steal(lam, rng)
    if hideout.get("image"):
        try:
            hideout["image"] = verified(hideout["image"], today, "lam")
        except Exception:  # noqa: BLE001
            hideout["image"] = ""  # the hideout survives without a photo

    context = {
        "date_pretty": today.strftime("%B %-d, %Y"),
        "preheader": f"Last night's haul: {haul['title']}",
        "archive_url": ARCHIVE_URL,
        "haul_image": haul["image"],
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
        "vault_image": vault.get("image", ""),
        "vault_title": vault.get("title", ""),
        "vault_date": vault.get("date", ""),
        "vault_url": vault.get("url", ""),
        "lam_name": hideout.get("name", ""),
        "lam_blurb": hideout.get("blurb", ""),
        "lam_image": hideout.get("image", ""),
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
    if "--send-outbox" in sys.argv:
        from engine.send import send_issue

        data = json.loads(OUTBOX.read_text())
        n = send_issue(data["subject"], data["html"])
        print(f"sent '{data['subject']}' to {n} subscriber(s)")
        return

    if "--wait-live" in sys.argv:
        # Apple Mail prefetches images the moment an email arrives, so every
        # self-hosted image must be live on Pages BEFORE the send.
        data = json.loads(OUTBOX.read_text())
        own = [u for u in re.findall(r'<img src="([^"]+)"', data["html"]) if u.startswith(ARCHIVE_URL)]
        deadline = time.time() + 300
        for u in own:
            while not probe_ok(u):
                if time.time() > deadline:
                    sys.exit(f"timed out waiting for {u} to deploy")
                print(f"  waiting for {u.rsplit('/', 1)[-1]}...")
                time.sleep(15)
        print(f"all {len(own)} self-hosted image(s) live")
        return

    subject, email_html, archive_html, today = build()
    write_archive(archive_html, today)
    if "--prepare" in sys.argv:
        OUTBOX.write_text(json.dumps({"subject": subject, "html": email_html}))
        print(f"prepared '{subject}' into the outbox")
    elif "--test" in sys.argv:
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
