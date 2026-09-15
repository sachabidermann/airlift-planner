"""Did the airfield survive the shaking?

The nearest airport to an earthquake is often the worst choice, because it
was shaken too. This module turns shaking intensity (MMI) at the airfield
into a rough probability that it can accept relief flights in the first days.

These are judgement figures anchored on recent history, not a fitted model:

  Kathmandu 2015   MMI about VII-VIII   stayed open, but heavy jets damaged the runway
  Port-au-Prince 2010   MMI about IX    runway intact, tower and ATC lost, chaos for days
  Hatay 2023       MMI about IX          runway fractured, closed for days
  Mandalay 2025    MMI about IX          control tower collapsed, closed
  Marrakech 2023   MMI about VI          fully operational, became the hub

The backtests replay those events and print the MMI the model sees at each
of those airports, so anyone can judge the table below.
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
