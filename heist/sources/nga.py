"""National Gallery of Art, Washington. CC0 open access, pool-based.

NGA has no live search API, but it publishes its open-access collection as CSVs
(github.com/NationalGalleryOfArt/opendata) and serves images from media.nga.gov,
which is reachable from CI. So, like the Library of Congress vault, we draw from
a pre-built pool (heist/nga_pool.json) committed to the repo. Rebuild or grow it
with tools/build_nga_pool.py from any machine. Note media.nga.gov sits behind
Cloudflare, which can intermittently challenge a fetch; the build's verified()
ladder and haul resampling absorb the occasional miss.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "nga_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"NGA pool missing: {e}")
    if not items:
        raise RuntimeError("NGA pool is empty")
    return dict(rng.choice(items))
