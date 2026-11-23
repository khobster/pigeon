"""The Brooklyn Museum. Public domain paintings, pool-based.

Brooklyn's site and API block scripts now, so the pool comes from Wikidata
and the images from Brooklyn's own uploads to Wikimedia Commons. Rebuild
with tools/build_brooklyn_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("brooklyn_pool.json", "Brooklyn Museum", rng)
