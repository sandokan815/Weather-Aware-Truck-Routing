"""
Route options from a third-party routing API.

Providers (ROUTING_PROVIDER): "osrm" (default, free public server), "ors"
(OpenRouteService, HGV/truck profile, needs ORS_API_KEY), "mapbox" (needs
MAPBOX_ACCESS_TOKEN), or "mock". If the configured provider fails, the other
configured providers are tried, then (optionally) mock routes.

Routing engines often return fewer than 3 alternatives for long trips (the
public OSRM server returns just one for LA -> Denver). To always offer 3
genuinely different corridors we additionally request routes forced through
"via" points offset perpendicular to the straight origin->destination line,
drop near-duplicates and unreasonable detours, and keep the fastest distinct
ones.
"""
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from django.conf import settings

from . import mock
from .geo import METERS_PER_MILE, haversine_mi, overlap_ratio

log = logging.getLogger(__name__)

MAX_DETOUR_FACTOR = 1.6     # alternatives may take at most 60% longer than the fastest
DUPLICATE_OVERLAP = 0.85    # routes sharing >85% of their path are considered duplicates
VIA_OFFSETS = (0.18, -0.18, 0.33, -0.33)  # fraction of straight-line distance


class RoutingError(Exception):
    pass


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _request(method, url, retries=1, **kwargs):
    kwargs.setdefault("timeout", settings.HTTP_TIMEOUT_SECONDS)
    headers = kwargs.pop("headers", {})
    headers.setdefault("User-Agent", settings.HTTP_USER_AGENT)
    for attempt in range(retries + 1):
        try:
            resp = requests.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as exc:
            if attempt == retries:
                raise RoutingError(f"Routing request failed: {exc}") from exc
            continue
        if resp.status_code == 429 and attempt < retries:
            time.sleep(1.2)  # public servers rate-limit; back off once
            continue
        return resp
    raise RoutingError("Routing request failed")


def _summary_from_legs(legs):
    """'I 15, I 70' style description from OSRM/Mapbox leg summaries."""
    names = []
    for leg in legs:
        for part in (leg.get("summary") or "").replace(";", ",").split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return ", ".join(names[:3])


def _parse_osrm_routes(data):
    routes = []
    for r in data.get("routes", []):
        coords = [[lat, lon] for lon, lat in r["geometry"]["coordinates"]]
        if len(coords) < 2:
            continue
        routes.append(
            {
                "coords": coords,
                "distance_mi": r["distance"] / METERS_PER_MILE,
                "duration_min": r["duration"] / 60,
                "summary": _summary_from_legs(r.get("legs", [])),
            }
        )
    return routes


# ---------------------------------------------------------------------------
# Providers: each takes [[lat, lon], ...] waypoints and returns a list of routes
# ---------------------------------------------------------------------------
def fetch_osrm(waypoints, alternatives):
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coord_str}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "true",  # needed for road-name summaries
        "alternatives": str(alternatives) if alternatives else "false",
    }
    resp = _request("GET", url, params=params)
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or data.get("code") != "Ok":
        raise RoutingError(f"OSRM error {resp.status_code}: {data.get('message') or resp.text[:200]}")
    return _parse_osrm_routes(data)


def fetch_mapbox(waypoints, alternatives):
    if not settings.MAPBOX_ACCESS_TOKEN:
        raise RoutingError("MAPBOX_ACCESS_TOKEN is not configured")
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in waypoints)
    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coord_str}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "true" if alternatives and len(waypoints) == 2 else "false",
        "access_token": settings.MAPBOX_ACCESS_TOKEN,
    }
    resp = _request("GET", url, params=params)
    data = resp.json()
    if resp.status_code != 200 or data.get("code") != "Ok":
        raise RoutingError(f"Mapbox error {resp.status_code}: {data.get('message', '')}")
    return _parse_osrm_routes(data)


