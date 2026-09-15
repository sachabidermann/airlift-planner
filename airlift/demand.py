"""How much relief cargo is needed per day?

Uses PAGER population exposure and minimum humanitarian standards.

  affected  = people at MMI VII or above  (moderate damage begins)
  priority  = people at MMI VIII or above (severe damage; roads often cut,
              so this is the population an airbridge exists for)

Per-person daily cargo is built from public planning figures:
  food      0.50 kg  (about 2,100 kcal of dry rations, WFP planning figure)
  medical   0.02 kg
  shelter   20 kg family kit for 5 people, spread over the first 7 days

Water is deliberately excluded: at 15 L/person/day it is never flown in at
scale; it is treated, trucked or produced locally.
"""

from dataclasses import dataclass

from .usgs import Exposure

FOOD_KG = 0.50
MEDICAL_KG = 0.02
SHELTER_KIT_KG = 20.0
SHELTER_KIT_PEOPLE = 5
FIRST_DAYS = 7

KG_PER_PERSON_DAY = FOOD_KG + MEDICAL_KG + SHELTER_KIT_KG / SHELTER_KIT_PEOPLE / FIRST_DAYS


@dataclass(frozen=True)
class Demand:
    affected: int          # people at MMI >= VII
    priority: int          # people at MMI >= VIII
    tonnes_per_day: float  # daily cargo for the priority population
    kg_per_person_day: float = KG_PER_PERSON_DAY


def estimate(exposure: Exposure | None) -> Demand | None:
    if exposure is None:
        return None
    priority = exposure.at_least(8)
    return Demand(
        affected=exposure.at_least(7),
        priority=priority,
        tonnes_per_day=priority * KG_PER_PERSON_DAY / 1000,
    )
