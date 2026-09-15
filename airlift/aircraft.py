"""Relief aircraft and what they need from a runway.

Approximate public planning figures, not operational data. Real numbers
depend on payload, weather, altitude, fuel and crew judgement. Edit freely.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Aircraft:
    name: str
    min_runway_ft: int      # shortest runway it can realistically use, loaded
    needs_paved: bool       # False = can use gravel / dirt strips
    payload_tonnes: float   # rough cargo per flight
    cruise_kmh: float       # cruising speed
    ground_time_h: float    # time on the ramp to offload and turn around


C130 = Aircraft("C-130J", 3000, False, 19, 640, 1.25)
A400M = Aircraft("A400M", 3000, False, 37, 780, 1.5)
C17 = Aircraft("C-17", 3500, False, 77, 830, 2.25)
C5 = Aircraft("C-5M", 6000, True, 120, 830, 3.0)
B747F = Aircraft("747-8F", 9000, True, 130, 900, 3.0)

AIRCRAFT = [C130, A400M, C17, C5, B747F]

# The workhorse for the short hop from a gateway hub into the damage zone.
SHUTTLE = C130

# OurAirports surface codes that count as paved. Free text, so prefix match.
PAVED_PREFIXES = ("ASP", "CON", "PEM", "BIT", "TAR", "MAC")


def is_paved(surface: str) -> bool:
    return surface.strip().upper().startswith(PAVED_PREFIXES)


def usable_aircraft(runway_ft: int, surface: str) -> list[Aircraft]:
    """Every aircraft that can use a runway of this length and surface."""
    paved = is_paved(surface)
    return [
        a for a in AIRCRAFT
        if runway_ft >= a.min_runway_ft and (paved or not a.needs_paved)
    ]


def biggest_usable(runway_ft: int, surface: str) -> Aircraft | None:
    fits = usable_aircraft(runway_ft, surface)
    return max(fits, key=lambda a: a.payload_tonnes) if fits else None
