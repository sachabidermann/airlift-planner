"""Daily relief cargo needed, from population exposure.

Exposure comes from USGS PAGER, or from the Census reconstruction in
population.py when PAGER was not run.

  affected  = people at MMI VII or above  (moderate damage begins)
  priority  = people at MMI VIII or above (severe damage; the population an
              airbridge exists for)

Cargo per person per day:
  food      0.56 kg   a 2,100 kcal general ration weighs 550-590 g (UNHCR/UNICEF/WFP/WHO,
                      Food and Nutrition Needs in Emergencies, Table 2); 2,100 kcal is the
                      Sphere minimum
  medical   0.02 kg   judgment allowance for trauma supplies; the Interagency Emergency
                      Health Kit works out to about 0.0014 kg, so this is generous
  shelter   19.4 kg   IFRC shelter kit per family of five (11 kg tool kit plus two
                      4.2 kg tarpaulins), delivered once, spread over the first 7 days

Water is excluded. At the Sphere minimum of 15 liters per person per day it
is rarely flown in at scale; it is treated, trucked or produced locally.
Source links are in METHOD.md.
"""

from dataclasses import dataclass

from .usgs import Exposure

FOOD_KG = 0.56
MEDICAL_KG = 0.02
SHELTER_KIT_KG = 19.4
SHELTER_KIT_PEOPLE = 5
FIRST_DAYS = 7

KG_PER_PERSON_DAY = FOOD_KG + MEDICAL_KG + SHELTER_KIT_KG / SHELTER_KIT_PEOPLE / FIRST_DAYS

# Below this daily need the "share of need" figure is meaningless and is not shown.
NEGLIGIBLE_TPD = 5


@dataclass(frozen=True)
class Demand:
    affected: int          # people at MMI >= VII
    priority: int          # people at MMI >= VIII
    tonnes_per_day: float  # daily cargo for the priority population, metric tons
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
