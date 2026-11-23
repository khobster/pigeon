"""The Finnish National Gallery (Ateneum, Sinebrychoff, Kiasma). CC0, pool-based.

The whole collection is one open JSON download with CC0 images up to 4000px:
Schjerfbeck, Gallen-Kallela, Edelfelt, Simberg, and a drawer of Japanese
woodblock prints. Rebuild with tools/build_fng_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("fng_pool.json", "Finnish National Gallery", rng)
