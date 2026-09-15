"""Everything we pull from the USGS.

Public, key-free products per earthquake, real or simulated:

* the event itself (magnitude, location, time)
* ShakeMap: a grid of estimated shaking intensity (MMI, 1-10) around the quake,
  plus contour lines for drawing
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
    lon, lat, depth = feature["geometry"]["coordinates"]
    mag, when = props.get("mag"), props.get("time")
    if mag is None or when is None:
        # Some scenario records leave the summary fields empty; the origin product has them.
        origin = _product(props.get("products", {}), "origin", "origin-scenario")
        op = origin.get("properties", {}) if origin else {}
        mag = mag if mag is not None else float(op.get("magnitude", 0))
        lat = lat if lat is not None else float(op.get("latitude", 0))
        lon = lon if lon is not None else float(op.get("longitude", 0))
        depth = depth if depth is not None else float(op.get("depth", 10))
        if when is None:
            t = op.get("eventtime")
            when = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() * 1000 if t else 0
    return Quake(
        id=feature["id"],
        magnitude=float(mag),
        place=props.get("place") or props.get("title") or "unknown location",
        lat=lat,
        lon=lon,
        depth_km=float(depth or 10.0),
        time=datetime.fromtimestamp(when / 1000, tz=timezone.utc),
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
    the grid is treated as not felt (MMI I).
    """

    def __init__(self, x0: float, x1: float, nx: int, y0: float, y1: float, ny: int, values: list[float]):
        self.x0, self.x1, self.nx = x0, x1, nx
        self.y0, self.y1, self.ny = y0, y1, ny
        self.values = values

    @classmethod
    def from_covjson(cls, cov: dict) -> "ShakeGrid":
        axes = cov["domain"]["axes"]
        rng = cov["ranges"]["MMI"]
        if rng.get("axisNames") != ["y", "x"]:
            raise ValueError(f"unexpected axis order {rng.get('axisNames')}")
        grid = cls(axes["x"]["start"], axes["x"]["stop"], axes["x"]["num"],
                   axes["y"]["start"], axes["y"]["stop"], axes["y"]["num"],
                   [v if v is not None else 0.0 for v in rng["values"]])
        return grid if grid.y1 > grid.y0 else grid._flipped()

    @classmethod
    def from_grid_xml(cls, raw: bytes, max_n: int = 160) -> "ShakeGrid":
        """Older ShakeMaps (and legacy scenarios) only ship grid.xml. Downsampled."""
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
        values = [0.0] * (nx * ny)
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

    def _index(self, lat: float, lon: float) -> int | None:
        fx = (lon - self.x0) / (self.x1 - self.x0)
        fy = (lat - self.y0) / (self.y1 - self.y0)
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        ix = round(fx * (self.nx - 1))
        iy = round(fy * (self.ny - 1))
        return iy * self.nx + ix

    def covers(self, lat: float, lon: float) -> bool:
        return self._index(lat, lon) is not None

    def mmi_at(self, lat: float, lon: float) -> float:
        """MMI at a point; outside the grid counts as I (not felt)."""
        i = self._index(lat, lon)
        return max(1.0, self.values[i]) if i is not None else 1.0

    def cells(self) -> Iterator[tuple[float, float, float]]:
        """Yield (lat, lon, mmi) for every grid cell."""
        for iy in range(self.ny):
            lat = self.y0 + (self.y1 - self.y0) * iy / max(1, self.ny - 1)
            for ix in range(self.nx):
                lon = self.x0 + (self.x1 - self.x0) * ix / max(1, self.nx - 1)
                yield lat, lon, self.values[iy * self.nx + ix]


