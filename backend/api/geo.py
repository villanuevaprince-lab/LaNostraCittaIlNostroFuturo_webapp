"""Geocoding on demand, con quota globale per rispettare Nominatim pubblico."""

import json
import os
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request

from backend.security import limiter, login_required


geo_api = Blueprint("geo_api", __name__, url_prefix="/api/geo")
BOUNDS = (45.35, 45.56, 9.04, 9.36)


def in_milan(lat, lon):
    return BOUNDS[0] <= lat <= BOUNDS[1] and BOUNDS[2] <= lon <= BOUNDS[3]


@lru_cache(maxsize=512)
def nominatim(path, parameters):
    agent = "LaNostraCittaIlNostroFuturo/1.0 (https://github.com/villanuevaprince-lab/LaNostraCittaIlNostroFuturo_webapp)"
    if os.getenv("MAP_CONTACT_EMAIL"):
        agent += f" contact={os.environ['MAP_CONTACT_EMAIL']}"
    url = "https://nominatim.openstreetmap.org/" + path + "?" + urlencode(dict(parameters))
    query = Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    with urlopen(query, timeout=6) as response:
        return json.load(response)


@geo_api.get("/search")
@login_required
@limiter.limit("1 per second; 1000 per day", key_func=lambda: "nominatim-global")
def search():
    term = request.args.get("q", "").strip()
    if not 3 <= len(term) <= 120:
        return jsonify(error="Inserisci una via o zona (3–120 caratteri)."), 400
    try:
        results = nominatim("search", tuple(sorted({
            "q": term + ", Milano, Italia", "format": "jsonv2", "limit": 5,
            "viewbox": "9.04,45.56,9.36,45.35", "bounded": 1,
            "accept-language": "it",
        }.items())))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return jsonify(error="Ricerca indirizzo temporaneamente non disponibile."), 502
    return jsonify([{"lat": float(row["lat"]), "lng": float(row["lon"]),
                     "indirizzo": row["display_name"][:255]} for row in results
                    if in_milan(float(row["lat"]), float(row["lon"]))])


@geo_api.get("/reverse")
@login_required
@limiter.limit("1 per second; 1000 per day", key_func=lambda: "nominatim-global")
def reverse():
    lat, lon = request.args.get("lat", type=float), request.args.get("lng", type=float)
    if lat is None or lon is None or not in_milan(lat, lon):
        return jsonify(error="Seleziona un punto nell'area di Milano."), 400
    try:
        result = nominatim("reverse", tuple(sorted({
            "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2",
            "zoom": 18, "accept-language": "it",
        }.items())))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return jsonify(error="Indirizzo non disponibile. Puoi correggerlo nel campo sotto."), 502
    return jsonify(indirizzo=result.get("display_name", "")[:255])
