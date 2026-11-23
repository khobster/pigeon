"""The Minneapolis Institute of Art. Public domain ("available for any use"),
pool-based.

Mia's Asian collection is the draw: Hokusai, Hiroshige, Yoshitoshi, Japanese
screens and scrolls, Chinese and Indian painting, with its European and
American pictures alongside. Images are originals off img.artsmia.org, shrunk
by wsrv. Rebuild with tools/build_mia_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("mia_pool.json", "Mia", rng)
