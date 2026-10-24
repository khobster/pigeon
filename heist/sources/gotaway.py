"""The Ones That Got Away: great modern pieces the thief couldn't take.

Everything else in the heist is public domain, which means made before ~1931.
MoMA, the Whitney, the Met, Tate and the rest open their catalogs (CC0 data) but not their pictures,
because the art still belongs to the artists. So this section is text only:
it names a few pieces, admits defeat, and sends the reader to each museum's
own page to see them. Draws from heist/gotaway_pool.json (tools/build_gotaway_pool.py).
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "gotaway_pool.json"

# The thief's excuse, one per issue.
LINES = [
    "Too hot to move. Go see them yourself.",
    "Couldn't fence these. Go look instead.",
    "Cased them. Left them. Professional courtesy.",
    "Close enough to touch. Not close enough to take.",
    "Still in copyright. Still spoken for.",
]


def steal(rng, n=3, avoid=frozenset()):
    """n pieces from n different museums, skipping anything in avoid."""
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"Got-away pool missing: {e}")
    items = [i for i in items if i["url"] not in avoid]
    if not items:
        raise RuntimeError("Got-away pool is empty")
    # Pick the museums first so each one gets its share of the days.
    museums = sorted({i["museum"] for i in items})
    picks = [dict(rng.choice([i for i in items if i["museum"] == m]))
             for m in rng.sample(museums, min(n, len(museums)))]
    return {"pieces": picks, "line": rng.choice(LINES)}
