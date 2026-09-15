"""Small geography helpers."""

import math

EARTH_RADIUS_KM = 6371.0

# US territories count as the same country as the mainland for gateway choice:
# no border, no customs, same military airlift.
US_ALIASES = {"US": "US", "PR": "US", "VI": "US", "GU": "US", "MP": "US", "AS": "US"}


def same_country(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return US_ALIASES.get(a, a) == US_ALIASES.get(b, b)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points (the haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
