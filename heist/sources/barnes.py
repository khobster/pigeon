"""The Barnes Foundation, Philadelphia. Public-domain, pool-based.

The heist's taste is literally "the Barnes crossed with the Whitney", and the
Barnes is the one of those that leaves the door open: its public-domain works
(Cezanne, Renoir, Seurat, Modigliani, Prendergast, Glackens, Pascin, Demuth,
early Matisse) carry a Public Domain Mark. Its search API is a raw
Elasticsearch endpoint we'd rather not hit from CI every morning, so like
LACMA we draw from a pre-built pool (heist/barnes_pool.json). Images serve
from the Barnes's CloudFront bucket.

Rebuild the pool with tools/build_barnes_pool.py from any machine.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "barnes_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"Barnes pool missing: {e}")
    if not items:
        raise RuntimeError("Barnes pool is empty")
    return dict(rng.choice(items))
