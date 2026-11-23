"""Shared draw for the pool-based sources: a committed JSON list of works,
built offline by a tools/build_*_pool.py script, picked from at random."""
import json
from pathlib import Path

POOLS = Path(__file__).resolve().parent.parent


def steal_from(filename, name, rng):
    try:
        items = json.loads((POOLS / filename).read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"{name} pool missing: {e}")
    if not items:
        raise RuntimeError(f"{name} pool is empty")
    return dict(rng.choice(items))
