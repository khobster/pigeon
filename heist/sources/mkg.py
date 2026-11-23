"""MKG Hamburg (Museum fuer Kunst und Gewerbe). CC0, pool-based.

Jugendstil and Vienna Secession posters (Klimt, Moser, Urban, Lefler),
Japanese woodblock prints (Hokusai, Hiroshige, Harunobu, Utamaro) and Art
Nouveau glass and ceramics (Galle, Tiffany, Lalique), from MKG's open data
dump. Images top out at 1200px. Rebuild with tools/build_mkg_pool.py.
"""
from heist.sources.pooled import steal_from


def steal(rng):
    return steal_from("mkg_pool.json", "MKG Hamburg", rng)
