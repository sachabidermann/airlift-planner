"""Plan a two-tier airbridge for an earthquake.

Heavy jets fly into a gateway airport. C-130s shuttle cargo from there into
airfields inside the damage zone. Steps:

  1. find the center of the damage, weighted by shaking and by where people are
  2. score every airfield in range: shaking, usability, which aircraft fit
  3. work out every candidate gateway in full and keep the one that moves the
     most cargo into the zone, preferring gateways in the affected country
  4. spread the shuttle fleet over forward strips
  5. compare capacity with estimated need

Throughput follows Air Force Pamphlet 10-1403, Air Mobility Planning Factors
(2018), formula 9.0:

    tons per day = parking spots x planning payload x operating hours / ground time x 0.85

The 0.85 is the pamphlet's queuing efficiency. Parking spots ("maximum on
ground", MOG) are assumed from airport size, because real ramp plans are not
public. The result is a ceiling for those assumed spots, not a forecast: every
limit left out (fuel, handling, crews, airspace, aircraft availability) can
only lower it, while the spot counts themselves are guesses that can be wrong
in either direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import demand as demand_model
from .aircraft import C17, SHUTTLE, SHUTTLE_BLOCK_KMH, Aircraft, biggest_usable
from .airports import Airport
from .geo import distance_km, same_country
from .survivability import runway_usability
from .usgs import Event


@dataclass(frozen=True)
class Assumptions:
    ops_hours: float = 20          # airfield operating hours per day (AFPAM tabulates 10, 16 and 24)
    shuttle_fleet: int = 12        # C-130s available for the gateway-to-strip leg
    queue_efficiency: float = 0.85  # AFPAM 10-1403 formula 9.0
    gateway_max_km: float = 1000   # how far a gateway may be from the damage center
    gateway_min_runway_ft: int = 7000
    forward_max_km: float = 150    # inside the zone if this close to the damage center...
    zone_min_mmi: float = 6.5      # ...or if shaken this hard (handles long ruptures)
    forward_min_runway_ft: int = 3000
    min_usability: float = 0.5     # below this an airfield is flagged as likely knocked out
    road_reach_km: float = 50      # cargo landing this close to the damage center counts in full;
                                   # the share falls in a straight line to zero at forward_max_km
    min_sorties: float = 0.5       # a strip that gets less than this per day is not used
    near_tie: float = 0.10         # gateways within this share of the best are treated as equal; the nearer wins
    domestic_only: bool = True     # forward strips must be in the affected country
    # Assumed working parking spots by OurAirports size class. Port-au-Prince in
    # 2010 could unload six aircraft at once at first and nine later (Veatch and
    # Goentzel 2018).
    mog_gateway: dict = field(default_factory=lambda: {"large_airport": 6, "medium_airport": 3})   # small airports are never gateways
    mog_forward: dict = field(default_factory=lambda: {"large_airport": 3, "medium_airport": 2, "small_airport": 1})


@dataclass(frozen=True)
class Field:
    """An airport evaluated for one earthquake."""

    airport: Airport
    dist_km: float          # to the damage center
    mmi: float
    usability: float
    best_aircraft: Aircraft | None
    in_zone: bool


@dataclass(frozen=True)
class Gateway:
    field: Field
    aircraft: Aircraft
    inflow_tpd: float       # metric tons per day the gateway can receive


@dataclass(frozen=True)
class Forward:
    field: Field
    leg_km: float           # gateway to strip
    cycle_h: float          # round trip including both turnarounds
    sorties_per_day: float
    credit: float           # share of this strip's cargo that counts as inside the zone
    tonnes_per_day: float   # after usability and credit


@dataclass(frozen=True)
class Option:
    """One candidate gateway, worked out in full."""

    gateway: Gateway
    forwards: list[Forward]
    delivered_tpd: float


@dataclass
class Plan:
    event: Event
    center: tuple[float, float]
    center_basis: str               # what the center was weighted by
    country: str | None             # ISO-2 code of the most affected country
    demand: demand_model.Demand | None
    chosen: Option | None
    alternatives: list[Option]      # the best option on the other side of the domestic/foreign split
    people_sustained: float
    coverage: float | None
    traps: list[Field]              # in-zone airfields flagged as likely knocked out
    naive_pick: Field | None        # what a nearest-airfield rule would choose
    assumptions: Assumptions
    fields: list[Field]
    gateway_candidates: int = 0     # airports that passed the gateway filters, whether or not any could reach the zone

    @property
    def gateway(self) -> Gateway | None:
        return self.chosen.gateway if self.chosen else None

    @property
    def forwards(self) -> list[Forward]:
        return self.chosen.forwards if self.chosen else []

    @property
    def delivered_tpd(self) -> float:
        return self.chosen.delivered_tpd if self.chosen else 0.0


# --------------------------------------------------------------------------- steps


def damage_center(event: Event, airports: list[Airport] | None = None) -> tuple[tuple[float, float], str]:
    """Center of the damage: mean position weighted by (MMI - 6) and by people.

    People come from the event (PAGER's city list, or Census points). Without
    them, airfields stand in as a land proxy so an offshore rupture is not
    centered on open water. Without a ShakeMap it is the epicenter.
    """
    q = event.quake
    if event.shake is None:
        return (q.lat, q.lon), "epicenter"
    grid = event.shake
    if event.people:
        source, basis = event.people, "shaking and population"
    elif airports:
        source, basis = [(ap.lat, ap.lon, 1.0) for ap in airports if grid.covers(ap.lat, ap.lon)], "shaking and airfield locations"
    else:
        source, basis = [], ""
    w_sum = lat_sum = lon_sum = 0.0
    for lat, lon, n in source:
        w = (grid.mmi_at(lat, lon) - 6.0) * n
        if w > 0:
            w_sum, lat_sum, lon_sum = w_sum + w, lat_sum + w * lat, lon_sum + w * grid._wrap(lon)
    if w_sum == 0:
        basis = "shaking"
        for lat, lon, mmi in grid.cells():
            w = mmi - 6.0
            if w > 0:
                w_sum, lat_sum, lon_sum = w_sum + w, lat_sum + w * lat, lon_sum + w * lon
    if w_sum == 0:
        return (q.lat, q.lon), "epicenter"
    return (lat_sum / w_sum, (lon_sum / w_sum + 180) % 360 - 180), basis


def evaluate_fields(event: Event, airports: list[Airport], center, a: Assumptions) -> list[Field]:
    fields = []
    for ap in airports:
        d = distance_km(center[0], center[1], ap.lat, ap.lon)
        if d > a.gateway_max_km:
            continue
        mmi = event.mmi_at(ap.lat, ap.lon)
        fields.append(
            Field(
                airport=ap,
                dist_km=d,
                mmi=mmi,
                usability=runway_usability(mmi),
                best_aircraft=biggest_usable(ap.longest_runway_ft, ap.surface, ap.width_ft),
                in_zone=(d <= a.forward_max_km or mmi >= a.zone_min_mmi),
            )
        )
    fields.sort(key=lambda f: f.dist_km)
    return fields


def gateway_candidates(fields: list[Field], a: Assumptions) -> list[Gateway]:
    out = []
    for f in fields:
        ap = f.airport
        if ap.kind not in ("large_airport", "medium_airport"):
            continue
        if ap.longest_runway_ft < a.gateway_min_runway_ft or f.best_aircraft is None:
            continue
        if f.usability < a.min_usability:
            continue
        ac = f.best_aircraft
        # Medium airports rarely have the pavement strength or ramp for a C-5 or 747.
        if ap.kind == "medium_airport" and ac.payload_tonnes > C17.payload_tonnes:
            ac = C17
        turns = a.ops_hours / ac.ground_time_h
        inflow = a.mog_gateway[ap.kind] * ac.payload_tonnes * turns * a.queue_efficiency * f.usability
        out.append(Gateway(field=f, aircraft=ac, inflow_tpd=inflow))
    out.sort(key=lambda g: g.inflow_tpd, reverse=True)
    return out


def forward_candidates(fields: list[Field], country: str | None, a: Assumptions) -> list[Field]:
    return [
        f for f in fields
        if f.in_zone
        and f.airport.longest_runway_ft >= a.forward_min_runway_ft
        and f.best_aircraft is not None          # long enough, and wide enough for a C-130
        and f.usability >= a.min_usability
        and (not a.domestic_only or country is None or same_country(f.airport.country, country))
    ]


def direct_credit(dist_km: float, a: Assumptions) -> float:
    """Share of cargo landing this far from the damage center that reaches it by road in the first days."""
    if dist_km <= a.road_reach_km:
        return 1.0
    if dist_km >= a.forward_max_km:
        return 0.0
    return 1.0 - (dist_km - a.road_reach_km) / (a.forward_max_km - a.road_reach_km)


def strip_credit(f: Field, a: Assumptions) -> float:
    """Same rule for forward strips: full credit inside the shaken area, road credit otherwise."""
    return 1.0 if f.mmi >= a.zone_min_mmi else direct_credit(f.dist_km, a)


def allocate_shuttles(gw: Gateway, strips: list[Field], a: Assumptions) -> list[Forward]:
    """Spread the shuttle fleet over forward strips, best tons per flight hour first."""
    legs = []
    for s in strips:
        if s.airport.ident == gw.field.airport.ident:
            continue
        credit = strip_credit(s, a)
        if credit <= 0:
            continue
        leg = distance_km(gw.field.airport.lat, gw.field.airport.lon, s.airport.lat, s.airport.lon)
        cycle = 2 * leg / SHUTTLE_BLOCK_KMH + 2 * SHUTTLE.ground_time_h
        max_sorties = a.ops_hours / cycle * a.mog_forward[s.airport.kind] * a.queue_efficiency   # ramp limit
        per_sortie = SHUTTLE.payload_tonnes * s.usability * credit
        legs.append((per_sortie / cycle, s, leg, cycle, max_sorties, credit, per_sortie))
    legs.sort(key=lambda x: x[0], reverse=True)

    fleet_hours = a.shuttle_fleet * a.ops_hours
    out = []
    for _, s, leg, cycle, max_sorties, credit, per_sortie in legs:
        if fleet_hours <= 1e-9:
            break
        sorties = min(max_sorties, fleet_hours / cycle)
        if sorties < a.min_sorties:
            continue
        fleet_hours -= sorties * cycle
        out.append(Forward(field=s, leg_km=leg, cycle_h=cycle, sorties_per_day=sorties,
                           credit=credit, tonnes_per_day=sorties * per_sortie))
    return out


def work_out(gw: Gateway, strips: list[Field], a: Assumptions) -> Option:
    forwards = allocate_shuttles(gw, strips, a)
    forwarded = sum(f.tonnes_per_day for f in forwards)
    # Cargo reaches the zone by road from a close gateway and by shuttle. It
    # can never exceed what lands at the gateway.
    by_road = gw.inflow_tpd * direct_credit(gw.field.dist_km, a)
    return Option(gateway=gw, forwards=forwards, delivered_tpd=min(gw.inflow_tpd, by_road + forwarded))


def pick(options: list[Option], a: Assumptions) -> Option | None:
    """The nearest of the options whose capacity is within `near_tie` of the best.

    A few percent of capacity is inside the model's precision, so it should not
    outrank being closer to the damage. Options that move nothing are ignored.
    """
    options = [o for o in options if o.delivered_tpd > 0]
    if not options:
        return None
    best = max(o.delivered_tpd for o in options)
    close = [o for o in options if o.delivered_tpd >= best * (1 - a.near_tie)]
    return min(close, key=lambda o: (o.gateway.field.dist_km, -o.delivered_tpd))


# --------------------------------------------------------------------------- main entry


def build_plan(event: Event, airports: list[Airport], a: Assumptions | None = None) -> Plan:
    a = a or Assumptions()
    center, basis = damage_center(event, airports)
    fields = evaluate_fields(event, airports, center, a)
    dem = demand_model.estimate(event.exposure)

    known = {ap.country for ap in airports}
    country = event.exposure.main_country(valid=known) if event.exposure else None
    if country is None and fields:
        country = fields[0].airport.country
    strips = forward_candidates(fields, country, a)

    # Every candidate is worked out in full; pre-ranking on inflow would drop a
    # slightly shaken airport near the damage in favor of distant ones.
    cands = gateway_candidates(fields, a)
    options = [work_out(gw, strips, a) for gw in cands]
    best_domestic = pick([o for o in options if same_country(o.gateway.field.airport.country, country)], a)
    best_foreign = pick([o for o in options if not same_country(o.gateway.field.airport.country, country)], a)

    # Domestic first; a cross-border gateway needs clearance. Foreign only if
    # nothing domestic can move anything into the zone.
    chosen = best_domestic or best_foreign
    alternatives = [best_foreign] if best_domestic and best_foreign else []

    delivered = chosen.delivered_tpd if chosen else 0.0
    people = delivered * 1000 / demand_model.KG_PER_PERSON_DAY
    coverage = (delivered / dem.tonnes_per_day) if dem and dem.tonnes_per_day > 0 else None

    traps = [
        f for f in fields
        if f.in_zone
        and f.airport.longest_runway_ft >= a.forward_min_runway_ft
        and f.best_aircraft is not None
        and f.usability < a.min_usability
    ]
    naive = next((f for f in fields if f.airport.longest_runway_ft >= a.forward_min_runway_ft and f.best_aircraft is not None), None)

    return Plan(
        event=event, center=center, center_basis=basis, country=country, demand=dem,
        chosen=chosen, alternatives=alternatives, people_sustained=people, coverage=coverage,
        traps=traps, naive_pick=naive, assumptions=a, fields=fields, gateway_candidates=len(cands),
    )
