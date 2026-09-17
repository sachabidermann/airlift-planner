"""Probability that an airfield can take relief flights after shaking.

Maps shaking intensity (MMI) at the airfield to the probability that it can
take relief flights in the first three days. The curve is a judgment call. It
was set by hand while looking at the five international earthquakes below, so
for those the backtests check consistency, not out-of-sample skill. The four
US events were added later and the curve was left unchanged; Oakland,
Anchorage and China Lake are listed here.

  Marrakech 2023       MMI VI     no major damage, became the relief gateway
  Oakland 1989         MMI VII    lost 3,000 ft of runway to liquefaction (a miss: see below)
  Kathmandu 2015       MMI VII    stayed open; runway later damaged by heavy jets
  Anchorage 2018       MMI VII    tower evacuated, reopened the same day
  Gaziantep 2023       MMI VII    closed to passengers, took relief flights
  Kahramanmaras 2023   MMI VIII   closed to passengers, took relief flights (the curve flags it: a false alarm)
  Port-au-Prince 2010  MMI VIII   runway intact, tower unusable, field saturated
  China Lake 2019      MMI VIII   declared not mission capable (a miss: the curve gives 64%)
  Hatay 2023           MMI IX     runway fractured, closed six days
  Nay Pyi Taw 2025     MMI IX     control tower collapsed; closed to commercial flights for a week, relief flights from day 2
  Mandalay 2025        MMI IX-X   runway, terminal and radar damage; closed to commercial flights for a week, relief flights from day 4

Published alternatives exist and are the first planned replacement. FEMA's
Hazus earthquake model (Technical Manual, section 7.7) has fragility curves
for control towers, terminals and fuel facilities, and treats runway damage
as a ground-failure problem: "Little damage is attributed to ground shaking."
That is the Oakland miss: intensity does not see soft fill. Roark, Truman and
Gould (2000) published an airport functionality curve against peak ground
acceleration for the New Madrid region.
"""

import math

# (mmi, probability the airfield is usable)
USABILITY = [
    (5.0, 1.00),
    (6.0, 0.97),
    (7.0, 0.90),
    (8.0, 0.60),
    (9.0, 0.30),
    (10.0, 0.10),
]


def runway_usability(mmi: float) -> float:
    """Probability (0-1) that an airfield at this MMI can take relief flights. Linear between points."""
    if mmi <= USABILITY[0][0]:
        return USABILITY[0][1]
    if mmi >= USABILITY[-1][0]:
        return USABILITY[-1][1]
    for (m0, p0), (m1, p1) in zip(USABILITY, USABILITY[1:]):
        if m0 <= mmi <= m1:
            return p0 + (p1 - p0) * (mmi - m0) / (m1 - m0)
    return USABILITY[-1][1]


def roman(mmi: float) -> str:
    """MMI as a Roman numeral, halves rounded up (6.5 is VII), as the dashboard does."""
    numerals = ["-", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    return numerals[max(0, min(10, math.floor(mmi + 0.5)))]
