"""From the Vault: a find from the Library of Congress archives.

loc.gov sits behind Cloudflare, which 403s the GitHub Actions runner's
datacenter IP, so the build can no longer search loc.gov live (it did until
mid-June 2026, when the block went from intermittent empty bodies to a hard
403). Rather than let the thief's favorite drawer keep coming up empty, we
draw from a pool curated and color-vetted ahead of time in heist/loc_pool.json
(see tools/build_loc_pool.py). Every item in the pool is already confirmed to
be a real, large, in-color image, so the Vault section is always present and
always vivid. The build's verified() still downloads and re-checks the image
at send time, self-hosting it like every other piece.

Refresh the pool by re-running the builder from any non-blocked IP (a normal
laptop): `python tools/build_loc_pool.py heist/loc_pool.json`.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "loc_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"LOC pool missing: {e}")
    if not items:
        raise RuntimeError("LOC pool is empty")
    # Seeded choice keeps the day reproducible; ~180 items means a long run
    # before the vault repeats itself.
    return dict(rng.choice(items))
