# Airlift Planner

**When an earthquake hits, which nearby airfields can take which relief aircraft?**

Disaster-response planners answer this question by hand: pull the quake location, open an airport database, check runway lengths and surfaces, cross-reference aircraft requirements, sort by distance. Airlift Planner turns that into one command.

```
uv run main.py --latest
```

```
M 5.6  78 km NNE of Tobelo, Indonesia  (2026-09-14 10:58 UTC)

      dist  airport                                             runway  surface   aircraft
  --------  ------------------------------------------------ ---------  --------- ------------------------------
     45 km  WAEW  Pitu Airport                                7,880 ft  ASP       C-130J A400M C-17 C-5M
    156 km  ID-0273  Marimoi Airport                          3,020 ft  ASP       C-130J A400M
    197 km  WAEE  Sultan Babullah Airport                     5,875 ft  ASP       C-130J A400M C-17
    243 km  WAMN  Melangguane Airport                         4,593 ft  ASP       C-130J A400M C-17
```

(Real output from 2026-09-15. Straight-line distances.)

## Why this exists

I'm a college freshman interested in decision-support software for defense and humanitarian operations. The core idea in that field is the same everywhere: an operator has a situation, an inventory of assets, and a set of physical constraints, and needs the right match fast. This project is my first attempt at that pattern, built entirely on public data.

## Data sources (all free, all public)

| source | what it provides | link |
|---|---|---|
| USGS Earthquake Hazards Program | live GeoJSON feed of recent earthquakes | https://earthquake.usgs.gov/earthquakes/feed/ |
| OurAirports | public-domain database of every airport and runway in the world | https://ourairports.com/data/ |

Aircraft runway requirements are approximate planning figures from public sources and are configurable in `airlift/aircraft.py`.

## How it works

1. `airlift/quakes.py` pulls recent earthquakes from the USGS feed.
2. `airlift/airports.py` downloads and caches the OurAirports airport and runway tables.
3. `airlift/planner.py` finds airfields within a radius of the quake, reads each one's longest open runway, and checks which aircraft can use it.
4. `main.py` prints the result as a ranked table.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/sachabidermann/airlift-planner
cd airlift-planner
uv sync
uv run main.py --list          # recent significant quakes
uv run main.py --latest        # plan for the most recent one
uv run main.py --quake <id>    # plan for a specific quake id
```

## Roadmap

- [ ] Population within reach of each airfield (WorldPop)
- [ ] Road distance from airfield to epicenter, not just straight line
- [ ] Web map view
- [ ] Other disaster feeds (cyclones, floods)

## Status

Early. Built in public. Feedback welcome.
