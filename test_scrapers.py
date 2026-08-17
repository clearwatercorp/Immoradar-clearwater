#!/usr/bin/env python3
"""Diagnostic des 4 scrapers, à lancer là où l'accès réseau est normal :

    python3 test_scrapers.py            # teste les 4 sources
    python3 test_scrapers.py leboncoin  # teste une seule source

Affiche, pour chaque source : le nombre d'annonces brutes récupérées, le
nombre retenues après filtrage (zone / prix / surface), et un échantillon.
En cas de problème, colle la sortie complète — elle contient les codes HTTP
et les messages d'erreur de chaque scraper.
"""

import sys
import traceback

from scrapers import leboncoin, bienici, pap, seloger
from scrapers.common import passes_filters

SOURCES = {
    "leboncoin": leboncoin.search,
    "bienici":   bienici.search,
    "pap":       pap.search,
    "seloger":   seloger.search,
}


def test_source(name, fn):
    print(f"\n{'=' * 60}\n  {name.upper()}\n{'=' * 60}")
    try:
        ads = fn()
    except Exception:
        print(f"❌ EXCEPTION dans {name}:")
        traceback.print_exc()
        return

    print(f"→ {len(ads)} annonce(s) brute(s) récupérée(s)")
    if not ads:
        print("   (voir les messages ci-dessus pour la raison : HTTP, structure, anti-bot…)")
        return

    kept = [a for a in ads if passes_filters(dict(a))]
    print(f"→ {len(kept)} retenue(s) après filtres (zone, prix, surface)")

    for ad in ads[:3]:
        print(
            f"\n   • {ad.get('titre', '')[:70]}\n"
            f"     {ad.get('prix')} € · {ad.get('surface')} m² · {ad.get('pieces')} p. "
            f"· {ad.get('type_bien')} · {ad.get('ville')} {ad.get('cp')}\n"
            f"     DPE={ad.get('dpe')} lat/lon={ad.get('lat')},{ad.get('lon')}\n"
            f"     {ad.get('link')}"
        )

    champs_vides = [
        champ for champ in ("titre", "prix", "surface", "ville", "link")
        if not any(a.get(champ) for a in ads)
    ]
    if champs_vides:
        print(f"\n   ⚠️  Champs systématiquement vides (parsing à revoir) : {', '.join(champs_vides)}")


def main():
    demandees = sys.argv[1:] or list(SOURCES)
    inconnues = [n for n in demandees if n not in SOURCES]
    if inconnues:
        print(f"Source(s) inconnue(s) : {', '.join(inconnues)}\nDisponibles : {', '.join(SOURCES)}")
        sys.exit(1)

    for name in demandees:
        test_source(name, SOURCES[name])
    print(f"\n{'=' * 60}\nTerminé.")


if __name__ == "__main__":
    main()
