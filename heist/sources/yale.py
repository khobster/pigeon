"""Yale: the Yale Center for British Art and the Yale University Art Gallery.
Public domain, pool-based.

Turner, Constable, Stubbs, Blake, Van Gogh's Night Cafe, Homer. The old live
source searched Yale's LUX, which now answers scripts with a bot challenge
(so it almost never delivered), and it trusted the manifest's top-level CC0,
which covers the metadata, not the image. The pool is read from the open IIIF
manifests and checks each canvas's real "Image Use Rights". Rebuild with
tools/build_yale_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("yale_pool.json", "Yale", rng)
