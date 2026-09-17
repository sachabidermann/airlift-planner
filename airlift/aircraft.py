"""Relief aircraft and what they need from a runway.

Payloads are planning payloads, not maximums, and ground times are expedited
offload times, both from Air Force Pamphlet 10-1403, Air Mobility Planning
Factors (2018), Tables 3 and 5. The A400M and 747-8F are not in the pamphlet;
their payloads are 75% of the manufacturer's maximum, the same ratio the
pamphlet implies for the C-17 and C-5M, and their ground times are judgment.
Sources for every number are listed in METHOD.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Aircraft:
    name: str
    min_runway_ft: int      # shortest runway it can use (AFPAM Table 1, manufacturer data)
    needs_paved: bool       # False = can use gravel or dirt strips
    payload_tonnes: float   # planning payload per flight, metric tons
    ground_time_h: float    # hours on the ramp to offload and turn around


C130 = Aircraft("C-130J-30", 3000, False, 16.3, 1.75)
A400M = Aircraft("A400M", 3000, False, 28.0, 2.0)
C17 = Aircraft("C-17", 3500, False, 59.0, 2.25)
C5 = Aircraft("C-5M", 6000, True, 90.7, 3.75)
B747F = Aircraft("747-8F", 9000, True, 100.0, 3.0)

AIRCRAFT = [C130, A400M, C17, C5, B747F]

# Aircraft used for the gateway-to-strip leg, and its block speed on short legs
# (AFPAM Table 4: 286 knots on a 500 nm leg).
SHUTTLE = C130
SHUTTLE_BLOCK_KMH = 530

# OurAirports surface text that counts as paved. Free text, so prefix match.
# A blank surface is treated as unpaved, which is the conservative direction.
PAVED_PREFIXES = ("ASP", "CON", "PEM", "BIT", "TAR", "MAC", "PAV", "HARD", "CEM", "COMPOSITE")


def is_paved(surface: str) -> bool:
    return surface.strip().upper().startswith(PAVED_PREFIXES)


def usable_aircraft(runway_ft: int, surface: str) -> list[Aircraft]:
    """Every aircraft that can use a runway of this length and surface."""
    paved = is_paved(surface)
    return [a for a in AIRCRAFT if runway_ft >= a.min_runway_ft and (paved or not a.needs_paved)]


def biggest_usable(runway_ft: int, surface: str) -> Aircraft | None:
    fits = usable_aircraft(runway_ft, surface)
    return max(fits, key=lambda a: a.payload_tonnes) if fits else None
