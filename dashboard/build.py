"""Export what the dashboard needs, and the answers the browser model must reproduce.

    uv run dashboard/build.py

Writes:
  docs/data.json           inputs per event (evaluated airfields, exposure, shaking grid).
                           The dashboard re-runs the airbridge model in the browser from these.
  dashboard/expected.json  the Python planner's results for every backtest and scenario under
                           nine assumption sets. `node dashboard/test_model.js` checks that
                           docs/model.js reproduces each one.
"""

import dataclasses
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backtests"))

from airlift import demand as demand_model  # noqa: E402
from airlift.aircraft import AIRCRAFT, C17, SHUTTLE, SHUTTLE_BLOCK_KMH, is_paved  # noqa: E402
from airlift.airbridge import Assumptions, build_plan, damage_center, evaluate_fields  # noqa: E402
from airlift.airports import load_airports, provenance  # noqa: E402
from airlift.geo import US_ALIASES  # noqa: E402
from airlift.population import ensure_exposure  # noqa: E402
from airlift.survivability import USABILITY  # noqa: E402
from airlift.usgs import fetch_event, fetch_recent  # noqa: E402
from events import EVENTS, SCENARIOS  # noqa: E402

DATA_OUT = ROOT / "docs" / "data.json"
EXPECTED_OUT = ROOT / "dashboard" / "expected.json"

# The dashboard's sliders go this far; export every airfield any setting could need.
SLIDER_MAX_FORWARD_KM = 300
EXPORT_A = Assumptions(forward_max_km=SLIDER_MAX_FORWARD_KM)

# Assumption sets the browser model is checked against, spanning the slider ranges.
CASES = [
    {},
    {"shuttle_fleet": 4},
    {"shuttle_fleet": 40, "ops_hours": 24},
    {"forward_max_km": 50},
    {"forward_max_km": 300},
    {"min_usability": 0.3},
    {"min_usability": 0.8},
    {"domestic_only": False},
    {"ops_hours": 8, "shuttle_fleet": 24, "forward_max_km": 200, "min_usability": 0.6},
]


def export_event(event, airports, meta=None, group="week"):
    meta = meta or {}
    center, center_basis = damage_center(event, airports)
    fields = evaluate_fields(event, airports, center, EXPORT_A)
    q = event.quake
    # Keep every airfield any slider setting could use, plus the nearest-airfield
    # pick and the watch list so the dashboard can always show them.
    naive = next((f for f in fields if f.airport.longest_runway_ft >= EXPORT_A.forward_min_runway_ft), None)
    always = set(meta.get("watch", [])) | ({naive.airport.ident} if naive else set())
    keep = []
    for f in fields:
        ap = f.airport
        gateway_candidate = ap.kind in ("large_airport", "medium_airport") and ap.longest_runway_ft >= EXPORT_A.gateway_min_runway_ft
        strip_candidate = f.in_zone and ap.longest_runway_ft >= EXPORT_A.forward_min_runway_ft
        if not (gateway_candidate or strip_candidate or ap.ident in always):
            continue
        keep.append({
            "ident": ap.ident, "name": ap.name, "country": ap.country, "kind": ap.kind,
            "lat": round(ap.lat, 6), "lon": round(ap.lon, 6),
            "runway": ap.longest_runway_ft, "surface": ap.surface, "paved": is_paved(ap.surface),
            "mmi": round(f.mmi, 6), "dist": round(f.dist_km, 6),
            "best": f.best_aircraft.name if f.best_aircraft else None,
        })
    grid = None
    if event.shake:
        g = event.shake.downsampled(120)
        grid = {"x0": round(g.x0, 4), "x1": round(g.x1, 4), "nx": g.nx, "y0": round(g.y0, 4), "y1": round(g.y1, 4), "ny": g.ny,
                "v": [None if math.isnan(v) else int(round(v * 10)) for v in g.values]}   # MMI x 10; null = no value
    known = {ap.country for ap in airports}
    country = event.exposure.main_country(valid=known) if event.exposure else None
    if country is None and fields:
        country = fields[0].airport.country
    return {
        "id": q.id,
        "name": meta.get("name") or f"{q.place}, M{q.magnitude:.1f}",
        "title": str(q),
        "magnitude": q.magnitude,
        "time": q.time.isoformat(),
        "scenario": q.scenario,
        "lat": q.lat, "lon": q.lon,
        "alert": event.alert,
        "mmi_source": event.mmi_source,
        "exposure_source": event.exposure.source if event.exposure else None,
        "center": [round(center[0], 4), round(center[1], 4)],
        "center_basis": center_basis,
        "country": country,
        "exposure": {str(k): v for k, v in event.exposure.by_mmi.items()} if event.exposure else None,
        "fields": keep,
        "grid": grid,
        "group": meta.get("group", group),
        "note": meta.get("happened"),
        "sources": meta.get("sources", []),
        "backtest": "hub_used" in meta,
        "closed": meta.get("closed"),
        "hub_text": meta.get("hub_text"),
        "hub_used": meta.get("hub_used", []),
    }


