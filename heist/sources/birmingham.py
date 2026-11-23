"""Birmingham Museum and Art Gallery. Public domain, pool-based.

The Pre-Raphaelites' home: Burne-Jones, Rossetti, Millais, Ford Madox Brown,
Holman Hunt, Sandys. The museum's own pages are gone and its image bank
isn't hot-linkable, so the pool comes from Wikidata and the images from
Wikimedia Commons. Rebuild with
tools/build_wikidata_pool.py birmingham.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("birmingham_pool.json", "Birmingham", rng)
