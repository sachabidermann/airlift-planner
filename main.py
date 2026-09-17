"""Command-line entry point.

    uv run main.py --list                     significant quakes this week
    uv run main.py --latest                   plan for the newest one
    uv run main.py --quake us7000pn9s         plan for any USGS event or scenario id
    uv run main.py --quake <id> --refresh     fetch the latest ShakeMap version first
"""

import argparse
import sys

import requests

from airlift.airbridge import Assumptions, build_plan
from airlift.airports import load_airports
from airlift.population import ensure_exposure
from airlift.report import render_text
from airlift.usgs import fetch_event, fetch_recent


def main() -> int:
    parser = argparse.ArgumentParser(description="Airlift Planner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list recent quakes")
    group.add_argument("--latest", action="store_true", help="plan for the newest quake")
    group.add_argument("--quake", metavar="ID", help="plan for a specific USGS event or scenario id")
    parser.add_argument("--min-mag", type=float, default=5.5, help="minimum magnitude for --list/--latest (default 5.5)")
    parser.add_argument("--fleet", type=int, default=12, help="C-130-class shuttle aircraft available (default 12)")
    parser.add_argument("--forward-km", type=float, default=150, help="forward strips within this distance of the damage center (default 150)")
    parser.add_argument("--refresh", action="store_true", help="re-download this event's USGS products (USGS revises ShakeMaps, sometimes years later)")
    args = parser.parse_args()

    try:
        if args.list or args.latest:
            quakes = fetch_recent(min_magnitude=args.min_mag)
            if not quakes:
                print(f"no quakes at or above M{args.min_mag} in the past week")
                return 0
            if args.list:
                for q in quakes:
                    print(f"{q.id:<14} {q}")
                return 0
            quake_id = quakes[0].id
        else:
            quake_id = args.quake
        event = ensure_exposure(fetch_event(quake_id, refresh=args.refresh))
        airports = load_airports()
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    except requests.HTTPError as err:
        code = err.response.status_code if err.response is not None else "?"
        print(f"USGS returned HTTP {code}. Check the event id (see --list, or https://earthquake.usgs.gov/earthquakes/map/).", file=sys.stderr)
        return 1
    except requests.RequestException as err:
        print(f"network error: {err}", file=sys.stderr)
        return 1

    plan = build_plan(event, airports, Assumptions(shuttle_fleet=args.fleet, forward_max_km=args.forward_km))
    print(render_text(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
