"""
TFG: Geocodificació d'Entitats
Converteix noms de lloc en coordenades reals via Nominatim (OpenStreetMap).
Gratuït, sense API key.

Instal·lació: pip install geopy
"""

import time
from typing import Optional
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError


GEOLOCATOR   = Nominatim(user_agent="tfg_arqueologia_uab_2026")
REQUEST_DELAY = 1.2   # Nominatim: màx 1 req/seg


def geocode_one(name: str, entity_type: str) -> tuple[Optional[float], Optional[float], str, str]:
    """
    Geocodifica un nom de lloc.
    Retorna (lat, lon, display_name, status).
    """
    queries = _build_queries(name, entity_type)

    for query in queries:
        try:
            time.sleep(REQUEST_DELAY)
            result = GEOLOCATOR.geocode(
                query,
                viewbox=[(-20.0, -80.0), (5.0, -50.0)],   # Amazònia sud-occidental
                bounded=False,
                language="es",
                timeout=10,
            )
            if result:
                return (
                    round(result.latitude, 6),
                    round(result.longitude, 6),
                    result.address,
                    "found",
                )
        except GeocoderTimedOut:
            time.sleep(2)
        except GeocoderServiceError as e:
            print(f"   Error servei Nominatim: {e}")
            return None, None, "", "error"

    return None, None, "", "not_found"


def _build_queries(name: str, entity_type: str) -> list[str]:
    """Genera variants de cerca per augmentar la taxa d'èxit."""
    queries = [name]
    hints = {
        "river":      [f"río {name}", f"{name} river Amazon"],
        "settlement": [f"{name} Bolivia", f"{name} Brazil", f"{name} Amazon"],
        "region":     [f"{name} South America", f"{name} Bolivia", f"{name} Brazil"],
        "other":      [f"{name} Amazon basin", f"{name} South America"],
    }
    queries += hints.get(entity_type, [f"{name} South America"])
    # Versió netejada (sense articles)
    clean = name.replace("río ", "").replace("región del ", "").replace("ciudad de ", "").strip()
    if clean != name:
        queries.append(clean)
    return queries


def geocode_all_db(db) -> int:
    """
    Geocodifica totes les entitats de la DB que no tenen coordenades.
    Retorna el nombre d'entitats geocodificades amb èxit.
    """
    pending = db.get_entities_without_coords()
    if not pending:
        print("Totes les entitats ja estan geocodificades.")
        return 0

    # Agrupar per nom normalitzat: geocodificar una sola vegada per nom
    groups = {}  # clau: nom normalitzat, valor: llista d'entitats
    for e in pending:
        key = e["name"].lower().strip()
        groups.setdefault(key, []).append(e)

    unique_names = len(groups)
    saved_calls = len(pending) - unique_names
    print(f"\nGeocodificant {len(pending)} entitats ({unique_names} noms unics, {saved_calls} crides estalviades)...\n")

    ok = 0
    for key, entity_group in groups.items():
        representative = entity_group[0]
        name  = representative["name"]
        etype = representative["entity_type"]
        n_copies = len(entity_group)
        suffix = f" (x{n_copies})" if n_copies > 1 else ""
        print(f"   • {name:<35}{suffix:<6}", end="", flush=True)

        lat, lon, display, status = geocode_one(name, etype)

        # Aplicar el resultat a totes les entitats del grup
        for e in entity_group:
            db.update_geocoding(e["id"], lat, lon, status, display)

        if status == "found":
            print(f"✓  {lat:.4f}, {lon:.4f}")
            ok += n_copies
        else:
            print("✗  no trobat")

    print(f"\n   Resultat: {ok}/{len(pending)} geocodificades amb èxit")
    return ok