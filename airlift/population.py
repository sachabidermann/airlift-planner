"""US population exposure for earthquakes that have no PAGER product.

PAGER answers "how many people were shaken at each intensity". USGS does not
run it for most scenario earthquakes or for events before about 2007, so for
the United States this module rebuilds the answer from public Census files:

  * county population estimates, vintage 2023      (co-est2023-alldata.csv)
  * incorporated-place population, vintage 2023    (sub-est2023.csv)
  * Puerto Rico municipio population, vintage 2023 (prm-est2023-pop.xlsx)
  * county and place centroids and land areas      (2023 Gazetteer files)

Each incorporated place becomes a point with its own population. What is left
of each county after subtracting its places is spread over a disc the size of
the county. Every point is sampled against the ShakeMap grid and its people
are binned by intensity.

Limits: US residents only (a grid that reaches Canada or Mexico misses those
people); 2023 population even for a 1989 replay; places are discs, not real
boundaries. backtests/verify_shaking.py compares this reconstruction with
PAGER on the events that have both. Expect agreement within about 15 percent
where hundreds of thousands of people are involved, and much worse for small
counts.
"""

from __future__ import annotations

import csv
import io
import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from .usgs import Event, Exposure, ShakeGrid

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "census"
POPEST = "https://www2.census.gov/programs-surveys/popest"
COUNTY_POP = f"{POPEST}/datasets/2020-2023/counties/totals/co-est2023-alldata.csv"
PLACE_POP = f"{POPEST}/datasets/2020-2023/cities/totals/sub-est2023.csv"
PR_MUNICIPIO_POP = f"{POPEST}/tables/2020-2023/municipios/totals/prm-est2023-pop.xlsx"
GAZETTEER = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer"
GAZ_COUNTIES = f"{GAZETTEER}/2023_Gaz_counties_national.zip"
GAZ_PLACES = f"{GAZETTEER}/2023_Gaz_place_national.zip"

# A place's people occupy at most its land area, and at least this density.
# Without the floor, Anchorage's 286,000 people would be spread over a
# municipality the size of Delaware.
MIN_URBAN_DENSITY_PER_KM2 = 1000

SOURCE = "US Census 2023 reconstruction (US residents only)"


@dataclass(frozen=True)
class PopPoint:
    lat: float
    lon: float
    people: int
    radius_km: float     # the people are spread over a disc this size
    country: str         # "US" or "PR"


def _get(url: str, name: str) -> bytes:
    dest = DATA_DIR / name
    if dest.exists():
        return dest.read_bytes()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url} ...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return r.content


def _gazetteer(url: str, name: str) -> dict[str, tuple[float, float, float, str]]:
    """GEOID -> (lat, lon, land_km2, place name)."""
    with zipfile.ZipFile(io.BytesIO(_get(url, name))) as z:
        text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    out = {}
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        row = {k.strip(): (v.strip() if v else v) for k, v in row.items()}
        try:
            out[row["GEOID"]] = (float(row["INTPTLAT"]), float(row["INTPTLONG"]), float(row["ALAND"]) / 1e6, row.get("NAME", ""))
        except (KeyError, ValueError):
            continue
    return out


