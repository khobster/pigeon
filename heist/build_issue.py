"""Assemble today's heist, archive it to docs/, and optionally send it.

Usage:
  python -m heist.build_issue                       # build + archive only (dry run)
  python -m heist.build_issue --send                # build + archive + send to the list
  python -m heist.build_issue --test you@email.com  # build + send to one address only
"""
import json
import os
import random
import re
import subprocess
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
PINNED = ROOT / "heist" / "pinned"  # heist/pinned/<date>.json overrides the build


def resized(url, width=1120):
    """The wsrv.nl image CDN, used only to fetch a smaller render at build
    time. Width 1120 = retina-sharp at the 560px layout."""
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


def all_live(urls, timeout=300):
    """Poll until every url serves an image, or the timeout lapses."""
    deadline = time.time() + timeout
    for u in urls:
        while not probe_ok(u):
            if time.time() > deadline:
                return False
            print(f"  waiting for {u.rsplit('/', 1)[-1]}...")
            time.sleep(15)
    return True


def retrigger_pages(attempt):
    """Nudge GitHub Pages to redeploy by pushing an empty commit.

    Pages occasionally fails its OWN deploy with a transient 401 and never
    retries; any push to the branch starts a fresh deploy. We only do this
    inside CI (where a checkout token and git identity already exist) — never
    on a local --wait-live, which must not push."""
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", f"retrigger Pages deploy (attempt {attempt})"],
        check=True,
    )
    subprocess.run(["git", "pull", "--rebase", "--autostash"], check=True)
    subprocess.run(["git", "push"], check=True)


def verified(url, today, tag, width=1120):
    """Download the image and return a URL on OUR domain, or raise.

    This is the whole guarantee. Every image in the email is a file we
    physically hold and serve from heist.arugulamotors.com, so once it is
    confirmed live on Pages it cannot break when the email is opened later,
    no matter what a museum server or CDN does in the meantime. A piece
    whose bytes we cannot fetch gets dropped; the manifest never lists loot
    the thief could not actually carry out.

    Per attempt we try the wsrv-resized render first (smaller file), then
    the origin directly. Retries with backoff because some origins (Harvard)
    rate-limit datacenter IPs like the GitHub runner."""
    if not url:
        raise RuntimeError("no image url")
    art_dir = DOCS / "assets" / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(4):
        for candidate in (resized(url, width), url):
            try:
                resp = requests.get(candidate, timeout=45, headers=UA)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if not ctype.startswith("image/"):
                    raise RuntimeError(f"not an image: {ctype or 'unknown'}")
                ext = ".png" if "png" in ctype else ".jpg"
                name = f"{today.isoformat()}-{tag}{ext}"
                (art_dir / name).write_bytes(resp.content)
                return f"{ARCHIVE_URL}assets/art/{name}"
            except Exception as e:  # noqa: BLE001
                last = e
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"could not fetch {url}: {last}")


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
            piece["image"] = verified(piece["image"], today, f"extra{len(extras)}", width=880)
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


# Generic catalog language that makes dull loot. The manifest wants the
# gem, so the framing words, the materials, the container shapes and the
# unidentified-portrait boilerplate all get filtered out and whatever rare
# proper noun is left ("Yue", "Hakone", "Dorian") becomes the loot.
SUBJECT_STOP = {
    # framing / grammar
    "the", "from", "with", "and", "for", "also", "known", "series",
    "untitled", "study", "view", "scene", "after", "called", "plate",
    "number", "between", "design", "detail", "group", "set", "pair",
    "model", "picture",
    # generic people
    "portrait", "madame", "monsieur", "saint", "young", "woman", "man",
    "men", "girl", "boy", "child", "head", "figure", "landscape",
    "unidentified", "unknown", "sitter",
    # formats / materials
    "sheet", "panel", "fragment", "album", "leaf", "page", "photograph",
    "photo", "print", "drawing", "painting", "sketch", "poster",
    "lithograph", "etching", "engraving", "watercolor", "still", "life",
    # container shapes
    "covered", "box", "jar", "vase", "dish", "bowl", "cup", "plate",
    "bottle", "vessel", "ware", "lid", "cover", "tile", "statue", "bust",
    "relief",
    # bland modifiers
    "new", "old", "red", "blue", "green", "white", "black", "gold", "two",
    "one", "three", "large", "small", "great", "big",
}


