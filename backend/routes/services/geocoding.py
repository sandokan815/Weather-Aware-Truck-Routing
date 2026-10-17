"""
Address search for the origin/destination autocomplete.

GEOCODING_PROVIDER: "nominatim" (default), "photon" or "mapbox".

Nominatim is weak at partial words ("Los Ang" -> a street in Mexico), so for
type-ahead requests (autocomplete=True) we ask Photon first - same OSM data,
but built for prefix search - and fall back to Nominatim. Full lookups (when the
user submits text without picking a suggestion) use the configured provider
first. Results are cached.
"""
import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)


def _get(url, params):
    resp = requests.get(
        url,
        params=params,
        timeout=min(settings.HTTP_TIMEOUT_SECONDS, 10),
        headers={"User-Agent": settings.HTTP_USER_AGENT, "Accept-Language": "en"},
    )
    resp.raise_for_status()
    return resp.json()


def nominatim(query, limit):
    params = {"q": query, "format": "jsonv2", "limit": limit, "addressdetails": 0}
    if settings.GEOCODE_COUNTRY_CODES:
        params["countrycodes"] = settings.GEOCODE_COUNTRY_CODES
    data = _get(f"{settings.NOMINATIM_BASE_URL}/search", params)
    return [
        {"label": d["display_name"], "lat": float(d["lat"]), "lon": float(d["lon"])}
        for d in data
    ]


def photon(query, limit):
    data = _get(f"{settings.PHOTON_BASE_URL}/api/", {"q": query, "limit": limit * 2, "lang": "en"})
    allowed = {c.strip().upper() for c in settings.GEOCODE_COUNTRY_CODES.split(",") if c.strip()}
    results = []
    for f in data.get("features", []):
        p = f["properties"]
        if allowed and p.get("countrycode", "").upper() not in allowed:
            continue
        parts = [p.get("name"), p.get("city"), p.get("state"), p.get("country")]
        label = ", ".join(dict.fromkeys(x for x in parts if x))
        if any(r["label"] == label for r in results):
            continue  # Photon often returns a city and its boundary twice
        lon, lat = f["geometry"]["coordinates"]
        results.append({"label": label, "lat": lat, "lon": lon})
    return results[:limit]


def mapbox(query, limit):
    if not settings.MAPBOX_ACCESS_TOKEN:
        return []
    params = {
        "access_token": settings.MAPBOX_ACCESS_TOKEN,
        "autocomplete": "true",
        "limit": limit,
    }
    if settings.GEOCODE_COUNTRY_CODES:
        params["country"] = settings.GEOCODE_COUNTRY_CODES
    data = _get(
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/{requests.utils.quote(query)}.json",
        params,
    )
    return [
        {"label": f["place_name"], "lat": f["center"][1], "lon": f["center"][0]}
        for f in data.get("features", [])
    ]


PROVIDERS = {"nominatim": nominatim, "photon": photon, "mapbox": mapbox}


def search(query, limit=5, autocomplete=False):
    query = query.strip()
    if len(query) < 3:
        return []
    digest = hashlib.md5(query.lower().encode()).hexdigest()
    key = f"geo:{settings.GEOCODING_PROVIDER}:{int(autocomplete)}:{digest}:{limit}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    primary = settings.GEOCODING_PROVIDER
    if autocomplete and primary == "nominatim":
        primary = "photon"
    order = [primary] + [p for p in ("photon", "nominatim") if p != primary]
    results = []
    for name in order:
        try:
            results = PROVIDERS[name](query, limit)
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.warning("Geocoder %s failed: %s", name, exc)
            continue
        if results:
            break

    cache.set(key, results, 24 * 60 * 60)
    return results
