"""Nationalmuseum, Stockholm. Public domain paintings, pool-based.

The museum gave its public-domain paintings to Wikimedia Commons at full
resolution (Rembrandt, Boucher, Zorn, Larsson, Josephson), and Wikidata
catalogs them; images serve from upload.wikimedia.org. Rebuild with
tools/build_nationalmuseum_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("nationalmuseum_pool.json", "Nationalmuseum", rng)
