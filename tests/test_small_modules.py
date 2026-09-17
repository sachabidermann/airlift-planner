"""Usability curve, demand, aircraft fit, distances, population sampling. No network."""

import math

import pytest

from airlift import airports as airports_module
from airlift import demand
from airlift.aircraft import AIRCRAFT, biggest_usable, is_paved, usable_aircraft
from airlift.geo import distance_km, same_country
from airlift.population import PopPoint, _disc_samples, exposure_from_grid
from airlift.report import fmt_people, pct
from airlift.survivability import USABILITY, roman, runway_usability
from airlift.usgs import Exposure, ShakeGrid


# ---- survivability

def test_usability_curve_points_and_interpolation():
    for mmi, p in USABILITY:
        assert runway_usability(mmi) == pytest.approx(p)
    assert runway_usability(7.5) == pytest.approx(0.75)
    assert runway_usability(2) == 1.0 and runway_usability(12) == pytest.approx(0.10)


def test_usability_never_rises_with_shaking():
    values = [runway_usability(m / 10) for m in range(10, 111)]
    assert all(a >= b for a, b in zip(values, values[1:]))


def test_roman_rounds_halves_up_like_the_dashboard():
    assert [roman(m) for m in (4.49, 4.5, 6.5, 9.51, 0.2, 12)] == ["IV", "V", "VII", "X", "-", "X"]


# ---- demand

def test_demand_per_person_and_total():
    assert demand.KG_PER_PERSON_DAY == pytest.approx(0.56 + 0.02 + 19.4 / 5 / 7)
    exp = Exposure(by_mmi={6: 5_000_000, 7: 2_000_000, 8: 900_000, 9: 100_000}, by_country={})
    d = demand.estimate(exp)
    assert d.affected == 3_000_000 and d.priority == 1_000_000
    assert d.tonnes_per_day == pytest.approx(1_000_000 * demand.KG_PER_PERSON_DAY / 1000)
    assert demand.estimate(None) is None


# ---- aircraft

def test_which_aircraft_fit_a_runway():
    names = lambda runway, surface: [a.name for a in usable_aircraft(runway, surface)]
    assert names(2999, "ASP") == []
    assert names(3000, "GRVL") == ["C-130J-30", "A400M"]
    assert names(3500, "DIRT") == ["C-130J-30", "A400M", "C-17"]
    assert names(8999, "CON") == ["C-130J-30", "A400M", "C-17", "C-5M"]
    assert names(9000, "ASPH-G") == [a.name for a in AIRCRAFT]
    assert biggest_usable(12000, "GRVL").name == "C-17", "big jets need pavement"
    assert biggest_usable(1000, "ASP") is None


def test_paved_surface_text():
    assert all(is_paved(s) for s in ["ASP", "asphalt", "CONC", "PEM", "BIT", "Paved", "Hard", "CEM", "Composite"])
    assert not any(is_paved(s) for s in ["", "GRVL", "TURF", "DIRT", "WATER", "ICE"])


def test_airport_loader_skips_water_and_closed_runways(tmp_path, monkeypatch):
    (tmp_path / "airports.csv").write_text(
        "id,ident,type,name,latitude_deg,longitude_deg,iso_country\n"
        "1,AAAA,small_airport,Land,1,2,US\n2,BBBB,small_airport,Lake,3,4,US\n"
        "3,CCCC,heliport,Pad,5,6,US\n4,DDDD,small_airport,Shut,7,8,US\n")
    (tmp_path / "runways.csv").write_text(
        "airport_ref,length_ft,surface,closed\n1,4000,ASP,0\n1,6000,TURF,0\n2,13000,WATER,0\n3,100,CON,0\n4,9000,ASP,1\n")
    monkeypatch.setattr(airports_module, "DATA_DIR", tmp_path)
    loaded = {a.ident: a for a in airports_module.load_airports()}
    assert set(loaded) == {"AAAA"}
    assert loaded["AAAA"].longest_runway_ft == 6000 and loaded["AAAA"].surface == "TURF"
    assert len(airports_module.provenance()) == 2 and len(airports_module.provenance()[0]["sha256"]) == 64


# ---- geography and formatting

def test_great_circle_distance():
    assert distance_km(37.6188, -122.3750, 33.9425, -118.4081) == pytest.approx(543, abs=2)   # SFO to LAX
    assert distance_km(10, 179.5, 10, -179.5) == pytest.approx(distance_km(10, 0, 10, 1), rel=1e-9)
    assert distance_km(5, 5, 5, 5) == 0


def test_us_territories_count_as_domestic():
    assert same_country("PR", "US") and same_country("US", "GU") and same_country("TR", "TR")
    assert not same_country("US", "CA") and not same_country(None, "US")


def test_number_formatting():
    assert [fmt_people(n) for n in (950, 12_400, 999_499, 999_500, 5_440_000)] == ["950", "12k", "999k", "1.0M", "5.4M"]
    assert [pct(x) for x in (0.4972, 0.60, 0.9234, 1.0)] == ["49%", "60%", "92%", "100%"]


# ---- population sampling

def test_disc_samples_cover_the_disc_evenly():
    pts = _disc_samples(40.0, -100.0, radius_km=40, cell_km=5)
    radii = [distance_km(40.0, -100.0, la, lo) for la, lo in pts]
    assert max(radii) < 40
    assert sum(radii) / len(radii) == pytest.approx(40 * 2 / 3, rel=0.06)     # mean radius of a uniform disc
    assert _disc_samples(40.0, -100.0, radius_km=2, cell_km=5) == [(40.0, -100.0)]


def test_exposure_from_grid_conserves_people():
    n = 41
    values = [8.2 if ix >= n // 2 else 5.4 for _ in range(n) for ix in range(n)]      # east half MMI VIII, west half V
    grid = ShakeGrid(-101, -99, n, 39, 41, n, values)
    points = [PopPoint(40.0, -100.6, 70_000, 5.0, "US"), PopPoint(40.0, -99.4, 30_000, 5.0, "US"),
              PopPoint(45.0, -100.0, 999_999, 5.0, "US")]                              # outside the grid: ignored
    exp = exposure_from_grid(grid, points)
    assert sum(exp.by_mmi.values()) == 100_000
    assert exp.by_mmi[5] == 70_000 and exp.by_mmi[8] == 30_000
    assert exp.main_country() == "US"
