"""The One That Got Away: a great modern piece the thief couldn't take.

Everything else in the heist is public domain, which means made before ~1931.
MoMA and the Whitney open their catalogs (CC0 data) but not their pictures,
because the art still belongs to the artists. So this section is text only:
it names one piece, admits defeat, and sends the reader to the museum's own
page to see it. Draws from heist/gotaway_pool.json (tools/build_gotaway_pool.py).
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "gotaway_pool.json"

# The thief's excuse, one per issue. {museum} is "MoMA" or "the Whitney".
LINES = [
    "Cased it for weeks. Still in copyright, still at {museum}.",
    "Too hot to move. You'll have to go look at it yourself.",
    "Got as far as the frame. The artist's estate got the rest.",
    "This one's still spoken for, and {museum} has very good lawyers.",
    "Some things you can't fence. This is one of them.",
    "Left it right where we found it. Professional courtesy.",
    "Close enough to touch. Not close enough to take.",
    "Every thief has one. This is ours, and it's at {museum}.",
]


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"Got-away pool missing: {e}")
    if not items:
        raise RuntimeError("Got-away pool is empty")
    # Pick the museum first so MoMA and the Whitney split the days evenly.
    museum = rng.choice(sorted({i["museum"] for i in items}))
    piece = dict(rng.choice([i for i in items if i["museum"] == museum]))
    piece["line"] = rng.choice(LINES).format(museum=piece["museum"])
    return piece