def fetch_ors(waypoints, alternatives):
    """OpenRouteService with the heavy-goods-vehicle (truck) profile."""
    if not settings.ORS_API_KEY:
        raise RoutingError("ORS_API_KEY is not configured")
    body = {"coordinates": [[lon, lat] for lat, lon in waypoints]}
    straight = haversine_mi(*waypoints[0], *waypoints[-1])
    # ORS only supports alternative_routes for trips under ~100 km.
    if alternatives and len(waypoints) == 2 and straight < 55:
        body["alternative_routes"] = {"target_count": alternatives, "share_factor": 0.6, "weight_factor": 1.6}
    resp = _request(
        "POST",
        "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson",
        json=body,
        headers={"Authorization": settings.ORS_API_KEY},
    )
    if resp.status_code != 200:
        raise RoutingError(f"OpenRouteService error {resp.status_code}: {resp.text[:200]}")
    routes = []
    for f in resp.json().get("features", []):
        props = f["properties"]["summary"]
        routes.append(
            {
                "coords": [[lat, lon] for lon, lat in f["geometry"]["coordinates"]],
                "distance_mi": props["distance"] / METERS_PER_MILE,
                "duration_min": props["duration"] / 60,
                "summary": "",
            }
        )
    return routes


PROVIDERS = {"osrm": fetch_osrm, "mapbox": fetch_mapbox, "ors": fetch_ors}


# ---------------------------------------------------------------------------
# Alternative-route generation
# ---------------------------------------------------------------------------
def via_candidates(origin, dest):
    """Points offset perpendicular to the midpoint of the origin->dest line."""
    (lat1, lon1), (lat2, lon2) = origin, dest
    coslat = math.cos(math.radians((lat1 + lat2) / 2)) or 1e-6
    dx, dy = (lon2 - lon1) * coslat, lat2 - lat1  # locally "flat" coordinates
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    px, py = -dy / length, dx / length  # unit perpendicular
    mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
    return [
        [mid_lat + py * f * length, mid_lon + px * f * length / coslat]
        for f in VIA_OFFSETS
    ]


def _routes_with_alternatives(fetch, origin, dest, count):
    """
    Primary request (with native alternatives) and via-point requests are sent
    in parallel to keep latency to a single round trip (~3 s for OSRM).
    """
    def try_via(via):
        try:
            return fetch([origin, via, dest], 0)
        except RoutingError as exc:
            log.info("Via-point route failed: %s", exc)
            return []

    vias = via_candidates(origin, dest)
    with ThreadPoolExecutor(max_workers=len(vias) + 1) as pool:
        primary_future = pool.submit(fetch, [origin, dest], count)
        via_futures = [pool.submit(try_via, v) for v in vias]
        routes = primary_future.result()  # raises RoutingError -> next provider
        extra = [r for f in via_futures for r in f.result()]

    if not routes:
        raise RoutingError("No route found between origin and destination")

    fastest = min(r["duration_min"] for r in routes)
    for cand in sorted(extra, key=lambda r: r["duration_min"]):
        if len(routes) >= count:
            break
        if cand["duration_min"] > fastest * MAX_DETOUR_FACTOR:
            continue  # unreasonable detour
        if any(overlap_ratio(cand["coords"], r["coords"]) > DUPLICATE_OVERLAP for r in routes):
            continue  # essentially the same road as a route we already have
        routes.append(cand)

    return sorted(routes[:count], key=lambda r: r["duration_min"])


def get_routes(origin, dest, count=3):
    """
    Returns (routes, provider_name, warnings). Each route:
    {coords: [[lat, lon], ...], distance_mi, duration_min, summary}
    """
    warnings = []
    preferred = settings.ROUTING_PROVIDER
    if preferred == "mock":
        return mock.mock_routes(origin, dest), "mock", warnings

    order = [preferred] + [p for p in ("osrm", "ors", "mapbox") if p != preferred]
    for name in order:
        fetch = PROVIDERS.get(name)
        if fetch is None:
            continue
        if name == "ors" and not settings.ORS_API_KEY:
            continue
        if name == "mapbox" and not settings.MAPBOX_ACCESS_TOKEN:
            continue
        try:
            routes = _routes_with_alternatives(fetch, origin, dest, count)
            if len(routes) < count:
                warnings.append(f"Only {len(routes)} distinct route(s) found for this trip.")
            if name != preferred:
                warnings.append(f"{preferred} routing failed; used {name} instead.")
            return routes, name, warnings
        except RoutingError as exc:
            log.warning("Routing provider %s failed: %s", name, exc)
            warnings.append(f"{name}: {exc}")

    if settings.ALLOW_MOCK_FALLBACK:
        warnings.append("All routing providers failed; showing simulated routes.")
        return mock.mock_routes(origin, dest), "mock", warnings
    raise RoutingError("; ".join(warnings) or "Routing failed")
