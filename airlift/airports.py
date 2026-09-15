"""Load the OurAirports airport and runway tables.

Data: https://ourairports.com/data/  (public domain, updated nightly)
The two CSVs are downloaded once into data/ and reused after that.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"

# Airport types worth considering for a relief flight. Heliports, seaplane
# bases and closed fields are skipped.
USABLE_TYPES = {"large_airport", "medium_airport", "small_airport"}


@dataclass(frozen=True)
class Airport:
    ident: str          # ICAO-style code, e.g. WIEE
    name: str
    country: str        # ISO-2 code
    lat: float
    lon: float
    longest_runway_ft: int
    surface: str        # surface of the longest open runway


def _download(url: str, dest: Path) -> Path:
    """Download url to dest unless it is already there."""
    if dest.exists():
        return dest
    DATA_DIR.mkdir(exist_ok=True)
    print(f"downloading {url} ...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def load_airports() -> list[Airport]:
    airports_csv = _download(AIRPORTS_URL, DATA_DIR / "airports.csv")
    runways_csv = _download(RUNWAYS_URL, DATA_DIR / "runways.csv")

    # Step 1: for each airport, find its longest open runway.
    longest: dict[str, tuple[int, str]] = {}
    with runways_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("closed") == "1":
                continue
            try:
                length_ft = int(float(row["length_ft"]))
            except (ValueError, KeyError):
                continue
            ref = row["airport_ref"]
            if ref not in longest or length_ft > longest[ref][0]:
                longest[ref] = (length_ft, row.get("surface", ""))

    # Step 2: build Airport objects for usable fields that have a runway.
    airports = []
    with airports_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["type"] not in USABLE_TYPES:
                continue
            runway = longest.get(row["id"])
            if runway is None:
                continue
            airports.append(
                Airport(
                    ident=row["ident"],
                    name=row["name"],
                    country=row["iso_country"],
                    lat=float(row["latitude_deg"]),
                    lon=float(row["longitude_deg"]),
                    longest_runway_ft=runway[0],
                    surface=runway[1],
                )
            )
    return airports
