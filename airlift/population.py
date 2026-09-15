"""US population exposure for earthquakes that have no PAGER product (scenarios).

PAGER answers "how many people were shaken at each intensity". USGS does not
run it for most simulated scenarios, so for the United States we rebuild it
from public Census files:

  * county population estimates          (co-est2023-alldata.csv)
  * incorporated-place population         (sub-est2023.csv, SUMLEV 162 and 157)
  * county and place centroids and areas  (Census Gazetteer files)

Cities become points with their own population. What is left of each county
after subtracting its cities is spread over a disc the size of the county.
Each point is sampled against the ShakeMap grid and its people are binned by
intensity. Coarser than PAGER's 1 km population grid, but honest and free.

Puerto Rico: the municipio population file is not published in the same
folder; municipios are taken from the Gazetteer with the island's 2023 total
spread by land area. Flagged in the output as an approximation.
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .geo import US_ALIASES, same_country  # noqa: F401  (re-exported)
from .usgs import Event, Exposure, ShakeGrid

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "census"
COUNTY_POP = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/counties/totals/co-est2023-alldata.csv"
PLACE_POP = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/cities/totals/sub-est2023.csv"
STATE_POP = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2023/state/totals/NST-EST2023-ALLDATA.csv"
GAZ_COUNTIES = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_counties_national.zip"
GAZ_PLACES = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_place_national.zip"

@dataclass(frozen=True)
class PopPoint:
    lat: float
    lon: float
    people: int
    radius_km: float     # spread the people over a disc this size
    country: str         # "US" or "PR"


def _get(url: str, name: str) -> bytes:
    dest = DATA_DIR / name
    if dest.exists():
        return dest.read_bytes()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url} ...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return r.content


def _gazetteer(url: str, name: str) -> dict[str, tuple[float, float, float, str]]:
    """GEOID -> (lat, lon, land_km2, state_abbrev)."""
    raw = _get(url, name)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    out = {}
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        row = {k.strip(): (v.strip() if v else v) for k, v in row.items()}
        try:
            out[row["GEOID"]] = (float(row["INTPTLAT"]), float(row["INTPTLONG"]), float(row["ALAND"]) / 1e6, row["USPS"])
        except (KeyError, ValueError):
            continue
    return out


_POINTS: list[PopPoint] | None = None


def load_points() -> list[PopPoint]:
    """Build the US population point set once per process."""
    global _POINTS
    if _POINTS is not None:
        return _POINTS

    counties = _gazetteer(GAZ_COUNTIES, "gaz_counties.zip")
    places = _gazetteer(GAZ_PLACES, "gaz_places.zip")

    county_pop: dict[str, int] = {}
    for row in csv.DictReader(io.StringIO(_get(COUNTY_POP, "co-est2023-alldata.csv").decode("latin-1"))):
        if row["SUMLEV"] == "050":
            county_pop[row["STATE"] + row["COUNTY"]] = int(row["POPESTIMATE2023"])

    place_pop: dict[str, int] = {}
    place_in_county: dict[str, int] = {}
    for row in csv.DictReader(io.StringIO(_get(PLACE_POP, "sub-est2023.csv").decode("latin-1"))):
        if row["SUMLEV"] == "162":                      # whole incorporated place
            place_pop[row["STATE"] + row["PLACE"]] = int(row["POPESTIMATE2023"])
        elif row["SUMLEV"] == "157":                    # the part of a place inside one county
            key = row["STATE"] + row["COUNTY"]
            place_in_county[key] = place_in_county.get(key, 0) + int(row["POPESTIMATE2023"])

    points: list[PopPoint] = []
    for geoid, people in place_pop.items():
        g = places.get(geoid)
        if g and people > 0:
            points.append(PopPoint(g[0], g[1], people, max(1.0, math.sqrt(g[2] / math.pi)), "US"))
    for geoid, people in county_pop.items():
        g = counties.get(geoid)
        if not g:
            continue
        rest = people - place_in_county.get(geoid, 0)
        if rest > 0:
            points.append(PopPoint(g[0], g[1], rest, max(2.0, math.sqrt(g[2] / math.pi)), "US"))

    # Puerto Rico: island total spread over municipios by land area.
    pr_total = 0
    for row in csv.DictReader(io.StringIO(_get(STATE_POP, "nst-est2023-alldata.csv").decode("latin-1"))):
        if row.get("STATE") == "72":
            pr_total = int(row["POPESTIMATE2023"])
    pr = {k: v for k, v in counties.items() if k.startswith("72")}
    land = sum(v[2] for v in pr.values()) or 1.0
    for geoid, g in pr.items():
        points.append(PopPoint(g[0], g[1], int(pr_total * g[2] / land), max(2.0, math.sqrt(g[2] / math.pi)), "PR"))

    _POINTS = points
    return points


def _disc_samples(lat: float, lon: float, radius_km: float, cell_km: float) -> list[tuple[float, float]]:
    """Points spread over a disc; one point if the disc is smaller than a grid cell."""
    if radius_km <= cell_km:
        return [(lat, lon)]
    rings = min(4, int(radius_km / cell_km))
    pts = [(lat, lon)]
    for r in range(1, rings + 1):
        rad = radius_km * r / rings
        n = 6 * r
        for k in range(n):
            ang = 2 * math.pi * k / n
            dlat = rad / 111.0 * math.cos(ang)
            dlon = rad / (111.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(ang)
            pts.append((lat + dlat, lon + dlon))
    return pts


def exposure_from_grid(grid: ShakeGrid, points: list[PopPoint] | None = None) -> Exposure:
    """Population by rounded MMI, PAGER-style, for the area a ShakeMap covers."""
    points = points if points is not None else load_points()
    cell_km = abs(grid.y1 - grid.y0) / max(1, grid.ny - 1) * 111.0
    by_mmi: dict[int, int] = {m: 0 for m in range(1, 11)}
    by_country: dict[str, dict[int, int]] = {}
    for p in points:
        if not grid.covers(p.lat, p.lon):
            continue
        samples = _disc_samples(p.lat, p.lon, p.radius_km, cell_km)
        share = p.people / len(samples)
        acc = by_country.setdefault(p.country, {m: 0 for m in range(1, 11)})
        for lat, lon in samples:
            m = max(1, min(10, round(grid.mmi_at(lat, lon))))
            by_mmi[m] += share
            acc[m] += share
    by_mmi = {m: int(v) for m, v in by_mmi.items()}
    by_country = {c: {m: int(v) for m, v in acc.items()} for c, acc in by_country.items()}
    return Exposure(by_mmi=by_mmi, by_country=by_country)


def ensure_exposure(event: Event) -> Event:
    """Give an event without PAGER a Census-based exposure, if its grid touches the US."""
    if event.exposure is not None or event.shake is None:
        return event
    exp = exposure_from_grid(event.shake)
    if exp.at_least(1) > 0:
        event.exposure = Exposure(by_mmi=exp.by_mmi, by_country=exp.by_country, source="US Census (county and city points)")
    return event
