"""The Biodiversity Heritage Library. Public domain, pool-based.

Hand-colored natural history plates from two dozen great illustrated books:
Gould's birds, Curtis's Botanical Magazine, Merian's Surinam insects, Reeve's
shells, Hewitson's butterflies, Redoute's lilies and roses. Full-resolution
page scans from BHL's open S3 bucket (WebP, so wsrv converts them to JPEG).
Rebuild with tools/build_bhl_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("bhl_pool.json", "BHL", rng)
