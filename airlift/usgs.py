"""Everything we pull from the USGS.

Public, key-free products per earthquake, real or simulated:

* the event itself (magnitude, location, time)
* ShakeMap: a grid of estimated shaking intensity (MMI, 1-10) around the quake
* PAGER: how many people were exposed to each intensity level

Real events come from the ComCat detail feed. Simulated "scenario" events
(HayWired, ShakeOut, Cascadia, ...) come from the scenario catalog and carry
the same products under slightly different names.

Docs: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
      https://earthquake.usgs.gov/fdsnws/scenario/1/
      https://earthquake.usgs.gov/data/shakemap/
      https://earthquake.usgs.gov/data/pager/
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
DETAIL_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{id}.geojson"
SCENARIO_URL = "https://earthquake.usgs.gov/fdsnws/scenario/1/query?format=geojson&eventid={id}"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "usgs"


# --------------------------------------------------------------------------- quake


@dataclass(frozen=True)
class Quake:
    id: str
    magnitude: float
    place: str
    lat: float
    lon: float
    depth_km: float
    time: datetime
    scenario: bool = False

    def __str__(self) -> str:
        when = "USGS scenario, simulated" if self.scenario else f"{self.time:%Y-%m-%d %H:%M} UTC"
        return f"M {self.magnitude:.1f}  {self.place}  ({when})"


def _quake_from_feature(feature: dict, scenario: bool = False) -> Quake:
    props = feature["properties"]
    coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]
    lon, lat, depth = (list(coords) + [None, None, None])[:3]
    mag, when = props.get("mag"), props.get("time")
    if mag is None or when is None or lat is None or lon is None:
        # Some scenario records leave the summary fields empty; the origin product has them.
        origin = _product(props.get("products", {}), "origin", "origin-scenario")
        op = origin.get("properties", {}) if origin else {}

        def num(key):
            try:
                return float(op[key])
            except (KeyError, TypeError, ValueError):
                return None

        mag = mag if mag is not None else num("magnitude")
        lat = lat if lat is not None else num("latitude")
        lon = lon if lon is not None else num("longitude")
        depth = depth if depth is not None else num("depth")
        if when is None and op.get("eventtime"):
            when = datetime.fromisoformat(op["eventtime"].replace("Z", "+00:00")).timestamp() * 1000
    if mag is None or lat is None or lon is None:
        raise ValueError(f"USGS record {feature.get('id')!r} has no magnitude or location")
    return Quake(
        id=feature["id"],
        magnitude=float(mag),
        place=props.get("place") or props.get("title") or "unknown location",
        lat=float(lat),
        lon=float(lon),
        depth_km=float(depth) if depth is not None else 10.0,
        time=datetime.fromtimestamp((when or 0) / 1000, tz=timezone.utc),
        scenario=scenario,
    )


def fetch_recent(min_magnitude: float = 5.5) -> list[Quake]:
    """Quakes from the past 7 days at or above min_magnitude, newest first."""
    response = requests.get(FEED_URL, timeout=30)
    response.raise_for_status()
    quakes = [
        _quake_from_feature(f)
        for f in response.json()["features"]
        if f["properties"].get("mag") is not None and f["properties"]["mag"] >= min_magnitude
    ]
    quakes.sort(key=lambda q: q.time, reverse=True)
    return quakes


# --------------------------------------------------------------------------- shaking


class ShakeGrid:
    """Estimated shaking intensity (MMI) on a regular lat/lon grid.

    Values are stored row-major, south to north, west to east. Anything outside
    the grid is treated as not felt (MMI I). Cells USGS left empty are NaN.
    Grids that cross the 180th meridian use longitudes beyond +/-180, so
    lookups shift the requested longitude into the grid's range first.
    """

    def __init__(self, x0: float, x1: float, nx: int, y0: float, y1: float, ny: int, values: list[float]):
        if nx < 2 or ny < 2 or x0 == x1 or y0 == y1:
            raise ValueError("degenerate ShakeMap grid")
        if len(values) != nx * ny:
            raise ValueError(f"ShakeMap grid has {len(values)} values, expected {nx * ny}")
        self.x0, self.x1, self.nx = x0, x1, nx
        self.y0, self.y1, self.ny = y0, y1, ny
        self.values = values

    def _wrap(self, lon: float) -> float:
        lo, hi = min(self.x0, self.x1), max(self.x0, self.x1)
        if lo <= lon <= hi:
            return lon
        return lo + (lon - lo) % 360.0

    @classmethod
    def from_covjson(cls, cov: dict) -> "ShakeGrid":
        axes = cov["domain"]["axes"]
        rng = cov["ranges"]["MMI"]
        if rng.get("axisNames") != ["y", "x"]:
            raise ValueError(f"unexpected axis order {rng.get('axisNames')}")
        grid = cls(axes["x"]["start"], axes["x"]["stop"], axes["x"]["num"],
                   axes["y"]["start"], axes["y"]["stop"], axes["y"]["num"],
                   [float(v) if v is not None else math.nan for v in rng["values"]])
        return grid if grid.y1 > grid.y0 else grid._flipped()

    @classmethod
    def from_grid_xml(cls, raw: bytes, max_n: int = 1000) -> "ShakeGrid":
        """Older ShakeMaps and legacy scenarios only ship grid.xml.

        Read at full resolution unless an axis exceeds max_n cells, in which
        case every stride-th cell is kept.
        """
        root = ET.fromstring(raw)
        spec = mmi_index = None
        data_text = ""
        for el in root.iter():
            tag = el.tag.split("}")[-1]
            if tag == "grid_specification":
                spec = el.attrib
            elif tag == "grid_field" and el.attrib.get("name", "").upper() == "MMI":
                mmi_index = int(el.attrib["index"]) - 1
            elif tag == "grid_data":
                data_text = el.text or ""
        if spec is None or mmi_index is None:
            raise ValueError("grid.xml without grid_specification or MMI field")
        lon0, lon1 = float(spec["lon_min"]), float(spec["lon_max"])
        lat0, lat1 = float(spec["lat_min"]), float(spec["lat_max"])
        nlon, nlat = int(spec["nlon"]), int(spec["nlat"])
        stride = max(1, math.ceil(max(nlon, nlat) / max_n))
        nx, ny = (nlon - 1) // stride + 1, (nlat - 1) // stride + 1
        values = [math.nan] * (nx * ny)
        dlon, dlat = (lon1 - lon0) / max(1, nlon - 1), (lat1 - lat0) / max(1, nlat - 1)
        for line in data_text.split("\n"):
            parts = line.split()
            if len(parts) <= mmi_index:
                continue
            ix = round((float(parts[0]) - lon0) / dlon)
            iy = round((float(parts[1]) - lat0) / dlat)
            if ix % stride or iy % stride:
                continue
            cx, cy = ix // stride, iy // stride
            if 0 <= cx < nx and 0 <= cy < ny:
                values[cy * nx + cx] = float(parts[mmi_index])
        return cls(lon0, lon0 + dlon * stride * (nx - 1), nx, lat0, lat0 + dlat * stride * (ny - 1), ny, values)

    def _flipped(self) -> "ShakeGrid":
        rows = [self.values[i * self.nx:(i + 1) * self.nx] for i in range(self.ny)]
        return ShakeGrid(self.x0, self.x1, self.nx, self.y1, self.y0, self.ny, [v for r in reversed(rows) for v in r])

    def downsampled(self, max_n: int = 120) -> "ShakeGrid":
        stride = max(1, math.ceil(max(self.nx, self.ny) / max_n))
        if stride == 1:
            return self
        xs, ys = range(0, self.nx, stride), range(0, self.ny, stride)
        values = [self.values[iy * self.nx + ix] for iy in ys for ix in xs]
        dx, dy = (self.x1 - self.x0) / max(1, self.nx - 1), (self.y1 - self.y0) / max(1, self.ny - 1)
        return ShakeGrid(self.x0, self.x0 + dx * xs[-1], len(xs), self.y0, self.y0 + dy * ys[-1], len(ys), values)

    def covers(self, lat: float, lon: float) -> bool:
        if math.isnan(lat) or math.isnan(lon):
            return False
        fx = (self._wrap(lon) - self.x0) / (self.x1 - self.x0)
        fy = (lat - self.y0) / (self.y1 - self.y0)
        return 0 <= fx <= 1 and 0 <= fy <= 1

    def mmi_at(self, lat: float, lon: float) -> float:
        """MMI at a point, bilinear between the four surrounding cells.

        Outside the grid, or where USGS left the grid empty, counts as I (not felt).
        """
        if not self.covers(lat, lon):
            return 1.0
        fx = (self._wrap(lon) - self.x0) / (self.x1 - self.x0) * (self.nx - 1)
        fy = (lat - self.y0) / (self.y1 - self.y0) * (self.ny - 1)
        ix, iy = min(int(fx), self.nx - 2), min(int(fy), self.ny - 2)
        tx, ty = fx - ix, fy - iy
        v = self.values
        row0 = v[iy * self.nx + ix] * (1 - tx) + v[iy * self.nx + ix + 1] * tx
        row1 = v[(iy + 1) * self.nx + ix] * (1 - tx) + v[(iy + 1) * self.nx + ix + 1] * tx
        mmi = row0 * (1 - ty) + row1 * ty
        return 1.0 if math.isnan(mmi) else max(1.0, mmi)

    def cells(self) -> Iterator[tuple[float, float, float]]:
        """Yield (lat, lon, mmi) for every grid cell that has a value."""
        for iy in range(self.ny):
            lat = self.y0 + (self.y1 - self.y0) * iy / (self.ny - 1)
            for ix in range(self.nx):
                mmi = self.values[iy * self.nx + ix]
                if not math.isnan(mmi):
                    yield lat, self.x0 + (self.x1 - self.x0) * ix / (self.nx - 1), mmi


def estimate_mmi(magnitude: float, depth_km: float, epicentral_km: float) -> float:
    """Fallback when no ShakeMap exists: a published intensity-vs-distance formula.

    Allen, Wald and Worden (2012), "Intensity attenuation for active crustal
    regions", J. Seismol. 16:409-433, hypocentral-distance form:

        MMI = 2.085 + 1.428 M - 1.402 ln(sqrt(R^2 + Rm^2)) [+ 0.078 ln(R/50) if R > 50 km]
        Rm  = -0.209 + 2.042 exp(M - 5)

    R is hypocentral distance in km. Fitted for M 5.0-7.9 within 300 km.
    Coefficients checked against OpenQuake's allen_2012_ipe.py and its test
    table (tests/test_usgs.py). It assumes a point source and no site effects,
    so it is used only until USGS publishes a ShakeMap.
    """
    r = math.sqrt(epicentral_km**2 + depth_km**2)
    rm = -0.209 + 2.042 * math.exp(magnitude - 5)
    mmi = 2.085 + 1.428 * magnitude - 1.402 * math.log(math.sqrt(r**2 + rm**2))
    if r > 50:
        mmi += 0.078 * math.log(r / 50)
    return max(1.0, min(10.0, mmi))


# --------------------------------------------------------------------------- exposure


PAGER_US_CODES = {"WU", "EU", "XF"}


@dataclass(frozen=True)
class Exposure:
    """People exposed to each MMI level, from PAGER (or rebuilt from Census data)."""

    by_mmi: dict[int, int]
    by_country: dict[str, dict[int, int]]   # ISO-2 code -> {mmi: people}
    source: str = "USGS PAGER"

    def at_least(self, mmi: int) -> int:
        return sum(n for level, n in self.by_mmi.items() if level >= mmi)

    def main_country(self, mmi: int = 7, valid: set[str] | None = None) -> str | None:
        """The country with the most people at or above this intensity.

        PAGER splits the United States into internal region codes (WU west,
        EU east, XF California); they are counted as US. Pass the set of real
        country codes as `valid` to ignore anything else unrecognized.
        """
        totals: dict[str, int] = {}
        for code, levels in self.by_country.items():
            code = "US" if code in PAGER_US_CODES else code
            if valid is not None and code not in valid:
                continue
            totals[code] = totals.get(code, 0) + sum(n for level, n in levels.items() if level >= mmi)
        totals = {c: n for c, n in totals.items() if n > 0}
        return max(totals, key=totals.get) if totals else None

    @classmethod
    def from_pager_xml(cls, text: str) -> "Exposure":
        """Older events (before ~2018) only ship pager.xml."""
        root = ET.fromstring(text)
        by_mmi: dict[int, int] = {}
        for el in root.iter("exposure"):
            if el.get("dmin") is None or el.get("dmax") is None:
                continue
            mmi = math.floor((float(el.get("dmin")) + float(el.get("dmax"))) / 2 + 0.5)
            by_mmi[mmi] = by_mmi.get(mmi, 0) + int(float(el.get("exposure", 0)))
        ccode = root.get("ccode")
        return cls(by_mmi=by_mmi, by_country={ccode: dict(by_mmi)} if ccode else {})

    @classmethod
    def from_json(cls, data: dict) -> "Exposure":
        pe = data["population_exposure"]
        levels = [int(m) for m in pe["mmi"]]
        return cls(
            by_mmi=dict(zip(levels, (int(n) for n in pe["aggregated_exposure"]))),
            by_country={
                c["country_code"]: dict(zip(levels, (int(n) for n in c["exposure"])))
                for c in pe.get("country_exposures", [])
            },
        )


# --------------------------------------------------------------------------- event


@dataclass
class Event:
    quake: Quake
    shake: ShakeGrid | None      # None when the USGS made no ShakeMap
    exposure: Exposure | None    # None when there is no population exposure
    alert: str | None            # PAGER alert level: green / yellow / orange / red
    shake_version: int | None = None
    shake_updated: datetime | None = None
    shake_format: str | None = None   # "covjson medium", "covjson low" or "grid.xml"
    # Where people are: (lat, lon, people). From PAGER's city list, or Census
    # points for US scenarios. Used to center the plan on people, not on ocean.
    people: list[tuple[float, float, float]] = dataclasses.field(default_factory=list)

    @property
    def mmi_source(self) -> str:
        if not self.shake:
            return "distance formula (no ShakeMap yet)"
        if self.shake_version and self.shake_updated:
            return f"USGS ShakeMap v{self.shake_version}, {self.shake_updated:%Y-%m-%d}"
        return "USGS ShakeMap"

    def mmi_at(self, lat: float, lon: float) -> float:
        if self.shake:
            return self.shake.mmi_at(lat, lon)
        from .geo import distance_km  # local import to avoid a cycle
        d = distance_km(self.quake.lat, self.quake.lon, lat, lon)
        return estimate_mmi(self.quake.magnitude, self.quake.depth_km, d)


def _cached_get(url: str, dest: Path) -> bytes:
    """Download once. Written to a temporary name first so a failed download never leaves a partial file."""
    if dest.exists():
        return dest.read_bytes()
    response = requests.get(url, timeout=600)
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(dest)
    return response.content


def _product(products: dict, *names: str) -> dict | None:
    for name in names:
        entries = products.get(name)
        if entries:
            return entries[0]
    return None


def fetch_event(quake_id: str, refresh: bool = False) -> Event:
    """Load one quake (real or scenario) plus ShakeMap and PAGER, cached on disk.

    USGS revises ShakeMaps, often within hours and sometimes years later. Pass
    refresh=True during a live response to fetch the latest version. The new copy replaces
    the cached one only after every download has succeeded.
    """
    # The id becomes a folder name that refresh later deletes, so it must be a
    # plain USGS id and nothing that can climb out of the cache directory.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.]{0,79}", quake_id) or ".." in quake_id:
        raise ValueError(f"not a USGS event id: {quake_id!r}")
    folder = CACHE_DIR / quake_id
    if not refresh:
        return _load_event(quake_id, folder)
    fresh = CACHE_DIR / f"{quake_id}.refresh"
    shutil.rmtree(fresh, ignore_errors=True)
    try:
        event = _load_event(quake_id, fresh)
    except Exception:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    shutil.rmtree(folder, ignore_errors=True)
    fresh.replace(folder)
    return event


def _load_event(quake_id: str, folder: Path) -> Event:
    scenario = quake_id.endswith("_se")      # USGS scenario ids end in _se
    if scenario:
        # The regular feed answers for some scenario ids with a hollow record
        # (no magnitude, no coordinates); the scenario catalog has the real one.
        detail = json.loads(_cached_get(SCENARIO_URL.format(id=quake_id), folder / "detail.json"))
    else:
        try:
            detail = json.loads(_cached_get(DETAIL_URL.format(id=quake_id), folder / "detail.json"))
        except requests.HTTPError:
            detail = json.loads(_cached_get(SCENARIO_URL.format(id=quake_id), folder / "detail.json"))
            scenario = True
    if detail.get("type") == "FeatureCollection":            # a scenario query can wrap a collection
        if not detail.get("features"):
            raise ValueError(f"USGS has no event or scenario with id {quake_id!r}")
        detail = detail["features"][0]
        scenario = True
    if not scenario and "shakemap-scenario" in detail["properties"].get("products", {}):
        scenario = True
    # Keep the id we were asked for: USGS may answer with a different preferred
    # id (or none at all for some scenarios), and every link and cache uses ours.
    quake = dataclasses.replace(_quake_from_feature(detail, scenario=scenario), id=quake_id)
    products = detail["properties"].get("products", {})

    shake = exposure = alert = None
    shake_version = shake_updated = shake_format = None

    sm = _product(products, "shakemap", "shakemap-scenario")
    if sm:
        contents = sm.get("contents", {})
        try:
            shake_version = int(sm.get("properties", {}).get("version"))
        except (TypeError, ValueError):
            shake_version = None
        if sm.get("updateTime"):
            shake_updated = datetime.fromtimestamp(sm["updateTime"] / 1000, tz=timezone.utc)
        # Medium resolution (about 5 km cells) is preferred; low resolution and
        # the legacy grid.xml are fallbacks for older products.
        medium = contents.get("download/coverage_mmi_medium_res.covjson", {}).get("url")
        low = contents.get("download/coverage_mmi_low_res.covjson", {}).get("url")
        legacy = (contents.get("download/grid.xml") or contents.get("grid.xml") or {}).get("url")
        if medium:
            shake = ShakeGrid.from_covjson(json.loads(_cached_get(medium, folder / "mmi_medium_res.covjson")))
            shake_format = "covjson medium"
        elif low:
            shake = ShakeGrid.from_covjson(json.loads(_cached_get(low, folder / "mmi_low_res.covjson")))
            shake_format = "covjson low"
        elif legacy:
            shake = ShakeGrid.from_grid_xml(_cached_get(legacy, folder / "grid.xml"))
            shake_format = "grid.xml"

    people: list[tuple[float, float, float]] = []
    pager = _product(products, "losspager", "losspager-scenario")
    if pager:
        contents = pager.get("contents", {})
        url = contents.get("json/exposures.json", {}).get("url")
        if url:
            exposure = Exposure.from_json(json.loads(_cached_get(url, folder / "exposures.json")))
            url = contents.get("json/cities.json", {}).get("url")
            if url:
                cities = json.loads(_cached_get(url, folder / "cities.json")).get("all_cities", [])
                people = [(c["lat"], c["lon"], float(c.get("pop") or 0)) for c in cities]
        else:
            url = contents.get("pager.xml", {}).get("url")
            if url:
                text = _cached_get(url, folder / "pager.xml").decode("utf-8", "replace")
                exposure = Exposure.from_pager_xml(text)
                people = [(float(el.get("lat")), float(el.get("lon")), float(el.get("population") or 0))
                          for el in ET.fromstring(text).iter("city")]
        alert = pager.get("properties", {}).get("alertlevel")

    return Event(quake=quake, shake=shake, exposure=exposure, alert=alert,
                 shake_version=shake_version, shake_updated=shake_updated, shake_format=shake_format,
                 people=[p for p in people if p[2] > 0])
