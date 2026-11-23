"""The J. Paul Getty Museum, Los Angeles. Public-domain, pool-based.

The Getty's Open Content Program gives away its public-domain images as CC0
at full resolution: Van Gogh's Irises, Manet, Rembrandt, a deep bench of
illuminated manuscripts, drawings and decorative arts. Big, sharp images
from a reliable IIIF server, which is exactly what a hero needs. Like the
Barnes and LACMA we draw from a pre-built pool (heist/getty_pool.json) so
the nightly build never depends on a SPARQL endpoint.

Rebuild the pool with tools/build_getty_pool.py from any machine.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "getty_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"Getty pool missing: {e}")
    if not items:
        raise RuntimeError("Getty pool is empty")
    return dict(rng.choice(items))
