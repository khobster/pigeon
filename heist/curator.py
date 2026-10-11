"""The art director.

Pure color/saturation metrics can tell a vivid image from a dull one, but they
cannot tell COOL from uncool — that is why a vivid devotional scene kept beating
a great modernist piece. So this module actually LOOKS at the candidate images
with Claude vision and picks the coolest hero plus a ranked bag, to the heist's
Barnes / Whitney / Guggenheim / MoMA sensibility: bold, striking, timeless art
an indie artist would hang on a wall or put on an album cover, old or new.

Fails soft: returns None on a missing key, an API error, or an unparseable
reply, and the build falls back to its vividness ranking.
"""
import base64
import json
import re

import requests

from engine.common import ANTHROPIC_API_KEY

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are the art director for 'the heist', a daily art newsletter. Its taste "
    "is the Barnes Foundation crossed with the Whitney, the Guggenheim, and MoMA: "
    "bold, striking, timeless art that an indie musician would hang on the wall or "
    "put on an album cover. Age is irrelevant; coolness is everything. The thief's "
    "whole pitch is 'this might be old, it might be new, but look how COOL this "
    "is.' You LOVE: strong color and shape, graphic punch, post-impressionist, "
    "modernist, and avant-garde energy, bold prints and design, the striking and "
    "the unexpected, from ANY culture or era: an Art Deco poster, a Mexican folk "
    "retablo, a Persian miniature, a Mucha, a van Gogh, a Japanese woodblock, a "
    "West African mask, a Russian constructivist print. LEAN MODERN AND INDIE: "
    "when two pieces are similarly cool, take the more modern, graphic, or off-"
    "canonical one over the safe old masterpiece. VARIETY MATTERS: favor a MIX of "
    "cultures, regions, eras, and mediums across the hero and the bag. Japanese "
    "woodblock prints are wonderful but the newsletter has been leaning on them "
    "hard, so do NOT default to one, and avoid a hero plus a bag that are mostly "
    "from a single tradition. The SAME caution applies to ceremonial masks: they "
    "are striking but have been overused as the hero, so do not crown a mask as "
    "the hero unless it clearly beats every other candidate. Vary the hero's FORM "
    "(a poster, a painting, a print, a textile, a design object, now and then a "
    "mask), not just its culture. You REJECT as "
    "uncool, no matter how old or famous: stuffy academic portraits, dull "
    "devotional scenes, muddy or timid images, fussy decorative filler, botanical "
    "or catalog plates, and anything that feels creaky, safe, or forgettable. "
    "HARD RULE, overriding everything else: NEVER choose anything racist, "
    "demeaning, or colonial, no matter how visually striking or famous: racial "
    "caricatures, blackface or minstrel imagery, 'human zoo' or ethnographic-"
    "spectacle scenes (colonized people displayed as exhibits or circus acts), "
    "ethnic or religious stereotypes, or anything that dehumanizes a group. "
    "Exclude such images from BOTH the hero and the bag entirely. You are shown "
    "numbered candidate images with their catalog data. Output ONLY the requested "
    "JSON object."
)


def available():
    return bool(ANTHROPIC_API_KEY)


def curate(items, bag_size):
    """items: list of dicts with 'i' (int index), 'title', 'artist', 'year',
    'medium', 'museum', and 'image' (JPEG bytes). Returns {'hero': i, 'bag':
    [i, ...]} using only indices present in items, or None on failure."""
    if not ANTHROPIC_API_KEY or not items:
        return None
    content = []
    for it in items:
        b64 = base64.standard_b64encode(it["image"]).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
        content.append({"type": "text", "text": (
            f'[{it["i"]}] {(it.get("title") or "")[:70]} / '
            f'{(it.get("artist") or "")[:40]} / {it.get("year") or ""} / '
            f'{it.get("museum") or ""}'
        )})
    content.append({"type": "text", "text": (
        "Choose the single COOLEST image as the hero: the one most likely to end "
        "up on an album cover or an indie wall. Then rank the coolest of the rest "
        f"for the bag, up to {bag_size} of them, and DROP any that are uncool "
        "rather than padding the list. Judge the pictures, not the labels. Return "
        'JSON exactly of this shape: {"hero": <index>, "bag": [<index>, ...]}. '
        "Use only the bracketed numbers shown."
    )})
    try:
        resp = requests.post(
            API,
            timeout=90,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 800,
                "system": SYSTEM,
                "messages": [{"role": "user", "content": content}],
            },
        )
        resp.raise_for_status()
        text = "".join(
            b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text"
        ).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"  [art director unavailable, using vividness ranking] {e}")
        return None
    valid = {it["i"] for it in items}
    hero = data.get("hero")
    if hero not in valid:
        return None
    bag = []
    for i in (data.get("bag") or []):
        if i in valid and i != hero and i not in bag:
            bag.append(i)
    return {"hero": hero, "bag": bag}
