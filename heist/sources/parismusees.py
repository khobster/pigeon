"""Paris Musées: the 14 City of Paris museums (Petit Palais, Carnavalet, the
Musée d'Art Moderne, Cernuschi, Galliera, Maison de Victor Hugo, ...).
CC0, pool-based.

Paris Musées released its public-domain collection as CC0 in 2020. Its own
API needs a key and its site is often down, but it mirrored ~326,000 of those
images to Wikimedia Commons, and upload.wikimedia.org never blocks the GitHub
runner. The pool (heist/parismusees_pool.json) is searched from that mirror's
colorful seams (posters, shop signs, fans, menus, paintings), license- and
color-vetted ahead of time.

Rebuild the pool with tools/build_parismusees_pool.py from any machine.
"""
import json
from pathlib import Path

POOL = Path(__file__).resolve().parent.parent / "parismusees_pool.json"


def steal(rng):
    try:
        items = json.loads(POOL.read_text())
    except FileNotFoundError as e:
        raise RuntimeError(f"Paris Musées pool missing: {e}")
    if not items:
        raise RuntimeError("Paris Musées pool is empty")
    return dict(rng.choice(items))
