"""Match a quake to the airfields around it."""

import math
from dataclasses import dataclass

from .aircraft import Aircraft, usable_aircraft
from .airports import Airport
from .quakes import Quake

EARTH_RADIUS_KM = 6371.0


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points (the haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Option:
    airport: Airport
    distance_km: float
    aircraft: list[Aircraft]


def plan(quake: Quake, airports: list[Airport], radius_km: float = 300) -> list[Option]:
    """Airfields within radius_km of the quake that at least one aircraft can use.

    Sorted nearest first.
    """
    options = []
    for airport in airports:
        d = distance_km(quake.lat, quake.lon, airport.lat, airport.lon)
        if d > radius_km:
            continue
        fits = usable_aircraft(airport.longest_runway_ft, airport.surface)
        if not fits:
            continue
        options.append(Option(airport=airport, distance_km=d, aircraft=fits))
    options.sort(key=lambda o: o.distance_km)
    return options
