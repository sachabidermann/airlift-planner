"""Relief aircraft and what they need from a runway.

These are approximate public planning figures, not operational data.
Real requirements depend on payload, weather, altitude and crew judgement.
Edit freely.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Aircraft:
    name: str
    min_runway_ft: int      # shortest runway it can realistically use, loaded
    needs_paved: bool       # False = can land on gravel / dirt strips
    payload_tonnes: int     # rough maximum cargo


AIRCRAFT = [
    Aircraft("C-130J", min_runway_ft=3000, needs_paved=False, payload_tonnes=19),
    Aircraft("A400M", min_runway_ft=3000, needs_paved=False, payload_tonnes=37),
    Aircraft("C-17", min_runway_ft=3500, needs_paved=False, payload_tonnes=77),
    Aircraft("C-5M", min_runway_ft=6000, needs_paved=True, payload_tonnes=120),
    Aircraft("747-8F", min_runway_ft=9000, needs_paved=True, payload_tonnes=130),
]

# OurAirports surface codes that count as paved. The field is free text,
# so we match on common prefixes.
PAVED_PREFIXES = ("ASP", "CON", "PEM", "BIT", "TAR", "MAC")


def is_paved(surface: str) -> bool:
    return surface.strip().upper().startswith(PAVED_PREFIXES)


def usable_aircraft(runway_ft: int, surface: str) -> list[Aircraft]:
    """Return every aircraft that can use a runway of this length and surface."""
    paved = is_paved(surface)
    return [
        a for a in AIRCRAFT
        if runway_ft >= a.min_runway_ft and (paved or not a.needs_paved)
    ]
