"""Design a two-tier airbridge for an earthquake.

Real relief airlifts are hub-and-spoke: heavy jets fly into a large,
undamaged "gateway" airport, and smaller aircraft shuttle cargo the last
100-200 km into strips inside the damage zone. The binding constraints are
ramp space (how many aircraft can be on the ground at once) and turnaround
time, not runway length.

This module:
  1. finds the centre of the damage (shaking-weighted, not the epicentre)
  2. scores every airfield nearby for shaking damage and aircraft fit
  3. picks the gateway that maximises cargo actually delivered into the zone,
     preferring one inside the affected country
  4. allocates a shuttle fleet across forward strips
  5. compares delivered tonnes per day with estimated demand
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import demand as demand_model
from .aircraft import C17, SHUTTLE, Aircraft, biggest_usable
from .airports import Airport
from .geo import distance_km, same_country
from .survivability import runway_usability
from .usgs import Event


@dataclass(frozen=True)
class Assumptions:
    ops_hours: float = 20          # flying hours per day (night ops, crew limits)
    shuttle_fleet: int = 12        # C-130-class aircraft available for the forward leg
    gateway_max_km: float = 1000   # how far a gateway may be from the damage centre
    gateway_min_runway_ft: int = 7000
    forward_max_km: float = 150    # inside the zone if this close to the damage centre...
    zone_min_mmi: float = 6.5      # ...or if shaken this hard (handles long ruptures)
    forward_min_runway_ft: int = 3000
    min_usability: float = 0.5     # below this an airfield is "likely knocked out"
    road_reach_km: float = 50      # cargo landing this close to the damage centre counts in full;
                                   # credit fades to zero at forward_max_km (trucks, first days)
    domestic_only: bool = True     # forward strips must be in the affected country
    # Cargo parking spots by airport size ("maximum on ground").
    mog_gateway: dict = field(default_factory=lambda: {"large_airport": 6, "medium_airport": 3, "small_airport": 1})
    mog_forward: dict = field(default_factory=lambda: {"large_airport": 3, "medium_airport": 2, "small_airport": 1})


@dataclass(frozen=True)
class Field:
    """An airport evaluated for this particular earthquake."""

    airport: Airport
    dist_km: float          # to the damage centre
    mmi: float
    usability: float
    best_aircraft: Aircraft | None
    in_zone: bool


@dataclass(frozen=True)
class Gateway:
    field: Field
    aircraft: Aircraft
    inflow_tpd: float       # expected tonnes/day arriving from outside


@dataclass(frozen=True)
class Forward:
    field: Field
    leg_km: float           # gateway to strip
    cycle_h: float          # round trip including both turnarounds
    sorties_per_day: float
    tonnes_per_day: float


@dataclass(frozen=True)
class Option:
    """One candidate gateway, fully worked out."""

    gateway: Gateway
    forwards: list[Forward]
    delivered_tpd: float


@dataclass
class Plan:
    event: Event
    centre: tuple[float, float]
    country: str | None             # ISO-2 code of the most affected country
    demand: demand_model.Demand | None
    chosen: Option | None
    alternatives: list[Option]      # next-best options, domestic and foreign
    people_sustained: float
    coverage: float | None
    traps: list[Field]              # in-zone airfields likely knocked out
    naive_pick: Field | None        # what "nearest airfield" logic would choose
    assumptions: Assumptions
    fields: list[Field]             # everything evaluated, for the map

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


def damage_centre(event: Event) -> tuple[float, float]:
    """Shaking-weighted centre of the MMI >= VI area; epicentre if unavailable."""
    q = event.quake
    if event.shake is None:
        return q.lat, q.lon
    w_sum = lat_sum = lon_sum = 0.0
    for lat, lon, mmi in event.shake.cells():
        w = mmi - 6.0
        if w <= 0:
            continue
        w_sum += w
        lat_sum += w * lat
        lon_sum += w * lon
    if w_sum == 0:
        return q.lat, q.lon
    return lat_sum / w_sum, lon_sum / w_sum


def evaluate_fields(event: Event, airports: list[Airport], centre, a: Assumptions) -> list[Field]:
    fields = []
    for ap in airports:
        d = distance_km(centre[0], centre[1], ap.lat, ap.lon)
        if d > a.gateway_max_km:
            continue
        mmi = event.mmi_at(ap.lat, ap.lon)
        fields.append(
            Field(
                airport=ap,
                dist_km=d,
                mmi=mmi,
                usability=runway_usability(mmi),
                best_aircraft=biggest_usable(ap.longest_runway_ft, ap.surface),
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
        # Regional (medium) airports rarely have the pavement strength or ramp
        # for C-5 / 747 class aircraft; cap them at the C-17.
        if ap.kind == "medium_airport" and ac.payload_tonnes > C17.payload_tonnes:
            ac = C17
        sorties_per_spot = a.ops_hours / ac.ground_time_h
        inflow = f.usability * a.mog_gateway[ap.kind] * sorties_per_spot * ac.payload_tonnes
        out.append(Gateway(field=f, aircraft=ac, inflow_tpd=inflow))
    out.sort(key=lambda g: g.inflow_tpd, reverse=True)
    return out


def forward_candidates(fields: list[Field], country: str | None, a: Assumptions) -> list[Field]:
    return [
        f for f in fields
        if f.in_zone
        and f.airport.longest_runway_ft >= a.forward_min_runway_ft
        and f.usability >= a.min_usability
        and (not a.domestic_only or country is None or same_country(f.airport.country, country))
    ]


def direct_credit(dist_km: float, a: Assumptions) -> float:
    """Share of cargo landing at a gateway that reaches the damage zone by road in the first days."""
    if dist_km <= a.road_reach_km:
        return 1.0
    if dist_km >= a.forward_max_km:
        return 0.0
    return 1.0 - (dist_km - a.road_reach_km) / (a.forward_max_km - a.road_reach_km)


def allocate_shuttles(gw: Gateway, strips: list[Field], a: Assumptions) -> list[Forward]:
    """Spread the shuttle fleet over forward strips, best tonnes-per-flight-hour first."""
    legs = []
    for s in strips:
        if s.airport.ident == gw.field.airport.ident:
            continue
        leg = distance_km(gw.field.airport.lat, gw.field.airport.lon, s.airport.lat, s.airport.lon)
        cycle = 2 * leg / SHUTTLE.cruise_kmh + 2 * SHUTTLE.ground_time_h
        max_sorties = a.ops_hours / cycle * a.mog_forward[s.airport.kind]   # ramp-limited
        tpd_per_hour = SHUTTLE.payload_tonnes * s.usability / cycle
        legs.append((tpd_per_hour, s, leg, cycle, max_sorties))
    legs.sort(key=lambda x: x[0], reverse=True)

    fleet_hours = a.shuttle_fleet * a.ops_hours
    out = []
    for _, s, leg, cycle, max_sorties in legs:
        if fleet_hours <= 0:
            break
        sorties = min(max_sorties, fleet_hours / cycle)
        fleet_hours -= sorties * cycle
        out.append(
            Forward(
                field=s,
                leg_km=leg,
                cycle_h=cycle,
                sorties_per_day=sorties,
                tonnes_per_day=sorties * SHUTTLE.payload_tonnes * s.usability,
            )
        )
    return out


def work_out(gw: Gateway, strips: list[Field], a: Assumptions) -> Option:
    forwards = allocate_shuttles(gw, strips, a)
    forwarded = sum(f.tonnes_per_day for f in forwards)
    # Cargo at the gateway reaches the zone two ways: by road if the gateway is
    # close enough, and by shuttle aircraft otherwise. Neither can exceed what
    # actually lands at the gateway.
    by_road = gw.inflow_tpd * direct_credit(gw.field.dist_km, a)
    delivered = min(gw.inflow_tpd, by_road + forwarded)
    return Option(gateway=gw, forwards=forwards, delivered_tpd=delivered)


def _better(x: Option, y: Option | None) -> bool:
    if y is None:
        return True
    if abs(x.delivered_tpd - y.delivered_tpd) > 1e-9:
        return x.delivered_tpd > y.delivered_tpd
    return x.gateway.field.dist_km < y.gateway.field.dist_km


# --------------------------------------------------------------------------- main entry


def build_plan(event: Event, airports: list[Airport], a: Assumptions | None = None) -> Plan:
    a = a or Assumptions()
    centre = damage_centre(event)
    fields = evaluate_fields(event, airports, centre, a)
    dem = demand_model.estimate(event.exposure)

    known = {ap.country for ap in airports}
    country = event.exposure.main_country(valid=known) if event.exposure else None
    if country is None and fields:
        country = fields[0].airport.country
    strips = forward_candidates(fields, country, a)

    cands = gateway_candidates(fields, a)
    # Every candidate is worked out in full: ranking by raw inflow first would
    # drop a slightly shaken airport next to the damage in favour of pristine
    # ones hundreds of kilometres away.
    domestic = [g for g in cands if same_country(g.field.airport.country, country)]
    foreign = [g for g in cands if not same_country(g.field.airport.country, country)]

    best_domestic = best_foreign = None
    for gw in domestic:
        opt = work_out(gw, strips, a)
        if _better(opt, best_domestic):
            best_domestic = opt
    for gw in foreign:
        opt = work_out(gw, strips, a)
        if _better(opt, best_foreign):
            best_foreign = opt

    # Domestic first: a cross-border hub needs diplomatic clearance the first
    # days rarely allow. Fall back to foreign only if nothing domestic works.
    if best_domestic and best_domestic.delivered_tpd > 0:
        chosen, alternatives = best_domestic, [o for o in [best_foreign] if o]
    else:
        chosen, alternatives = best_foreign, [o for o in [best_domestic] if o]

    delivered = chosen.delivered_tpd if chosen else 0.0
    people = delivered * 1000 / demand_model.KG_PER_PERSON_DAY
    coverage = (delivered / dem.tonnes_per_day) if dem and dem.tonnes_per_day > 0 else None

    traps = [
        f for f in fields
        if f.in_zone
        and f.airport.longest_runway_ft >= a.forward_min_runway_ft
        and f.usability < a.min_usability
    ]
    naive = next(
        (f for f in fields if f.airport.longest_runway_ft >= a.forward_min_runway_ft), None
    )

    return Plan(
        event=event,
        centre=centre,
        country=country,
        demand=dem,
        chosen=chosen,
        alternatives=alternatives,
        people_sustained=people,
        coverage=coverage,
        traps=traps,
        naive_pick=naive,
        assumptions=a,
        fields=fields,
    )
