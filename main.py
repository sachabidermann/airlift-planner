"""Command-line entry point.

    uv run main.py --list                recent significant quakes
    uv run main.py --latest              airbridge plan for the newest one
    uv run main.py --quake us7000pn9s    airbridge plan for any USGS event id
"""

import argparse
import sys

from airlift.airbridge import Assumptions, build_plan
from airlift.airports import load_airports
from airlift.report import render_text, write_html
from airlift.usgs import fetch_event, fetch_recent


def main() -> int:
    parser = argparse.ArgumentParser(description="Airlift Planner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list recent quakes")
    group.add_argument("--latest", action="store_true", help="plan for the newest quake")
    group.add_argument("--quake", metavar="ID", help="plan for a specific USGS event id")
    parser.add_argument("--min-mag", type=float, default=5.5, help="minimum magnitude for --list/--latest (default 5.5)")
    parser.add_argument("--fleet", type=int, default=12, help="C-130-class shuttle aircraft available (default 12)")
    parser.add_argument("--forward-km", type=float, default=150, help="forward strips within this distance of the damage centre")
    parser.add_argument("--no-html", action="store_true", help="skip writing the HTML map")
    args = parser.parse_args()

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

    event = fetch_event(quake_id)
    airports = load_airports()
    plan = build_plan(event, airports, Assumptions(shuttle_fleet=args.fleet, forward_max_km=args.forward_km))
    print(render_text(plan))
    if not args.no_html:
        path = write_html(plan)
        print(f"map written to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
