"""Did the airfield survive the shaking?

Turns shaking intensity (MMI) at an airfield into a probability that it can
accept relief flights in the first days. Judgement figures anchored on
history, not a fitted model:

  Kathmandu 2015        MMI about VII    stayed open, but heavy jets damaged the runway
  Port-au-Prince 2010   MMI about VIII   runway intact, tower and ATC lost, chaos for days
  Anchorage 2018        MMI about VII    inspected and reopened the same day
  Gaziantep 2023        MMI about VII    stayed open, took relief flights
  Kahramanmaras 2023    MMI about VIII   stayed open (the curve's one false alarm)
  Hatay 2023            MMI about IX     runway fractured, closed for days
  Mandalay 2025         MMI about IX     control tower collapsed, closed
  Marrakech 2023        MMI about VI     fully operational, became the hub
  Oakland 1989          MMI about VI     main runway cracked by liquefaction: a miss.
                                         Intensity alone does not see soft fill.

The backtests print the MMI the model sees at each of these airports.
"""

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
    """Probability (0-1) that an airfield at this MMI can take relief flights."""
    if mmi <= USABILITY[0][0]:
        return USABILITY[0][1]
    if mmi >= USABILITY[-1][0]:
        return USABILITY[-1][1]
    for (m0, p0), (m1, p1) in zip(USABILITY, USABILITY[1:]):
        if m0 <= mmi <= m1:
            return p0 + (p1 - p0) * (mmi - m0) / (m1 - m0)
    return USABILITY[-1][1]


def roman(mmi: float) -> str:
    """MMI is traditionally written in Roman numerals."""
    numerals = ["-", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    return numerals[max(0, min(10, round(mmi)))]
