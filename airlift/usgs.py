"""Everything we pull from the USGS.

Three public, key-free products per earthquake:

* the event itself (magnitude, location, time)
* ShakeMap: a grid of estimated shaking intensity (MMI, 1-10) around the quake,
  plus contour lines for drawing
* PAGER: how many people were exposed to each intensity level

Docs: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
      https://earthquake.usgs.gov/data/shakemap/
      https://earthquake.usgs.gov/data/pager/
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
DETAIL_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{id}.geojson"
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

    def __str__(self) -> str:
        return f"M {self.magnitude:.1f}  {self.place}  ({self.time:%Y-%m-%d %H:%M} UTC)"


def _quake_from_feature(feature: dict) -> Quake:
    props = feature["properties"]
    lon, lat, depth = feature["geometry"]["coordinates"]
    return Quake(
        id=feature["id"],
        magnitude=float(props["mag"]),
        place=props.get("place") or props.get("title") or "unknown location",
        lat=lat,
        lon=lon,
        depth_km=float(depth or 10.0),
        time=datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc),
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

    Built from the USGS 'coverage_mmi_low_res.covjson' product. Anything
    outside the grid is treated as not felt (MMI 0).
    """

    def __init__(self, cov: dict):
        axes = cov["domain"]["axes"]
        self.x0, self.x1, self.nx = axes["x"]["start"], axes["x"]["stop"], axes["x"]["num"]
        self.y0, self.y1, self.ny = axes["y"]["start"], axes["y"]["stop"], axes["y"]["num"]
        rng = cov["ranges"]["MMI"]
        if rng.get("axisNames") != ["y", "x"]:
            raise ValueError(f"unexpected axis order {rng.get('axisNames')}")
        self.values = [v if v is not None else 0.0 for v in rng["values"]]

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
        i = self._index(lat, lon)
        return self.values[i] if i is not None else 0.0

    def cells(self) -> Iterator[tuple[float, float, float]]:
        """Yield (lat, lon, mmi) for every grid cell."""
        for iy in range(self.ny):
            lat = self.y0 + (self.y1 - self.y0) * iy / (self.ny - 1)
            for ix in range(self.nx):
                lon = self.x0 + (self.x1 - self.x0) * ix / (self.nx - 1)
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
    """People exposed to each MMI level, from PAGER."""

    by_mmi: dict[int, int]
    by_country: dict[str, dict[int, int]]   # ISO-2 code -> {mmi: people}

    def at_least(self, mmi: int) -> int:
        return sum(n for level, n in self.by_mmi.items() if level >= mmi)

    def main_country(self, mmi: int = 7) -> str | None:
        """The country with the most people at or above this intensity."""
        totals = {
            c: sum(n for level, n in levels.items() if level >= mmi)
            for c, levels in self.by_country.items()
        }
        totals = {c: n for c, n in totals.items() if n > 0}
        return max(totals, key=totals.get) if totals else None

    @classmethod
    def from_pager_xml(cls, text: str) -> "Exposure":
        """Older events (before ~2018) only ship pager.xml."""
        import xml.etree.ElementTree as ET

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
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return response.content


def _product_url(products: dict, product: str, content: str) -> str | None:
    entries = products.get(product)
    if not entries:
        return None
    contents = entries[0].get("contents", {})
    return contents.get(content, {}).get("url")


def fetch_event(quake_id: str) -> Event:
    """Load one quake plus its ShakeMap and PAGER products (cached on disk)."""
    folder = CACHE_DIR / quake_id
    detail = json.loads(_cached_get(DETAIL_URL.format(id=quake_id), folder / "detail.json"))
    quake = _quake_from_feature(detail)
    products = detail["properties"].get("products", {})

    shake = exposure = contours = alert = None

    url = _product_url(products, "shakemap", "download/coverage_mmi_low_res.covjson")
    if url:
        shake = ShakeGrid(json.loads(_cached_get(url, folder / "mmi_low_res.covjson")))

    url = _product_url(products, "shakemap", "download/cont_mi.json")
    if url:
        contours = json.loads(_cached_get(url, folder / "cont_mi.json"))

    url = _product_url(products, "losspager", "json/exposures.json")
    if url:
        exposure = Exposure.from_json(json.loads(_cached_get(url, folder / "exposures.json")))
    else:
        url = _product_url(products, "losspager", "pager.xml")
        if url:
            exposure = Exposure.from_pager_xml(_cached_get(url, folder / "pager.xml").decode("utf-8", "replace"))

    pager = products.get("losspager")
    if pager:
        alert = pager[0].get("properties", {}).get("alertlevel")

    return Event(quake=quake, shake=shake, exposure=exposure, contours=contours, alert=alert)