def keyword(text):
    """The most interesting word in a title: a distinctive proper noun, not
    generic catalog language. We keep capitalized words that survive the
    stop list (down to three letters, so 'Yue' and 'Lid' qualify) and, among
    those, take the longest. The manifest, one word per item."""
    words = re.findall(r"[A-Za-z][A-Za-z']*", text or "")
    def norm(w):
        w = w.lower()
        return w[:-2] if w.endswith("'s") else w
    caps = [w for w in words if w[0].isupper() and norm(w) not in SUBJECT_STOP and len(w) >= 3]
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


def prune_old_art(today, keep_days=365):
    """Delete self-hosted art older than a year. The live email is never
    affected; only archive pages past keep_days go text-only. Keeps the
    repo under the GitHub Pages size limit with zero maintenance."""
    art_dir = DOCS / "assets" / "art"
    if not art_dir.exists():
        return
    removed = 0
    for f in art_dir.glob("*-*.*"):
        stamp = f.name[:10]
        try:
            age = (today - date.fromisoformat(stamp)).days
        except ValueError:
            continue
        if age > keep_days:
            f.unlink()
            removed += 1
    if removed:
        print(f"pruned {removed} art file(s) older than {keep_days} days")


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
        # Every image is self-hosted now, so none of them may be sent until
        # all are confirmed live on Pages (Apple Mail prefetches at delivery).
        # If they don't come up, the usual cause is a transient Pages deploy
        # failure (a self-inflicted 401 on GitHub's side) that nothing retries
        # on its own; in CI we retrigger the deploy with an empty commit and
        # wait again, since the send is gated on the art actually being live.
        data = json.loads(OUTBOX.read_text())
        own = [u for u in re.findall(r'<img src="([^"]+)"', data["html"]) if u.startswith(ARCHIVE_URL)]
        for attempt in range(1, 4):
            if all_live(own):
                print(f"all {len(own)} image(s) live on our domain")
                return
            if not os.environ.get("GITHUB_ACTIONS"):
                break  # a local run can't (and must not) retrigger a deploy
            print(f"art not live (attempt {attempt}); retriggering the Pages deploy")
            retrigger_pages(attempt)
        sys.exit("timed out waiting for the art to deploy")

    if "--test-outbox" in sys.argv:
        from engine.send import send_issue

        to = sys.argv[sys.argv.index("--test-outbox") + 1]
        data = json.loads(OUTBOX.read_text())
        send_issue(data["subject"], data["html"], recipients=[to])
        print(f"test: sent '{data['subject']}' to {to} only")
        return

    # A pinned edition (heist/pinned/<date>.json, with subject/email_html/
    # archive_html) locks a specific hand-approved issue for that day instead
    # of regenerating it. The nightly build is not fully reproducible — The
    # Line is drawn fresh each run and the chunklet Lambda can be down — so
    # this is how we guarantee a particular issue goes out. Its art is already
    # live, so the usual publish/wait-live/send steps still apply unchanged.
    pin = PINNED / f"{date.today().isoformat()}.json"
    if pin.exists():
        data = json.loads(pin.read_text())
        write_archive(data["archive_html"], date.today())
        OUTBOX.write_text(json.dumps({"subject": data["subject"], "html": data["email_html"]}))
        print(f"using pinned edition for {date.today().isoformat()}: '{data['subject']}'")
        return

    # Building downloads every image into docs/. Because all art is now
    # self-hosted, sending can ONLY happen after the archive is pushed and
    # the images are confirmed live (--wait-live), so there is no immediate
    # --send/--test path: everything goes through the outbox.
    subject, email_html, archive_html, today = build()
    write_archive(archive_html, today)
    prune_old_art(today)
    OUTBOX.write_text(json.dumps({"subject": subject, "html": email_html}))
    if "--prepare" in sys.argv:
        print(f"prepared '{subject}' into the outbox")
    else:
        print(f"dry run: '{subject}' built and archived, not sent")


if __name__ == "__main__":
    main()
