"""Los Angeles County Museum of Art. Public-domain, pool-based.

LACMA releases its public-domain images "free of charge and for use without
restriction" (Public Domain Mark) but has no search API and no open-data dump,
so — like the National Gallery of Art and the Library of Congress vault — we
draw from a pre-built pool (heist/lacma_pool.json) committed to the repo. The
pool is biased toward LACMA's cool/graphic seam: prints, drawings, photographs,
costumes, textiles and decorative arts, plus anything made from 1850 on. Images
serve from collections-images.lacma.org (CloudFront + S3), reachable from CI.

Rebuild or grow the pool with tools/build_lacma_pool.py from any machine.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "lacma_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"LACMA pool missing: {e}")
    if not items:
        raise RuntimeError("LACMA pool is empty")
    return dict(rng.choice(items))
