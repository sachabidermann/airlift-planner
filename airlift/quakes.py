"""Pull recent earthquakes from the USGS public feed.

Feed docs: https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php
No API key needed.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

# Magnitude 4.5 and above, past 7 days. Other feeds: "significant_week", "2.5_day", ...
FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"


@dataclass(frozen=True)
class Quake:
    id: str
    magnitude: float
    place: str
    lat: float
    lon: float
    time: datetime

    def __str__(self) -> str:
        return f"M {self.magnitude:.1f}  {self.place}  ({self.time:%Y-%m-%d %H:%M} UTC)"


def fetch_quakes(min_magnitude: float = 5.5) -> list[Quake]:
    """Return recent quakes at or above min_magnitude, newest first."""
    response = requests.get(FEED_URL, timeout=30)
    response.raise_for_status()
    quakes = []
    for feature in response.json()["features"]:
        props = feature["properties"]
        mag = props.get("mag")
        if mag is None or mag < min_magnitude:
            continue
        lon, lat, _depth = feature["geometry"]["coordinates"]
        quakes.append(
            Quake(
                id=feature["id"],
                magnitude=mag,
                place=props.get("place") or "unknown location",
                lat=lat,
                lon=lon,
                time=datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc),
            )
        )
    quakes.sort(key=lambda q: q.time, reverse=True)
    return quakes
