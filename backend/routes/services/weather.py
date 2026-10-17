"""
Hourly weather from Open-Meteo (free, no key) with a deterministic mock fallback.

One Open-Meteo request can carry many coordinates, so all checkpoints of all
routes are fetched in a few batched calls. Values are requested in Open-Meteo's
default (metric) units and converted here:

  wind_speed_10m  km/h -> mph      (x 0.621371)
  rain + showers  mm   -> in/hr    (x 0.0393701; hourly sums = rate per hour)
  snowfall        cm   -> in/hr    (x 0.393701; Open-Meteo reports snowfall in cm)
  temperature_2m  C    -> F

Rain risk uses liquid precipitation only (rain + showers) so that snow is not
double counted; the total `precipitation` is returned for display.
"""
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache

from . import mock

log = logging.getLogger(__name__)

KMH_TO_MPH = 0.621371
MM_TO_IN = 0.0393701
CM_TO_IN = 0.393701

HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "showers",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
    "weather_code",
]
BATCH_SIZE = 20   # coordinates per Open-Meteo request (smaller batches return faster)
MAX_WORKERS = 6   # parallel requests; Open-Meteo rate-limits bursts, so stay modest

# WMO weather codes -> short description (subset used by Open-Meteo).
WMO_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


class WeatherError(Exception):
    pass


def point_key(lat, lon):
    """Weather grid cells are several km wide; 0.02 deg dedupes nearby points."""
    return (round(lat / 0.02) * 0.02, round(lon / 0.02) * 0.02)


def _num(values, i):
    v = values[i] if i < len(values) else None
    return 0.0 if v is None else float(v)


def _convert(hourly):
    """Open-Meteo hourly block -> list of per-hour dicts in imperial units."""
    n = len(hourly["time"])
    out = []
    for i in range(n):
        rain_mm = _num(hourly["rain"], i) + _num(hourly["showers"], i)
        code = hourly["weather_code"][i]
        out.append(
            {
                "wind_mph": round(_num(hourly["wind_speed_10m"], i) * KMH_TO_MPH, 1),
                "gust_mph": round(_num(hourly["wind_gusts_10m"], i) * KMH_TO_MPH, 1),
                "rain_in_hr": round(rain_mm * MM_TO_IN, 2),
                "snow_in_hr": round(_num(hourly["snowfall"], i) * CM_TO_IN, 2),
                "precip_in_hr": round(_num(hourly["precipitation"], i) * MM_TO_IN, 2),
                "temp_f": round(_num(hourly["temperature_2m"], i) * 9 / 5 + 32, 1),
                "weather_code": code,
                "description": WMO_CODES.get(code, "Unknown") if code is not None else "No data",
            }
        )
    return out


def _fetch_batch(points, start, hours, retries=2):
    end = start + timedelta(hours=hours - 1)
    params = {
        "latitude": ",".join(f"{lat:.3f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.3f}" for _, lon in points),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "GMT",
        "start_hour": start.strftime("%Y-%m-%dT%H:00"),
        "end_hour": end.strftime("%Y-%m-%dT%H:00"),
    }
    resp = requests.get(
        f"{settings.OPEN_METEO_BASE_URL}/v1/forecast",
        params=params,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )
    # DEBUG: raw third-party response, visible when DJANGO_DEBUG=true
    log.debug("Open-Meteo GET %s -> %s in %.2fs: %s", resp.url, resp.status_code, resp.elapsed.total_seconds(), resp.text[:500])
    if resp.status_code == 429 and retries > 0:
        time.sleep(1.5)  # burst limit hit - back off and retry
        return _fetch_batch(points, start, hours, retries - 1)
    if resp.status_code != 200:
        raise WeatherError(f"Open-Meteo HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    data = data if isinstance(data, list) else [data]  # single point -> dict
    if len(data) != len(points):
        raise WeatherError("Open-Meteo returned an unexpected number of locations")
    return [_convert(d["hourly"]) for d in data]


def fetch_hourly(points, start, hours):
    """
    Hourly series for each (lat, lon) in `points`.

    `start` is a UTC datetime truncated to the hour; each returned series has
    `hours` entries where entry i is the forecast for start + i hours.
    Returns (dict point_key -> series, provider_name, warnings).
    """
    keys = list(dict.fromkeys(point_key(lat, lon) for lat, lon in points))
    stamp = start.strftime("%Y%m%d%H")
    result, missing = {}, []
    for k in keys:
        cached = cache.get(f"wx:{k[0]:.2f}:{k[1]:.2f}:{stamp}:{hours}")
        if cached:
            result[k] = cached
        else:
            missing.append(k)

    if settings.WEATHER_PROVIDER == "mock":
        for k in missing:
            result[k] = mock.mock_hourly(k[0], k[1], start, hours)
        return result, "mock", []

    warnings = []
    provider = "open-meteo"
    if missing:
        batches = [missing[i : i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                series_lists = list(pool.map(lambda b: _fetch_batch(b, start, hours), batches))
            for batch, series_list in zip(batches, series_lists):
                for k, series in zip(batch, series_list):
                    result[k] = series
                    cache.set(f"wx:{k[0]:.2f}:{k[1]:.2f}:{stamp}:{hours}", series, 30 * 60)
        except (requests.RequestException, WeatherError, KeyError, ValueError) as exc:
            log.warning("Open-Meteo failed: %s", exc)
            if not settings.ALLOW_MOCK_FALLBACK:
                raise WeatherError(f"Weather service unavailable: {exc}") from exc
            warnings.append(f"Open-Meteo unavailable ({exc}); using simulated weather.")
            provider = "mock"
            for k in missing:
                result[k] = mock.mock_hourly(k[0], k[1], start, hours)
    return result, provider, warnings


def hour_index(start, when):
    """Index of the forecast hour nearest to `when` in a series beginning at `start`."""
    return max(0, math.floor((when - start).total_seconds() / 3600 + 0.5))
