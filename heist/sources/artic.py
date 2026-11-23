"""The Art Institute of Chicago. CC0, pool-based.

Seurat, Monet, Caillebotte, Cassatt, Hokusai, Hiroshige, Toulouse-Lautrec.
AIC's API blocks the runner, so the pool is listed from a laptop; the build
fetches images straight from AIC's IIIF host (it refuses wsrv; see
resized() in build_issue). The live-API module, aic.py, stays for
tools/retest_aic.py. Rebuild with tools/build_aic_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("aic_pool.json", "Art Institute of Chicago", rng)
