"""The Walters Art Museum, Baltimore. Public domain, pool-based.

The Walters blocks scripts, but it gave its collection's images to Wikimedia
Commons at high resolution; Wikidata catalogs them with the museum's own
object id, so links go to art.thewalters.org. Rebuild with
tools/build_wikidata_pool.py walters.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("walters_pool.json", "Walters", rng)