def _pr_municipios() -> dict[str, int]:
    """Municipio name -> 2023 population, read from the Census spreadsheet with the standard library."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(_get(PR_MUNICIPIO_POP, "prm-est2023-pop.xlsx"))) as z:
        shared = ["".join(t.text or "" for t in si.iter(ns + "t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si")]
        sheet = ET.fromstring(z.read(next(n for n in sorted(z.namelist()) if n.startswith("xl/worksheets/sheet"))))
    out = {}
    for row in sheet.iter(ns + "row"):
        cells = []
        for c in row.iter(ns + "c"):
            v = c.find(ns + "v")
            text = v.text if v is not None else ""
            cells.append(shared[int(text)] if c.get("t") == "s" and text else text)
        if cells and cells[0].startswith(".") and "Municipio" in cells[0]:
            out[cells[0].lstrip(".").split(",")[0].strip()] = int(float(cells[-1]))   # last column is 2023
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
        if row["SUMLEV"] == "162":                                  # a whole incorporated place
            place_pop[row["STATE"] + row["PLACE"]] = int(row["POPESTIMATE2023"])
        elif row["SUMLEV"] == "157" and row["PLACE"] != "99990":   # the part of a place inside one county
            key = row["STATE"] + row["COUNTY"]                      # (99990 is "Balance of county", not a place)
            place_in_county[key] = place_in_county.get(key, 0) + int(row["POPESTIMATE2023"])

    points: list[PopPoint] = []
    for geoid, people in place_pop.items():
        g = places.get(geoid)
        if g and people > 0:
            by_area = math.sqrt(g[2] / math.pi)
            by_density = math.sqrt(people / MIN_URBAN_DENSITY_PER_KM2 / math.pi)
            points.append(PopPoint(g[0], g[1], people, max(1.0, min(by_area, by_density)), "US"))
    for geoid, people in county_pop.items():
        g = counties.get(geoid)
        rest = people - place_in_county.get(geoid, 0)
        if g and rest > 0:
            points.append(PopPoint(g[0], g[1], rest, max(2.0, math.sqrt(g[2] / math.pi)), "US"))

    # Nobody counted twice, nobody dropped.
    placed = sum(p.people for p in points)
    if abs(placed - sum(county_pop.values())) > 0.002 * placed:
        raise RuntimeError(f"Census points hold {placed:,} people, county totals say {sum(county_pop.values()):,}")

    municipios = _pr_municipios()
    for geoid, g in counties.items():
        if geoid.startswith("72") and g[3] in municipios:
            points.append(PopPoint(g[0], g[1], municipios[g[3]], max(2.0, math.sqrt(g[2] / math.pi)), "PR"))

    _POINTS = points
    return points


def _disc_samples(lat: float, lon: float, radius_km: float, cell_km: float) -> list[tuple[float, float]]:
    """Points covering a disc evenly by area; one point if the disc is smaller than a grid cell."""
    if radius_km <= cell_km:
        return [(lat, lon)]
    rings = min(4, max(1, int(radius_km / cell_km)))
    pts = []
    for r in range(1, rings + 1):
        # Ring r sits at the middle of its annulus and gets points in proportion to its area.
        rad = radius_km * (r - 0.5) / rings
        n = 3 * (2 * r - 1)
        for k in range(n):
            ang = 2 * math.pi * (k + 0.5 * (r % 2)) / n
            dlat = rad / 111.0 * math.cos(ang)
            dlon = rad / (111.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(ang)
            pts.append((lat + dlat, lon + dlon))
    return pts


def exposure_from_grid(grid: ShakeGrid, points: list[PopPoint] | None = None) -> Exposure:
    """Population by rounded MMI, PAGER-style, for the area a ShakeMap covers."""
    points = points if points is not None else load_points()
    cell_km = abs(grid.y1 - grid.y0) / max(1, grid.ny - 1) * 111.0
    by_mmi = {m: 0.0 for m in range(1, 11)}
    by_country: dict[str, dict[int, float]] = {}
    for p in points:
        if not grid.covers(p.lat, p.lon):
            continue
        samples = _disc_samples(p.lat, p.lon, p.radius_km, cell_km)
        share = p.people / len(samples)
        acc = by_country.setdefault(p.country, {m: 0.0 for m in range(1, 11)})
        for lat, lon in samples:
            m = max(1, min(10, math.floor(grid.mmi_at(lat, lon) + 0.5)))
            by_mmi[m] += share
            acc[m] += share
    return Exposure(
        by_mmi={m: int(v) for m, v in by_mmi.items()},
        by_country={c: {m: int(v) for m, v in acc.items()} for c, acc in by_country.items()},
        source=SOURCE,
    )


def ensure_exposure(event: Event) -> Event:
    """Give a US event without PAGER a Census-based exposure and population points."""
    if event.exposure is not None or event.shake is None:
        return event
    exposure = exposure_from_grid(event.shake)
    if exposure.at_least(1) > 0:
        event.exposure = exposure
        event.people = [(p.lat, p.lon, float(p.people)) for p in load_points() if event.shake.covers(p.lat, p.lon)]
    return event
