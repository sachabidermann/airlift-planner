"""Command-line entry point.

    uv run main.py --list            recent significant quakes
    uv run main.py --latest          plan for the most recent one
    uv run main.py --quake <id>      plan for a specific quake id
"""

import argparse
import sys

from airlift.airports import load_airports
from airlift.planner import plan
from airlift.quakes import fetch_quakes


def print_plan(quake, options, limit):
    print()
    print(quake)
    print()
    if not options:
        print("  no usable airfields within range")
        return
    print(f"  {'dist':>8}  {'airport':<48} {'runway':>9}  {'surface':<9} aircraft")
    print(f"  {'-' * 8}  {'-' * 48} {'-' * 9}  {'-' * 9} {'-' * 30}")
    for o in options[:limit]:
        label = f"{o.airport.ident}  {o.airport.name}"[:48]
        names = " ".join(a.name for a in o.aircraft)
        print(
            f"  {o.distance_km:>5.0f} km  {label:<48} "
            f"{o.airport.longest_runway_ft:>6,} ft  {o.airport.surface[:9]:<9} {names}"
        )
    if len(options) > limit:
        print(f"  ... {len(options) - limit} more within range")


def main() -> int:
    parser = argparse.ArgumentParser(description="Airlift Planner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list recent quakes")
    group.add_argument("--latest", action="store_true", help="plan for the newest quake")
    group.add_argument("--quake", metavar="ID", help="plan for a specific USGS quake id")
    parser.add_argument("--min-mag", type=float, default=5.5, help="minimum magnitude (default 5.5)")
    parser.add_argument("--radius", type=float, default=300, help="search radius in km (default 300)")
    parser.add_argument("--limit", type=int, default=15, help="rows to show (default 15)")
    args = parser.parse_args()

    quakes = fetch_quakes(min_magnitude=args.min_mag)
    if not quakes:
        print(f"no quakes at or above M{args.min_mag} in the past week")
        return 0

    if args.list:
        for q in quakes:
            print(f"{q.id:<14} {q}")
        return 0

    if args.latest:
        quake = quakes[0]
    else:
        matches = [q for q in quakes if q.id == args.quake]
        if not matches:
            print(f"quake id {args.quake!r} not found; run --list to see ids", file=sys.stderr)
            return 1
        quake = matches[0]

    airports = load_airports()
    options = plan(quake, airports, radius_km=args.radius)
    print_plan(quake, options, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
