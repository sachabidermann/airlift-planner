"""Export everything the dashboard needs into docs/data.json.

    uv run dashboard/build.py

The dashboard (docs/index.html) re-runs the airbridge model in the browser, so
this exports the *inputs* per event (evaluated airfields, exposure, shaking
grid), not a finished plan. Included: the US and international real events,
the USGS scenarios, and every M5.5+ quake in the USGS feed for the past week.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtests"))

from airlift import demand as demand_model  # noqa: E402
from airlift.aircraft import AIRCRAFT, is_paved  # noqa: E402
from airlift.airbridge import Assumptions, damage_centre, evaluate_fields  # noqa: E402
from airlift.airports import load_airports  # noqa: E402
from airlift.geo import US_ALIASES  # noqa: E402
from airlift.population import ensure_exposure  # noqa: E402
from airlift.survivability import USABILITY  # noqa: E402
from airlift.usgs import fetch_event, fetch_recent  # noqa: E402
from run import EVENTS, SCENARIOS  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "data.json"

# Export enough airfields for the sliders' full range (forward radius up to 300 km).
EXPORT_A = Assumptions(forward_max_km=300)


def export_event(event, airports, meta=None, group="week"):
    meta = meta or {}
    centre = damage_centre(event)
    fields = evaluate_fields(event, airports, centre, EXPORT_A)
    q = event.quake
    keep = []
    for f in fields:
        ap = f.airport
        is_gateway_candidate = (
            ap.kind in ("large_airport", "medium_airport")
            and ap.longest_runway_ft >= EXPORT_A.gateway_min_runway_ft
        )
        is_strip_candidate = f.in_zone and ap.longest_runway_ft >= EXPORT_A.forward_min_runway_ft
        if not (is_gateway_candidate or is_strip_candidate):
            continue
        keep.append({
            "ident": ap.ident, "name": ap.name, "country": ap.country, "kind": ap.kind,
            "lat": round(ap.lat, 4), "lon": round(ap.lon, 4),
            "runway": ap.longest_runway_ft, "surface": ap.surface, "paved": is_paved(ap.surface),
            "mmi": round(f.mmi, 2), "dist": round(f.dist_km, 1),
            "best": f.best_aircraft.name if f.best_aircraft else None,
        })
    grid = None
    if event.shake:
        g = event.shake.downsampled(120)
        grid = {"x0": round(g.x0, 4), "x1": round(g.x1, 4), "nx": g.nx, "y0": round(g.y0, 4), "y1": round(g.y1, 4), "ny": g.ny,
                "v": [int(round(v * 10)) for v in g.values]}
    known = {ap.country for ap in airports}
    country = event.exposure.main_country(valid=known) if event.exposure else None
    if country is None and fields:
        country = fields[0].airport.country
    return {
        "id": q.id,
        "name": meta.get("name") or f"{q.place}, M{q.magnitude:.1f}",
        "title": str(q),
        "magnitude": q.magnitude,
        "place": q.place,
        "time": q.time.isoformat(),
        "scenario": q.scenario,
        "lat": q.lat, "lon": q.lon,
        "alert": event.alert,
        "mmi_source": event.mmi_source,
        "exposure_source": event.exposure.source if event.exposure else None,
        "centre": [round(centre[0], 4), round(centre[1], 4)],
        "country": country,
        "exposure": {str(k): v for k, v in event.exposure.by_mmi.items()} if event.exposure else None,
        "fields": keep,
        "grid": grid,
        "contours": None if grid else event.contours,
        "group": meta.get("group", group),
        "note": meta.get("happened"),
        "watch": meta.get("watch", []),
        "backtest": "actual" in meta,
        "closed": meta.get("closed"),
        "actual": meta.get("actual"),
        "actual_ident": meta.get("actual_ident"),
    }


def main() -> int:
    airports = load_airports()
    events = []
    for meta in EVENTS + SCENARIOS:
        print(meta["group"], meta["id"])
        events.append(export_event(ensure_exposure(fetch_event(meta["id"])), airports, meta))
    known = {e["id"] for e in events}
    for q in fetch_recent(5.5):
        if q.id in known:
            continue
        print("recent", q.id)
        events.append(export_event(fetch_event(q.id), airports, group="week"))

    data = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "aircraft": [
            {"name": a.name, "min_runway": a.min_runway_ft, "needs_paved": a.needs_paved,
             "payload": a.payload_tonnes, "cruise": a.cruise_kmh, "ground": a.ground_time_h}
            for a in AIRCRAFT
        ],
        "usability_curve": USABILITY,
        "country_aliases": US_ALIASES,
        "demand": {
            "food_kg": demand_model.FOOD_KG, "medical_kg": demand_model.MEDICAL_KG,
            "shelter_kit_kg": demand_model.SHELTER_KIT_KG, "shelter_kit_people": demand_model.SHELTER_KIT_PEOPLE,
            "first_days": demand_model.FIRST_DAYS, "kg_per_person_day": demand_model.KG_PER_PERSON_DAY,
        },
        "defaults": {
            "ops_hours": 20, "shuttle_fleet": 12, "gateway_max_km": 1000, "gateway_min_runway_ft": 7000,
            "forward_max_km": 150, "zone_min_mmi": 6.5, "forward_min_runway_ft": 3000,
            "min_usability": 0.5, "road_reach_km": 50, "domestic_only": True,
            "mog_gateway": {"large_airport": 6, "medium_airport": 3, "small_airport": 1},
            "mog_forward": {"large_airport": 3, "medium_airport": 2, "small_airport": 1},
        },
        "groups": [
            ["us-scenario", "United States: USGS scenario earthquakes"],
            ["us-real", "United States: real events"],
            ["intl-real", "International: real events"],
            ["week", "This week worldwide (USGS, M5.5+)"],
        ],
        "events": events,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(events)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
