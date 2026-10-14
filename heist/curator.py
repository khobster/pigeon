"""The art director.

Pure color/saturation metrics can tell a vivid image from a dull one, but they
cannot tell COOL from uncool — that is why a vivid devotional scene kept beating
a great modernist piece. So this module actually LOOKS at the candidate images
with a vision model and picks the coolest hero plus a ranked bag, to the heist's
Barnes / Whitney / Guggenheim / MoMA sensibility: bold, striking, timeless art
an indie artist would hang on a wall or put on an album cover, old or new.

Fails soft: returns None on a missing key, an API error, or an unparseable
reply, and the build falls back to its vividness ranking.
"""
import base64
import json
import re

import requests

from engine.common import CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN

# Cloudflare Workers AI, OpenAI-compatible chat completions endpoint.
API = (
    f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}"
    "/ai/v1/chat/completions"
)
# Free Cloudflare Workers AI vision model (natively multimodal). Swap this for
# another CF vision model id if a better/cheaper one becomes available.
MODEL = "@cf/meta/llama-4-scout-17b-16e-instruct"

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
    return bool(CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN)


def curate(items, bag_size):
    """items: list of dicts with 'i' (int index), 'title', 'artist', 'year',
    'medium', 'museum', and 'image' (JPEG bytes). Returns {'hero': i, 'bag':
    [i, ...]} using only indices present in items, or None on failure."""
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) or not items:
        return None
    content = []
    for it in items:
        b64 = base64.standard_b64encode(it["image"]).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
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
                "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 800,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": content},
                ],
            },
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
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
