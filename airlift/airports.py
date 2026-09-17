"""Load the OurAirports airport and runway tables.

Data: https://ourairports.com/data/  (public domain, updated nightly)
The two CSVs are downloaded once into data/ and reused after that. Because
the source changes nightly, provenance() reports the download date and hash
of the copies in use, and the backtests record them with their results.
"""

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"

# Airport types worth considering for a relief flight. Heliports, seaplane
# bases and closed fields are skipped.
USABLE_TYPES = {"large_airport", "medium_airport", "small_airport"}

# Surfaces that are not something a cargo aircraft can land on.
NOT_A_RUNWAY = ("WATER", "WTR", "ICE", "SNO")

# Fields whose own name says they are not built for transport aircraft.
NOT_FOR_TRANSPORTS = ("ULTRALIGHT", "GLIDERPORT", "GLIDER PORT")


@dataclass(frozen=True)
class Airport:
    ident: str          # ICAO code where one exists, e.g. KSFO
    name: str
    country: str        # ISO-2 code
    kind: str           # large_airport / medium_airport / small_airport
    lat: float
    lon: float
    longest_runway_ft: int
    surface: str        # surface of the longest open runway
    width_ft: int = 0   # width of that runway; 0 when OurAirports does not record it

    @property
    def label(self) -> str:
        return f"{self.ident} {self.name}"


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


def provenance() -> list[dict]:
    """Download date and SHA-256 of the airport tables currently cached."""
    out = []
    for name in ("airports.csv", "runways.csv"):
        path = DATA_DIR / name
        if not path.exists():
            continue
        out.append({
            "file": name,
            "downloaded": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return out


def load_airports() -> list[Airport]:
    airports_csv = _download(AIRPORTS_URL, DATA_DIR / "airports.csv")
    runways_csv = _download(RUNWAYS_URL, DATA_DIR / "runways.csv")

    # Step 1: for each airport, find its longest open runway on land.
    longest: dict[str, tuple[int, str, int]] = {}
    with runways_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("closed") == "1":
                continue
            if (row.get("surface") or "").strip().upper().startswith(NOT_A_RUNWAY):
                continue            # seaplane lanes and ice or snow strips
            try:
                length_ft = int(float(row["length_ft"]))
            except (ValueError, KeyError):
                continue
            try:
                width_ft = int(float(row.get("width_ft") or 0))
            except ValueError:
                width_ft = 0
            ref = row["airport_ref"]
            if ref not in longest or length_ft > longest[ref][0]:
                longest[ref] = (length_ft, row.get("surface", ""), width_ft)

    # Step 2: build Airport objects for usable fields that have a runway.
    airports = []
    with airports_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["type"] not in USABLE_TYPES:
                continue
            if any(word in row["name"].upper() for word in NOT_FOR_TRANSPORTS):
                continue
            runway = longest.get(row["id"])
            if runway is None:
                continue
            airports.append(
                Airport(
                    ident=row["ident"],
                    name=row["name"],
                    country=row["iso_country"],
                    kind=row["type"],
                    lat=float(row["latitude_deg"]),
                    lon=float(row["longitude_deg"]),
                    longest_runway_ft=runway[0],
                    surface=runway[1],
                    width_ft=runway[2],
                )
            )
    return airports