def expected_for(event, airports) -> list[dict]:
    out = []
    for overrides in CASES:
        plan = build_plan(event, airports, dataclasses.replace(Assumptions(), **overrides))
        out.append({
            "assumptions": overrides,
            "gateway": plan.gateway.field.airport.ident if plan.gateway else None,
            "delivered": round(plan.delivered_tpd, 3),
            "coverage": None if plan.coverage is None else round(plan.coverage, 6),
            "traps": sorted(t.airport.ident for t in plan.traps),
            "forwards": sorted(f.field.airport.ident for f in plan.forwards if f.sorties_per_day >= 0.5),
        })
    return out


def main() -> int:
    airports = load_airports()
    events, expected = [], {}
    for meta in EVENTS + SCENARIOS:
        print(meta["group"], meta["id"])
        event = ensure_exposure(fetch_event(meta["id"]))
        events.append(export_event(event, airports, meta))
        expected[meta["id"]] = expected_for(event, airports)
    known = {e["id"] for e in events}
    for q in fetch_recent(5.5):
        if q.id in known:
            continue
        print("recent", q.id)
        events.append(export_event(ensure_exposure(fetch_event(q.id)), airports, group="week"))

    data = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": provenance(),
        "aircraft": [
            {"name": a.name, "min_runway": a.min_runway_ft, "needs_paved": a.needs_paved,
             "payload": a.payload_tonnes, "ground": a.ground_time_h}
            for a in AIRCRAFT
        ],
        "shuttle": {"name": SHUTTLE.name, "block_kmh": SHUTTLE_BLOCK_KMH},
        "medium_airport_cap": C17.name,
        "usability_curve": USABILITY,
        "country_aliases": US_ALIASES,
        "demand": {
            "food_kg": demand_model.FOOD_KG, "medical_kg": demand_model.MEDICAL_KG,
            "shelter_kit_kg": demand_model.SHELTER_KIT_KG, "shelter_kit_people": demand_model.SHELTER_KIT_PEOPLE,
            "first_days": demand_model.FIRST_DAYS, "kg_per_person_day": demand_model.KG_PER_PERSON_DAY,
            "negligible_tpd": demand_model.NEGLIGIBLE_TPD,
        },
        "defaults": dataclasses.asdict(Assumptions()),
        "groups": [
            ["us-scenario", "United States: USGS scenario earthquakes"],
            ["us-real", "United States: real events"],
            ["intl-real", "International: real events"],
            ["week", "Recent at build time (USGS, M5.5+)"],
        ],
        "events": events,
    }
    DATA_OUT.parent.mkdir(exist_ok=True)
    DATA_OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    EXPECTED_OUT.write_text(json.dumps({"cases": len(CASES), "events": expected}, indent=1), encoding="utf-8")
    print(f"wrote {DATA_OUT} ({DATA_OUT.stat().st_size / 1024:.0f} KB, {len(events)} events)")
    print(f"wrote {EXPECTED_OUT} ({len(expected)} events x {len(CASES)} assumption sets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
