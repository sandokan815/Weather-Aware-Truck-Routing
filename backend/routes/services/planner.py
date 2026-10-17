"""
Trip planning pipeline used by POST /api/plan-trip:

  routes -> checkpoints every N miles -> ETA per checkpoint -> weather at ETA
  -> risk per checkpoint -> route summaries -> recommendation
  (+ a 0-48 h corridor forecast per checkpoint for the heatmap slider)
"""
import math
import time
import uuid
from datetime import timedelta, timezone

from django.core.cache import cache

from . import risk, routing, weather
from .geo import auto_sample_miles, build_checkpoints, downsample

CORRIDOR_HOURS = 48          # slider range 0..48 -> 49 hourly frames
MAX_POLYLINE_POINTS = 2500   # trim payload; plenty for display at any zoom
TRIP_CACHE_SECONDS = 60 * 60


def _floor_hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def plan_trip(origin, dest, departure, load_lb, sample_miles=None):
    """
    origin/dest: [lat, lon]; departure: aware datetime; returns the API payload.
    sample_miles: checkpoint spacing; None picks 10/25/50 from the trip length.
    """
    t0 = time.perf_counter()
    departure = departure.astimezone(timezone.utc)

    # 1. Routes -------------------------------------------------------------
    raw_routes, routing_provider, warnings = routing.get_routes(origin, dest, count=3)
    t_routes = time.perf_counter()

    # 2-3. Checkpoints + ETA -------------------------------------------------
    # One spacing for all alternatives (based on the longest) so they compare fairly.
    if sample_miles is None:
        sample_miles = auto_sample_miles(max(r["distance_mi"] for r in raw_routes))
    # checkpoint_eta = departure + (mile / total_miles) * total_duration
    routes = []
    for i, r in enumerate(raw_routes, start=1):
        total_mi, total_min = r["distance_mi"], r["duration_min"]
        cps = build_checkpoints(r["coords"], total_mi, sample_miles)
        for cp in cps:
            frac = cp["mile"] / total_mi if total_mi else 0.0
            cp["eta"] = departure + timedelta(minutes=frac * total_min)
        routes.append(
            {
                "id": i,
                "name": f"Route {i}",
                "via": r["summary"],
                "coordinates": downsample(r["coords"], MAX_POLYLINE_POINTS),
                "total_miles": round(total_mi, 1),
                "total_duration_min": round(total_min, 1),
                "checkpoints": cps,
            }
        )

    # 4. Weather: one batched fetch covering every checkpoint and the whole
    #    window [departure, departure + max(48h, longest trip)].
    start = _floor_hour(departure)
    longest_h = max(r["total_duration_min"] for r in routes) / 60
    hours = math.ceil(max(CORRIDOR_HOURS, longest_h)) + 2
    points = [(cp["lat"], cp["lon"]) for r in routes for cp in r["checkpoints"]]
    series_by_key, weather_provider, wx_warnings = weather.fetch_hourly(points, start, hours)
    warnings += wx_warnings
    t_weather = time.perf_counter()

    dep_idx = weather.hour_index(start, departure)
    corridor = {}
    for r in routes:
        frames = []
        for cp in r["checkpoints"]:
            series = series_by_key[weather.point_key(cp["lat"], cp["lon"])]

            # 4-5. Weather at this checkpoint's ETA + risk
            idx = min(weather.hour_index(start, cp["eta"]), len(series) - 1)
            wx = series[idx]
            cp["weather"] = wx
            cp["risk"] = risk.assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb)
            cp["eta_iso"] = cp.pop("eta").isoformat()
            cp["lat"], cp["lon"] = round(cp["lat"], 5), round(cp["lon"], 5)

            # Corridor heatmap: conditions at this spot for hour 0..48 after departure.
            window = series[dep_idx : dep_idx + CORRIDOR_HOURS + 1]
            frames.append(
                {
                    "mile": cp["mile"],
                    "lat": cp["lat"],
                    "lon": cp["lon"],
                    "wind": [h["wind_mph"] for h in window],
                    "rain": [h["rain_in_hr"] for h in window],
                    "snow": [h["snow_in_hr"] for h in window],
                    "risk": [
                        risk.risk_level(h["wind_mph"], h["rain_in_hr"], h["snow_in_hr"], load_lb)
                        for h in window
                    ],
                }
            )
        corridor[r["id"]] = frames

        # 6. Summary
        r["summary"] = risk.summarize_route(
            r["checkpoints"], r["total_miles"], r["total_duration_min"]
        )

    # 7. Recommendation
    ranking, best_id, reason = risk.recommend(routes)
    for r in routes:
        r["recommended"] = r["id"] == best_id
        r["rank"] = ranking.index(r["id"]) + 1

    trip_id = uuid.uuid4().hex
    corridor_payload = {
        "start_iso": departure.isoformat(),
        "hours": CORRIDOR_HOURS,
        "routes": corridor,
    }
    cache.set(f"trip:{trip_id}:corridor", corridor_payload, TRIP_CACHE_SECONDS)

    return {
        "trip_id": trip_id,
        "origin": {"lat": origin[0], "lon": origin[1]},
        "destination": {"lat": dest[0], "lon": dest[1]},
        "departure_iso": departure.isoformat(),
        "load_weight_lb": load_lb,
        "sample_miles": sample_miles,
        "routes": routes,
        "recommended_route_id": best_id,
        "ranking": ranking,
        "recommendation_reason": reason,
        "corridor": corridor_payload,
        "data_sources": {"routing": routing_provider, "weather": weather_provider},
        "warnings": warnings,
        "timing_ms": {
            "routing": round((t_routes - t0) * 1000),
            "weather": round((t_weather - t_routes) * 1000),
            "total": round((time.perf_counter() - t0) * 1000),
        },
    }


def get_corridor(trip_id, route_id=None):
    data = cache.get(f"trip:{trip_id}:corridor")
    if data is None:
        return None
    if route_id is None:
        return data
    frames = data["routes"].get(int(route_id))
    if frames is None:
        return None
    return {**data, "routes": {int(route_id): frames}}
