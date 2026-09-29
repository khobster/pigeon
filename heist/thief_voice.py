"""The thief's voice.

One Claude call per issue that turns dry catalog metadata (title, artist, year,
medium, museum) into a line of patter in the persona of 'your personal art
thief'. This is what makes the heist read like a person is showing you the loot
rather than a database dumping thumbnails.

Fails soft: if the key is missing, the call errors, or the reply won't parse, we
return {} and the template falls back to the plain captions. The newsletter must
still go out on a bad API day.
"""
import json
import re

import requests

from engine.common import ANTHROPIC_API_KEY

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-8"

SYSTEM = (
    "You write the one-line notes under the artworks in 'the heist', a daily art "
    "newsletter with a bold, timeless, album-cover sensibility. Your notes are "
    "sharp, dry, and specific to the picture: the one thing that makes it cool, "
    "or a small true detail that makes the reader look twice. Think of a sly, "
    "knowledgeable friend pointing at a wall, not a costumed thief narrating a "
    "caper. NO first-person heist role-play (no 'I stole', 'in my satchel', 'the "
    "guards', 'my loot'), NO theatrics, NO art-history jargon, NO salesy hype, NO "
    "corniness. One or two sentences at most, and shorter is better. Never use em "
    "dashes or en dashes; use commas or periods. Output ONLY the requested JSON "
    "object, nothing before or after it."
)


def available():
    return bool(ANTHROPIC_API_KEY)


def _piece(p):
    return {
        "title": p.get("title", ""),
        "artist": p.get("artist", ""),
        "year": p.get("year", ""),
        "medium": p.get("medium", ""),
        "museum": p.get("museum", ""),
    }


def narrate(hero, extras, vault=None):
    """Return {'hero', 'extras': [...]} of short notes, or {} on any failure.
    The 'extras' list is aligned one-to-one with the extras passed in (padded or
    truncated to match)."""
    if not ANTHROPIC_API_KEY:
        return {}
    loot = {
        "hero": _piece(hero),
        "extras": [_piece(e) for e in extras],
    }
    shape = (
        '{"hero": "<1-2 sharp sentences on the hero piece, the star of the haul>", '
        '"extras": ["<one short note per extra, in order>"]}'
    )
    prompt = (
        "Today's pieces, as JSON:\n\n"
        + json.dumps(loot, ensure_ascii=False)
        + "\n\nWrite the notes. Return a JSON object of exactly this shape:\n"
        + shape
        + f"\n\nThe \"extras\" array MUST contain exactly {len(extras)} strings, one "
        "per piece, in the same order. Keep the hero note to one or two sentences "
        "and each extra note to roughly 8 to 14 words."
    )
    try:
        resp = requests.post(
            API,
            timeout=60,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 1500,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        text = "".join(
            b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text"
        ).strip()
        # Strip a ```json fence if the model wrapped the object in one.
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"  [thief voice unavailable, shipping plain captions] {e}")
        return {}
    exs = data.get("extras") or []
    if not isinstance(exs, list):
        exs = []
    exs = (exs + [""] * len(extras))[: len(extras)]
    return {
        "hero": data.get("hero", "") or "",
        "extras": [e or "" for e in exs],
    }
