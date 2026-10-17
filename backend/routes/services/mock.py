"""
Deterministic mock routing + weather, used when external APIs are unreachable
(or when ROUTING_PROVIDER / WEATHER_PROVIDER = "mock"). Lets the whole app run
offline and makes demos reproducible.
"""
import math
from datetime import timedelta

from .geo import cumulative_miles, haversine_mi


def mock_routes(origin, dest):
    """Three synthetic routes: direct-ish, bowed left, bowed right."""
    (lat1, lon1), (lat2, lon2) = origin, dest
    routes = []
    for bow, speed_mph, label in ((0.0, 58, "Mock direct"), (0.18, 55, "Mock north"), (-0.22, 56, "Mock south")):
        coords = []
        n = 120
        for i in range(n + 1):
            t = i / n
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t
            # Perpendicular bow (sin curve) plus a small wiggle so it looks like a road.
            offset = bow * math.sin(math.pi * t) + 0.01 * math.sin(t * 40)
            lat += -(lon2 - lon1) * offset
            lon += (lat2 - lat1) * offset
            coords.append([lat, lon])
        miles = cumulative_miles(coords)[-1] * 1.12  # roads are longer than lines
        routes.append(
            {
                "coords": coords,
                "distance_mi": miles,
                "duration_min": miles / speed_mph * 60,
                "summary": label,
            }
        )
    return routes


# A synthetic storm that drifts east-north-east over time. Centered roughly on
# the Colorado Rockies / Utah so LA -> Denver demos show variation.
STORM_START = (38.8, -110.5)
STORM_DRIFT_DEG_PER_HR = (0.05, 0.25)
STORM_RADIUS_MI = 160


def mock_hourly(lat, lon, start, hours):
    series = []
    for h in range(hours):
        when = start + timedelta(hours=h)
        clat = STORM_START[0] + STORM_DRIFT_DEG_PER_HR[0] * h
        clon = STORM_START[1] + STORM_DRIFT_DEG_PER_HR[1] * h
        d = haversine_mi(lat, lon, clat, clon)
        strength = max(0.0, 1 - d / STORM_RADIUS_MI)  # 1 at the core, 0 outside
        diurnal = 0.5 + 0.5 * math.sin((when.hour - 9) / 24 * 2 * math.pi)
        cold = lat > 37.5 or (lon > -112 and lat > 35.5)
        temp_f = 70 - (lat - 32) * 3 - 8 * strength - 6 * (1 - diurnal)
        wind = 8 + 6 * diurnal + 52 * strength ** 1.2
        precip = 0.6 * strength ** 1.5
        snow = precip * 2.2 if cold and temp_f < 36 else 0.0
        rain = 0.0 if snow else precip
        code = 0 if strength == 0 else (73 if snow else 63)
        series.append(
            {
                "wind_mph": round(wind, 1),
                "gust_mph": round(wind * 1.4, 1),
                "rain_in_hr": round(rain, 2),
                "snow_in_hr": round(snow, 2),
                "precip_in_hr": round(precip, 2),
                "temp_f": round(temp_f, 1),
                "weather_code": code,
                "description": "Simulated " + ("snow" if snow else "rain" if rain else "clear"),
            }
        )
    return series
