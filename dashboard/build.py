"""Export everything the dashboard needs into docs/data.json.

    uv run dashboard/build.py

The dashboard (docs/index.html) re-runs the airbridge model in the browser, so
this exports the *inputs* per event (evaluated airfields, exposure, contours),
not a finished plan. The five backtests are always included, plus every M5.5+
quake in the USGS feed for the past week.
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
from airlift.survivability import USABILITY  # noqa: E402
from airlift.usgs import fetch_event, fetch_recent  # noqa: E402
from run import EVENTS as BACKTESTS  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "data.json"

# Export enough airfields for the sliders' full range (forward radius up to 300 km).
EXPORT_A = Assumptions(forward_max_km=300)


def export_event(event, airports, name=None, note=None, watch=None):
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
    return {
        "id": q.id,
        "name": name or f"{q.place}, M{q.magnitude:.1f}",
        "title": str(q),
        "magnitude": q.magnitude,
        "place": q.place,
        "time": q.time.isoformat(),
        "lat": q.lat, "lon": q.lon,
        "alert": event.alert,
        "mmi_source": event.mmi_source,
        "centre": [round(centre[0], 4), round(centre[1], 4)],
        "country": event.exposure.main_country() if event.exposure else (fields[0].airport.country if fields else None),
        "exposure": {str(k): v for k, v in event.exposure.by_mmi.items()} if event.exposure else None,
        "fields": keep,
        "contours": event.contours,
        "note": note,
        "watch": watch or [],
        "backtest": note is not None,
    }


def main() -> int:
    airports = load_airports()
    events = []
    for b in BACKTESTS:
        print("backtest", b["id"])
        events.append(export_event(fetch_event(b["id"]), airports, name=b["name"], note=b["happened"], watch=b["watch"]))
    backtest_ids = {b["id"] for b in BACKTESTS}
    for q in fetch_recent(5.5):
        if q.id in backtest_ids:
            continue
        print("recent", q.id)
        events.append(export_event(fetch_event(q.id), airports))

    data = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "aircraft": [
            {"name": a.name, "min_runway": a.min_runway_ft, "needs_paved": a.needs_paved,
             "payload": a.payload_tonnes, "cruise": a.cruise_kmh, "ground": a.ground_time_h}
            for a in AIRCRAFT
        ],
        "usability_curve": USABILITY,
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
        "events": events,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(events)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
