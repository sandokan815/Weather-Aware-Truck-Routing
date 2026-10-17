"""
Geometry helpers. All coordinates are [lat, lon] pairs (Leaflet order).
"""
import math
from bisect import bisect_left

EARTH_RADIUS_MI = 3958.8
METERS_PER_MILE = 1609.344


def haversine_mi(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(a)))


def cumulative_miles(coords):
    """Cumulative distance (miles) from the first point for every vertex."""
    cum = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_mi(lat1, lon1, lat2, lon2))
    return cum


def point_at_distance(coords, cum, dist):
    """Linearly interpolate the [lat, lon] located `dist` miles along the polyline."""
    if dist <= 0:
        return list(coords[0])
    if dist >= cum[-1]:
        return list(coords[-1])
    i = bisect_left(cum, dist)  # cum[i-1] < dist <= cum[i]
    seg = cum[i] - cum[i - 1]
    t = 0.0 if seg == 0 else (dist - cum[i - 1]) / seg
    (lat1, lon1), (lat2, lon2) = coords[i - 1], coords[i]
    return [lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t]


def checkpoint_miles(total_miles, sample_miles):
    """Mile markers 0, N, 2N, ... plus the destination (always included)."""
    marks = []
    m = 0.0
    while m < total_miles - 1e-6:
        marks.append(round(m, 3))
        m += sample_miles
    marks.append(round(total_miles, 3))
    return marks


def build_checkpoints(coords, total_miles, sample_miles):
    """
    Place checkpoints every `sample_miles` along the route.

    `total_miles` is the routing provider's road distance; the polyline's own
    haversine length can differ slightly, so mile markers are mapped onto the
    geometry proportionally (mile m -> fraction m/total of the polyline).
    """
    cum = cumulative_miles(coords)
    geom_len = cum[-1] or 1.0
    scale = geom_len / total_miles if total_miles > 0 else 1.0
    checkpoints = []
    for idx, mile in enumerate(checkpoint_miles(total_miles, sample_miles)):
        lat, lon = point_at_distance(coords, cum, mile * scale)
        checkpoints.append({"index": idx, "mile": round(mile, 1), "lat": lat, "lon": lon})
    return checkpoints


def downsample(coords, max_points):
    """Keep at most `max_points` vertices (always keeps first and last)."""
    n = len(coords)
    if n <= max_points:
        return coords
    step = (n - 1) / (max_points - 1)
    return [coords[round(i * step)] for i in range(max_points)]


def overlap_ratio(route_a, route_b, tolerance_mi=4.0, samples=40):
    """
    Fraction of sampled points of `route_a` that lie within `tolerance_mi`
    of `route_b`. Used to drop near-duplicate alternative routes.
    """
    a = downsample(route_a, samples)
    b = downsample(route_b, 400)
    close = 0
    for lat, lon in a:
        coslat = math.cos(math.radians(lat))
        # Equirectangular approximation is plenty for a "same road?" test.
        best = min(
            ((lat - blat) ** 2 + ((lon - blon) * coslat) ** 2) for blat, blon in b
        )
        if math.sqrt(best) * 69.0 <= tolerance_mi:
            close += 1
    return close / len(a)
