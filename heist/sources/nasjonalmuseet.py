"""Nasjonalmuseet, Oslo. Public domain paintings, pool-based.

Munch, Dahl, Gude, Thaulow, Kittelsen and Astrup. The museum site blocks
scripts, so the pool comes from Wikidata and the images from Wikimedia
Commons (makers dead before 1956, works by 1930). Rebuild with
tools/build_nasjonalmuseet_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("nasjonalmuseet_pool.json", "Nasjonalmuseet", rng)
