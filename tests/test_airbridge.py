"""The airbridge planner on a small hand-made world. No network.

The world: a 4 x 4 degree shaking grid centered on (0, 0), strongest in the
middle, and six airports placed so each rule has something to act on.
"""

import math
from datetime import datetime, timezone

import pytest

from airlift.aircraft import C17, SHUTTLE, SHUTTLE_BLOCK_KMH, B747F
from airlift.airbridge import (Assumptions, allocate_shuttles, build_plan, damage_center, direct_credit,
                               evaluate_fields, gateway_candidates, strip_credit)
from airlift.airports import Airport
from airlift.geo import distance_km
from airlift.usgs import Event, Exposure, Quake, ShakeGrid

KM = 1 / 111.195   # degrees of latitude per km


def cone_grid(peak=9.5, per_degree=3.0, n=81):
    """MMI falls off linearly with distance from (0, 0)."""
    values = []
    for iy in range(n):
        lat = -2 + 4 * iy / (n - 1)
        for ix in range(n):
            lon = -2 + 4 * ix / (n - 1)
            values.append(max(1.0, peak - per_degree * math.hypot(lat, lon)))
    return ShakeGrid(-2, 2, n, -2, 2, n, values)


def airport(ident, lat, lon, kind="small_airport", runway=5000, surface="ASP", country="AA"):
    return Airport(ident=ident, name=f"{ident} Field", country=country, kind=kind, lat=lat, lon=lon,
                   longest_runway_ft=runway, surface=surface)


AIRPORTS = [
    airport("NEAR", 0.05, 0.0, "large_airport", 11000),              # on top of the damage, MMI ~9.4
    airport("HUB", 1.2, 0.0, "large_airport", 10000),               # 133 km out, MMI ~5.9
    airport("REGN", 0.0, 1.5, "medium_airport", 9000),              # medium: capped at the C-17
    airport("STRP", 0.5, 0.0, "small_airport", 4000, "GRVL"),       # forward strip, MMI 8.0
    airport("TINY", 0.3, 0.3, "small_airport", 2000),               # too short for anything
    airport("FORN", -1.0, 0.0, "large_airport", 12000, country="BB"),
]


def event(people=None, exposure=True):
    exp = Exposure(by_mmi={7: 300_000, 8: 100_000, 9: 50_000}, by_country={"AA": {7: 300_000, 8: 100_000, 9: 50_000}}) if exposure else None
    quake = Quake("test", 7.5, "Testland", 0.0, 0.0, 10.0, datetime(2026, 1, 1, tzinfo=timezone.utc))
    return Event(quake=quake, shake=cone_grid(), exposure=exp, alert=None, people=people or [])


def test_direct_credit_fades_linearly():
    a = Assumptions()
    assert direct_credit(0, a) == 1 and direct_credit(50, a) == 1
    assert direct_credit(100, a) == pytest.approx(0.5)
    assert direct_credit(150, a) == 0 and direct_credit(400, a) == 0


def test_gateway_inflow_follows_afpam_formula():
    a = Assumptions()
    fields = evaluate_fields(event(), AIRPORTS, (0.0, 0.0), a)
    by = {g.field.airport.ident: g for g in gateway_candidates(fields, a)}
    hub = by["HUB"]
    # spots x planning payload x (operating hours / ground time) x 0.85 x usability
    expected = 6 * B747F.payload_tonnes * (20 / B747F.ground_time_h) * 0.85 * hub.field.usability
    assert hub.aircraft is B747F
    assert hub.inflow_tpd == pytest.approx(expected)
    assert by["REGN"].aircraft is C17, "a medium airport is capped at the C-17 even with a 9,000 ft runway"
    assert "NEAR" not in by, "an airport flagged as likely knocked out cannot be a gateway"
    assert "TINY" not in by and "STRP" not in by


