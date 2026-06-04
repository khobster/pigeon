"""Assemble today's heist, archive it to docs/, and optionally send it.

Usage:
  python -m heist.build_issue           # build + archive only (dry run)
  python -m heist.build_issue --send    # build + archive + send to the list
"""
import random
import sys
from datetime import date
from pathlib import Path

from engine.render import render
from heist.sources import met, aic, cleveland, rijks, chunklet, loc, lam

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARCHIVE_URL = "https://khobster.github.io/pigeon/"
HEADER_WEB = "assets/header.png"


def build_haul(rng, today, extras_wanted=3):
    """One hero piece plus a few companions from the other museums."""
    museums = [met, aic, cleveland] + ([rijks] if rijks.available() else [])
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


def build(today=None):
    today = today or date.today()
    rng = random.Random(today.isoformat())

    haul, extras = build_haul(rng, today)
    line = try_steal(chunklet, rng)
    vault = try_steal(loc, rng)
    hideout = try_steal(lam, rng)

    context = {
        "date_pretty": today.strftime("%B %-d, %Y"),
        "preheader": f"Tonight's haul: {haul['title']}",
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
        "line_context": line.get("context") or "lifted from somewhere in the canon",
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

    title = haul["title"]
    if len(title) > 60:  # museum titles can be novels; subjects should not be
        title = title[:60].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    subject = f"the heist · {title}"
    return subject, email_html, archive_html, today


def write_archive(archive_html, today):
    issues_dir = DOCS / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    (issues_dir / f"{today.isoformat()}.html").write_text(archive_html)

    issues = sorted(issues_dir.glob("*.html"), reverse=True)
    items = "\n".join(
        f'      <li><a href="issues/{p.name}">{p.stem}</a></li>' for p in issues
    )
    index = (ROOT / "docs" / "_index_template.html").read_text()
    (DOCS / "index.html").write_text(
        index.replace("{{issue_count}}", str(len(issues))).replace("{{issue_list}}", items)
    )
    print(f"archived issue {today.isoformat()} ({len(issues)} total)")


def main():
    subject, email_html, archive_html, today = build()
    write_archive(archive_html, today)
    if "--send" in sys.argv:
        from engine.send import send_issue

        n = send_issue(subject, email_html)
        print(f"sent '{subject}' to {n} subscriber(s)")
    else:
        print(f"dry run: '{subject}' built but not sent")


if __name__ == "__main__":
    main()