def estimate_mmi(magnitude: float, depth_km: float, epicentral_km: float) -> float:
    """Fallback when no ShakeMap exists: a published intensity-vs-distance formula.

    Allen, Wald & Worden (2012), hypocentral-distance form for active crustal
    regions. Coarse. Used only when the USGS has not produced a ShakeMap.
    """
    r = math.sqrt(epicentral_km**2 + depth_km**2)
    h = 1 + 0.078 * math.exp(magnitude - 5)
    mmi = 2.085 + 1.428 * magnitude - 1.402 * math.log(math.sqrt(r**2 + h**2))
    if r > 50:
        mmi += 0.078 * math.log(r / 50)
    return max(0.0, min(10.0, mmi))


# --------------------------------------------------------------------------- exposure


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

        PAGER sometimes uses internal codes (e.g. "XF"); pass the set of real
        country codes to skip those.
        """
        totals = {
            c: sum(n for level, n in levels.items() if level >= mmi)
            for c, levels in self.by_country.items()
            if valid is None or c in valid
        }
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
            mmi = round((float(el.get("dmin")) + float(el.get("dmax"))) / 2)
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
    exposure: Exposure | None    # None when there is no PAGER product
    contours: dict | None        # GeoJSON MMI contour lines, for the map
    alert: str | None            # PAGER alert level: green / yellow / orange / red

    @property
    def mmi_source(self) -> str:
        return "USGS ShakeMap" if self.shake else "distance formula (no ShakeMap yet)"

    def mmi_at(self, lat: float, lon: float) -> float:
        if self.shake:
            return self.shake.mmi_at(lat, lon)
        from .geo import distance_km  # local import to avoid a cycle
        d = distance_km(self.quake.lat, self.quake.lon, lat, lon)
        return estimate_mmi(self.quake.magnitude, self.quake.depth_km, d)


def _cached_get(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=600)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return response.content


def _product(products: dict, *names: str) -> dict | None:
    for name in names:
        entries = products.get(name)
        if entries:
            return entries[0]
    return None


def fetch_event(quake_id: str) -> Event:
    """Load one quake (real or scenario) plus ShakeMap and PAGER, cached on disk."""
    folder = CACHE_DIR / quake_id
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
    if detail.get("type") == "FeatureCollection":            # scenario query wraps a collection
        detail = detail["features"][0]
        scenario = True
    if not scenario and "shakemap-scenario" in detail["properties"].get("products", {}):
        scenario = True
    # Keep the id we were asked for: USGS may answer with a different preferred
    # id (or none at all for some scenarios), and every link and cache uses ours.
    quake = dataclasses.replace(_quake_from_feature(detail, scenario=scenario), id=quake_id)
    products = detail["properties"].get("products", {})

    shake = exposure = contours = alert = None

    sm = _product(products, "shakemap", "shakemap-scenario")
    if sm:
        contents = sm.get("contents", {})
        url = contents.get("download/coverage_mmi_low_res.covjson", {}).get("url")
        if url:
            shake = ShakeGrid.from_covjson(json.loads(_cached_get(url, folder / "mmi_low_res.covjson")))
        else:
            url = (contents.get("download/grid.xml") or contents.get("grid.xml") or {}).get("url")
            if url:
                shake = ShakeGrid.from_grid_xml(_cached_get(url, folder / "grid.xml"))
        url = contents.get("download/cont_mi.json", {}).get("url")
        if url:
            contours = json.loads(_cached_get(url, folder / "cont_mi.json"))

    pager = _product(products, "losspager", "losspager-scenario")
    if pager:
        contents = pager.get("contents", {})
        url = contents.get("json/exposures.json", {}).get("url")
        if url:
            exposure = Exposure.from_json(json.loads(_cached_get(url, folder / "exposures.json")))
        else:
            url = contents.get("pager.xml", {}).get("url")
            if url:
                exposure = Exposure.from_pager_xml(_cached_get(url, folder / "pager.xml").decode("utf-8", "replace"))
        alert = pager.get("properties", {}).get("alertlevel")

    return Event(quake=quake, shake=shake, exposure=exposure, contours=contours, alert=alert)