def test_shuttle_allocation_respects_fleet_and_ramp():
    a = Assumptions(shuttle_fleet=2)
    fields = evaluate_fields(event(), AIRPORTS, (0.0, 0.0), a)
    hub = next(g for g in gateway_candidates(fields, a) if g.field.airport.ident == "HUB")
    strips = [f for f in fields if f.airport.ident == "STRP"]
    (fwd,) = allocate_shuttles(hub, strips, a)
    leg = distance_km(1.2, 0.0, 0.5, 0.0)
    cycle = 2 * leg / SHUTTLE_BLOCK_KMH + 2 * SHUTTLE.ground_time_h
    ramp_limit = 20 / cycle * 1 * 0.85                      # one parking spot on a small strip
    assert fwd.cycle_h == pytest.approx(cycle)
    assert fwd.sorties_per_day == pytest.approx(min(ramp_limit, 2 * 20 / cycle))
    assert fwd.tonnes_per_day == pytest.approx(fwd.sorties_per_day * SHUTTLE.payload_tonnes * fwd.field.usability * fwd.credit)
    assert fwd.sorties_per_day * cycle <= 2 * 20 + 1e-9


def test_strip_credit_matches_gateway_rule():
    a = Assumptions()
    fields = {f.airport.ident: f for f in evaluate_fields(event(), AIRPORTS, (0.0, 0.0), a)}
    assert strip_credit(fields["STRP"], a) == 1.0                     # shaken at MMI 8: inside the damage
    assert strip_credit(fields["HUB"], a) == direct_credit(fields["HUB"].dist_km, a)


def test_plan_invariants():
    for overrides in [{}, {"shuttle_fleet": 1}, {"shuttle_fleet": 60, "ops_hours": 24}, {"forward_max_km": 20},
                      {"forward_max_km": 400}, {"min_usability": 0.05}, {"min_usability": 0.95}, {"domestic_only": False}]:
        a = Assumptions(**overrides)
        plan = build_plan(event(), AIRPORTS, a)
        if plan.gateway is None:
            assert plan.delivered_tpd == 0
            continue
        assert 0 <= plan.delivered_tpd <= plan.gateway.inflow_tpd + 1e-6
        used = [f.field.airport.ident for f in plan.forwards]
        assert len(used) == len(set(used))
        assert plan.gateway.field.airport.ident not in used
        assert not {t.airport.ident for t in plan.traps} & (set(used) | {plan.gateway.field.airport.ident})
        assert sum(f.sorties_per_day * f.cycle_h for f in plan.forwards) <= a.shuttle_fleet * a.ops_hours + 1e-6
        assert all(0 <= f.usability <= 1 for f in plan.fields)
        assert plan.people_sustained == pytest.approx(plan.delivered_tpd * 1000 / plan.demand.kg_per_person_day)


def test_nearest_airfield_is_the_trap():
    plan = build_plan(event(), AIRPORTS)
    assert plan.naive_pick.airport.ident == "NEAR"
    assert "NEAR" in {t.airport.ident for t in plan.traps}
    assert plan.gateway.field.airport.ident == "HUB"


def test_domestic_gateway_preferred_and_foreign_reported():
    plan = build_plan(event(), AIRPORTS)
    assert plan.country == "AA"
    assert plan.gateway.field.airport.country == "AA"
    assert [o.gateway.field.airport.ident for o in plan.alternatives] == ["FORN"]


def test_damage_center_follows_people_not_ocean():
    # All the people live in the north-east; the shaking is symmetric around (0, 0).
    people = [(0.6, 0.6, 100_000.0), (0.7, 0.5, 50_000.0)]
    (lat, lon), basis = damage_center(event(people=people), AIRPORTS)
    assert basis == "shaking and population"
    assert lat > 0.5 and lon > 0.4
    (lat, lon), basis = damage_center(event(), AIRPORTS)       # no people known: airfields stand in for land
    assert basis == "shaking and airfield locations"
    (lat, lon), basis = damage_center(event(), None)           # nothing known: the shaking alone
    assert basis == "shaking" and abs(lat) < 0.01 and abs(lon) < 0.01


def test_no_exposure_means_no_coverage_figure():
    plan = build_plan(event(exposure=False), AIRPORTS)
    assert plan.demand is None and plan.coverage is None and plan.delivered_tpd > 0


def test_no_airports_in_range():
    plan = build_plan(event(), [airport("FAR", 40.0, 40.0, "large_airport", 12000)])
    assert plan.gateway is None and plan.delivered_tpd == 0 and plan.traps == []
